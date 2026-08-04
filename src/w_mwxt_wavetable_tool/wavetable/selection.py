from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from itertools import combinations
import json
import math
from typing import Mapping, Sequence

from .deduplication import CodeV8BAnalysis
from .metrics import compare_wave_shapes
from .models import (
    ConstraintStrength,
    USER_POSITION_COUNT,
    WavetableBuildRequest,
    WavetableCandidate,
    WavetableContractError,
)
from .usefulness import CandidateStructureClass, CandidateUsefulnessAnalysis

WAVETABLE_SELECTION_SCHEMA_VERSION = 1
_SELECTION_PRECISION = 12


def _q(value: float) -> float:
    return round(float(value), _SELECTION_PRECISION)


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _normalized(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise WavetableContractError(f"{name} must be a normalized non-empty string")
    return value


def _entries(values: Sequence[str], *, name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence")
    result = tuple(_normalized(value, name=f"{name} entry") for value in values)
    if not allow_empty and not result:
        raise WavetableContractError(f"{name} must not be empty")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


def _ratio(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked) or not 0.0 <= checked <= 1.0:
        raise WavetableContractError(f"{name} must be finite and between 0 and 1")
    return checked


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


class KeyframeSelectionStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


class SelectionEvidenceKind(str, Enum):
    REQUIRED_LOCK = "required_lock"
    REQUIRED_CHRONOLOGY = "required_chronology"
    SOURCE_ENDPOINT = "source_endpoint"
    BREAKPOINT = "breakpoint"
    FEATURE_EXTREME = "feature_extreme"
    STRUCTURAL = "structural"
    GROUP_REPRESENTATIVE = "group_representative"
    PROTECTED_REDUNDANT = "protected_redundant"
    UTILITY = "utility"
    DIVERSITY = "diversity"
    TEMPORAL_COVERAGE = "temporal_coverage"
    OMITTED_REDUNDANT = "omitted_redundant"
    OMITTED_CAPACITY = "omitted_capacity"


@dataclass(frozen=True, slots=True)
class KeyframeSelectionPolicy:
    schema_version: int = WAVETABLE_SELECTION_SCHEMA_VERSION
    maximum_keyframes: int = USER_POSITION_COUNT
    requested_keyframe_count: int | None = None
    preserve_source_endpoints: bool = True
    exact_search_candidate_limit: int = 16
    exact_search_combination_limit: int = 50000
    utility_weight: float = 0.42
    diversity_weight: float = 0.28
    temporal_coverage_weight: float = 0.12
    structural_coverage_weight: float = 0.12
    group_coverage_weight: float = 0.06

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_SELECTION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported keyframe-selection policy schema version")
        for name in ("maximum_keyframes", "exact_search_candidate_limit", "exact_search_combination_limit"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise WavetableContractError(f"{name} must be a positive integer")
        if self.maximum_keyframes > USER_POSITION_COUNT:
            raise WavetableContractError("maximum_keyframes cannot exceed 61")
        if self.requested_keyframe_count is not None:
            if isinstance(self.requested_keyframe_count, bool) or not isinstance(
                self.requested_keyframe_count, int
            ):
                raise WavetableContractError("requested_keyframe_count must be an integer or None")
            if not 1 <= self.requested_keyframe_count <= self.maximum_keyframes:
                raise WavetableContractError(
                    "requested_keyframe_count must be between 1 and maximum_keyframes"
                )
        if not isinstance(self.preserve_source_endpoints, bool):
            raise WavetableContractError("preserve_source_endpoints must be boolean")
        weight_names = (
            "utility_weight",
            "diversity_weight",
            "temporal_coverage_weight",
            "structural_coverage_weight",
            "group_coverage_weight",
        )
        for name in weight_names:
            _ratio(getattr(self, name), name=name)
        if abs(sum(getattr(self, name) for name in weight_names) - 1.0) > 1e-9:
            raise WavetableContractError("selection objective weights must sum to one")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "maximum_keyframes": self.maximum_keyframes,
            "requested_keyframe_count": self.requested_keyframe_count,
            "preserve_source_endpoints": self.preserve_source_endpoints,
            "exact_search_candidate_limit": self.exact_search_candidate_limit,
            "exact_search_combination_limit": self.exact_search_combination_limit,
            "utility_weight": self.utility_weight,
            "diversity_weight": self.diversity_weight,
            "temporal_coverage_weight": self.temporal_coverage_weight,
            "structural_coverage_weight": self.structural_coverage_weight,
            "group_coverage_weight": self.group_coverage_weight,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_KEYFRAME_SELECTION_POLICY = KeyframeSelectionPolicy()


@dataclass(frozen=True, slots=True)
class KeyframeSelectionScore:
    schema_version: int
    selected_candidate_ids: tuple[str, ...]
    objective_score: float
    utility_score: float
    diversity_score: float
    temporal_coverage_score: float
    structural_coverage_score: float
    group_coverage_score: float

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_SELECTION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported keyframe-selection score schema version")
        selected = _entries(
            self.selected_candidate_ids, name="selected_candidate_ids", allow_empty=False
        )
        object.__setattr__(self, "selected_candidate_ids", selected)
        if len(selected) > USER_POSITION_COUNT:
            raise WavetableContractError("selection score cannot exceed 61 candidates")
        for name in (
            "objective_score",
            "utility_score",
            "diversity_score",
            "temporal_coverage_score",
            "structural_coverage_score",
            "group_coverage_score",
        ):
            _ratio(getattr(self, name), name=name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "objective_score": self.objective_score,
            "utility_score": self.utility_score,
            "diversity_score": self.diversity_score,
            "temporal_coverage_score": self.temporal_coverage_score,
            "structural_coverage_score": self.structural_coverage_score,
            "group_coverage_score": self.group_coverage_score,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class CandidateSelectionDecision:
    schema_version: int
    candidate_id: str
    group_id: str
    source_order_index: int
    selected: bool
    essential: bool
    forced: bool
    source_endpoint: bool
    group_representative: bool
    protected: bool
    removable: bool
    structure_class: CandidateStructureClass
    utility_score: float
    structural_priority: float
    selected_source_order_rank: int | None
    evidence_kinds: tuple[SelectionEvidenceKind, ...]
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_SELECTION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported candidate-selection schema version")
        for name in ("candidate_id", "group_id"):
            _normalized(getattr(self, name), name=name)
        if isinstance(self.source_order_index, bool) or not isinstance(
            self.source_order_index, int
        ) or self.source_order_index < 0:
            raise WavetableContractError("source_order_index must be non-negative")
        for name in (
            "selected",
            "essential",
            "forced",
            "source_endpoint",
            "group_representative",
            "protected",
            "removable",
        ):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        if not isinstance(self.structure_class, CandidateStructureClass):
            raise WavetableContractError("structure_class must be CandidateStructureClass")
        _ratio(self.utility_score, name="utility_score")
        _ratio(self.structural_priority, name="structural_priority")
        if self.selected_source_order_rank is not None and (
            isinstance(self.selected_source_order_rank, bool)
            or not isinstance(self.selected_source_order_rank, int)
            or self.selected_source_order_rank < 1
        ):
            raise WavetableContractError("selected_source_order_rank must be positive or None")
        kinds = tuple(self.evidence_kinds)
        object.__setattr__(self, "evidence_kinds", kinds)
        if any(not isinstance(item, SelectionEvidenceKind) for item in kinds):
            raise WavetableContractError("evidence_kinds must contain SelectionEvidenceKind values")
        if len(set(kinds)) != len(kinds):
            raise WavetableContractError("evidence_kinds must be unique")
        evidence = _entries(self.evidence, name="evidence", allow_empty=False)
        object.__setattr__(self, "evidence", evidence)
        _normalized(self.reason, name="reason")
        if self.selected != (self.selected_source_order_rank is not None):
            raise WavetableContractError("selected and selected_source_order_rank disagree")
        if self.essential and not self.selected:
            raise WavetableContractError("essential candidates must be selected")
        if self.forced and not self.selected:
            raise WavetableContractError("forced candidates must be selected")
        if self.removable and self.protected:
            raise WavetableContractError("removable candidates cannot be protected")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "group_id": self.group_id,
            "source_order_index": self.source_order_index,
            "selected": self.selected,
            "essential": self.essential,
            "forced": self.forced,
            "source_endpoint": self.source_endpoint,
            "group_representative": self.group_representative,
            "protected": self.protected,
            "removable": self.removable,
            "structure_class": self.structure_class.value,
            "utility_score": self.utility_score,
            "structural_priority": self.structural_priority,
            "selected_source_order_rank": self.selected_source_order_rank,
            "evidence_kinds": [item.value for item in self.evidence_kinds],
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class WavetableKeyframeSelection:
    schema_version: int
    status: KeyframeSelectionStatus
    request_sha256: str
    v8b_analysis_sha256: str
    policy: KeyframeSelectionPolicy
    available_candidate_count: int
    candidate_pool_count: int
    target_keyframe_count: int
    selected_candidate_ids: tuple[str, ...]
    essential_candidate_ids: tuple[str, ...]
    forced_candidate_ids: tuple[str, ...]
    omitted_candidate_ids: tuple[str, ...]
    decisions: tuple[CandidateSelectionDecision, ...]
    exact_search_used: bool
    objective_score: float | None
    utility_score: float | None
    diversity_score: float | None
    temporal_coverage_score: float | None
    structural_coverage_score: float | None
    group_coverage_score: float | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_SELECTION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported keyframe-selection schema version")
        if not isinstance(self.status, KeyframeSelectionStatus):
            raise WavetableContractError("status must be KeyframeSelectionStatus")
        _sha256(self.request_sha256, name="request_sha256")
        _sha256(self.v8b_analysis_sha256, name="v8b_analysis_sha256")
        if not isinstance(self.policy, KeyframeSelectionPolicy):
            raise WavetableContractError("policy must be KeyframeSelectionPolicy")
        for name in (
            "available_candidate_count",
            "candidate_pool_count",
            "target_keyframe_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise WavetableContractError(f"{name} must be a non-negative integer")
        selected = _entries(self.selected_candidate_ids, name="selected_candidate_ids")
        essential = _entries(self.essential_candidate_ids, name="essential_candidate_ids")
        forced = _entries(self.forced_candidate_ids, name="forced_candidate_ids")
        omitted = _entries(self.omitted_candidate_ids, name="omitted_candidate_ids")
        warnings = _entries(self.warnings, name="warnings")
        blockers = _entries(self.blockers, name="blockers")
        decisions = tuple(self.decisions)
        object.__setattr__(self, "selected_candidate_ids", selected)
        object.__setattr__(self, "essential_candidate_ids", essential)
        object.__setattr__(self, "forced_candidate_ids", forced)
        object.__setattr__(self, "omitted_candidate_ids", omitted)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "decisions", decisions)
        if any(not isinstance(item, CandidateSelectionDecision) for item in decisions):
            raise WavetableContractError("decisions must contain CandidateSelectionDecision")
        decision_ids = tuple(item.candidate_id for item in decisions)
        if len(set(decision_ids)) != len(decision_ids):
            raise WavetableContractError("selection decisions must have unique candidate IDs")
        if len(decision_ids) != self.available_candidate_count:
            raise WavetableContractError("available_candidate_count disagrees with decisions")
        if set(selected) & set(omitted):
            raise WavetableContractError("selected and omitted candidates must be disjoint")
        if set(selected) | set(omitted) != set(decision_ids):
            raise WavetableContractError("selected and omitted candidates must partition decisions")
        if not set(essential).issubset(selected):
            raise WavetableContractError("essential candidates must be selected")
        if not set(forced).issubset(selected):
            raise WavetableContractError("forced candidates must be selected")
        if len(selected) > self.policy.maximum_keyframes or len(selected) > USER_POSITION_COUNT:
            raise WavetableContractError("selected keyframes exceed the 61-position capacity")
        if not isinstance(self.exact_search_used, bool):
            raise WavetableContractError("exact_search_used must be boolean")
        score_names = (
            "objective_score",
            "utility_score",
            "diversity_score",
            "temporal_coverage_score",
            "structural_coverage_score",
            "group_coverage_score",
        )
        for name in score_names:
            value = getattr(self, name)
            if value is not None:
                _ratio(value, name=name)
        _normalized(self.reason, name="reason")
        selected_from_decisions = tuple(item.candidate_id for item in decisions if item.selected)
        if selected_from_decisions != selected:
            raise WavetableContractError("selected decisions must follow selected_candidate_ids")
        if self.status is KeyframeSelectionStatus.COMPLETE:
            if blockers:
                raise WavetableContractError("complete selection cannot contain blockers")
            if not selected:
                raise WavetableContractError("complete selection must contain keyframes")
            if len(selected) != self.target_keyframe_count:
                raise WavetableContractError("complete selection count must equal target_keyframe_count")
            if any(getattr(self, name) is None for name in score_names):
                raise WavetableContractError("complete selection requires objective scores")
        else:
            if not blockers:
                raise WavetableContractError("rejected selection requires blockers")
            if selected or essential or forced:
                raise WavetableContractError("rejected selection cannot expose partial keyframes")
            if any(getattr(self, name) is not None for name in score_names):
                raise WavetableContractError("rejected selection cannot expose objective scores")
            if any(item.selected for item in decisions):
                raise WavetableContractError("rejected decisions cannot be selected")

    @property
    def selected_keyframe_count(self) -> int:
        return len(self.selected_candidate_ids)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "v8b_analysis_sha256": self.v8b_analysis_sha256,
            "policy": self.policy.to_dict(),
            "available_candidate_count": self.available_candidate_count,
            "candidate_pool_count": self.candidate_pool_count,
            "target_keyframe_count": self.target_keyframe_count,
            "selected_keyframe_count": self.selected_keyframe_count,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "essential_candidate_ids": list(self.essential_candidate_ids),
            "forced_candidate_ids": list(self.forced_candidate_ids),
            "omitted_candidate_ids": list(self.omitted_candidate_ids),
            "decisions": [item.to_dict() for item in self.decisions],
            "exact_search_used": self.exact_search_used,
            "objective_score": self.objective_score,
            "utility_score": self.utility_score,
            "diversity_score": self.diversity_score,
            "temporal_coverage_score": self.temporal_coverage_score,
            "structural_coverage_score": self.structural_coverage_score,
            "group_coverage_score": self.group_coverage_score,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "selects_final_keyframes": True,
                "assigns_user_positions": False,
                "orders_final_table": False,
                "solves_chronology": False,
                "generates_variants": False,
                "interpolates_transitions": False,
                "materializes_wctd": False,
                "generates_sysex": False,
                "opens_midi_port": False,
                "transmits_midi": False,
            },
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"


@dataclass(frozen=True, slots=True)
class CodeV8CAnalysis:
    schema_version: int
    request_sha256: str
    v8b_analysis_sha256: str
    selection: WavetableKeyframeSelection
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_SELECTION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-C schema version")
        _sha256(self.request_sha256, name="request_sha256")
        _sha256(self.v8b_analysis_sha256, name="v8b_analysis_sha256")
        if not isinstance(self.selection, WavetableKeyframeSelection):
            raise WavetableContractError("selection must be WavetableKeyframeSelection")
        if self.selection.request_sha256 != self.request_sha256:
            raise WavetableContractError("selection does not link to the request")
        if self.selection.v8b_analysis_sha256 != self.v8b_analysis_sha256:
            raise WavetableContractError("selection does not link to V8-B")
        warnings = _entries(self.warnings, name="warnings")
        object.__setattr__(self, "warnings", warnings)
        _normalized(self.reason, name="reason")

    @property
    def status(self) -> KeyframeSelectionStatus:
        return self.selection.status

    @property
    def selected_candidate_ids(self) -> tuple[str, ...]:
        return self.selection.selected_candidate_ids

    @property
    def essential_candidate_ids(self) -> tuple[str, ...]:
        return self.selection.essential_candidate_ids

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request_sha256,
            "v8b_analysis_sha256": self.v8b_analysis_sha256,
            "selection": self.selection.to_dict(),
            "status": self.status.value,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "essential_candidate_ids": list(self.essential_candidate_ids),
            "warnings": list(self.warnings),
            "reason": self.reason,
            "boundaries": {
                "assigns_user_positions": False,
                "orders_final_table": False,
                "solves_chronology": False,
                "generates_variants": False,
                "interpolates_transitions": False,
                "materializes_wctd": False,
                "generates_sysex": False,
                "opens_midi_port": False,
                "transmits_midi": False,
            },
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"


def _required_candidate_ids(request: WavetableBuildRequest) -> tuple[str, ...]:
    required: set[str] = {
        lock.candidate_id
        for lock in request.position_locks
        if lock.strength is ConstraintStrength.REQUIRED
    }
    for constraint in request.chronology_constraints:
        if constraint.strength is ConstraintStrength.REQUIRED:
            required.add(constraint.before_candidate_id)
            required.add(constraint.after_candidate_id)
    return tuple(sorted(required))


def _candidate_utility(
    candidate: WavetableCandidate,
    structure: CandidateUsefulnessAnalysis,
) -> float:
    metrics = candidate.metrics
    class_bonus = {
        CandidateStructureClass.INELIGIBLE: 0.00,
        CandidateStructureClass.STABLE: 0.04,
        CandidateStructureClass.TRANSITION: 0.08,
        CandidateStructureClass.STRUCTURAL: 0.13,
        CandidateStructureClass.EXTREME: 0.17,
        CandidateStructureClass.BREAKPOINT: 0.20,
    }[structure.structure_class]
    value = (
        0.24 * structure.effective_usefulness_score
        + 0.20 * structure.structural_score
        + 0.10 * metrics.quality_score
        + 0.10 * metrics.source_fidelity
        + 0.10 * metrics.xt_compatibility
        + 0.08 * metrics.perceptual_novelty
        + 0.06 * metrics.stability_score
        + 0.05 * metrics.harmonic_richness
        + 0.04 * metrics.bass_power
        + 0.03 * metrics.usefulness_score
        + class_bonus
    )
    if not candidate.structural_eligible:
        value *= 0.35
    return _q(min(1.0, max(0.0, value)))


def _structural_priority(structure: CandidateUsefulnessAnalysis) -> float:
    base = {
        CandidateStructureClass.INELIGIBLE: 0.0,
        CandidateStructureClass.STABLE: 0.20,
        CandidateStructureClass.TRANSITION: 0.45,
        CandidateStructureClass.STRUCTURAL: 0.72,
        CandidateStructureClass.EXTREME: 0.90,
        CandidateStructureClass.BREAKPOINT: 1.0,
    }[structure.structure_class]
    return _q(max(base, structure.structural_score))


def _source_endpoint_ids(v8b: CodeV8BAnalysis) -> tuple[str, ...]:
    order = v8b.structure.source_order_candidate_ids
    if len(order) == 1:
        return order
    candidate_group = {
        item.candidate_id: item.group_id for item in v8b.deduplication.candidates
    }
    group_rep = {
        group.group_id: group.representative_candidate_id
        for group in v8b.deduplication.groups
    }
    first = group_rep[candidate_group[order[0]]]
    last = group_rep[candidate_group[order[-1]]]
    return (first,) if first == last else (first, last)


def _pair_score_cache(
    candidate_ids: Sequence[str],
    candidates: Mapping[str, WavetableCandidate],
) -> dict[tuple[str, str], float]:
    ordered = tuple(candidate_ids)
    result: dict[tuple[str, str], float] = {}
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1 :]:
            distance = compare_wave_shapes(candidates[left], candidates[right])
            key = tuple(sorted((left, right)))
            result[key] = _q(
                0.60 * distance.perceptual_distance
                + 0.40 * distance.spectral_distance
            )
    return result


def _objective(
    selected_ids: Sequence[str],
    *,
    candidates: Mapping[str, WavetableCandidate],
    structures: Mapping[str, CandidateUsefulnessAnalysis],
    group_ids: Mapping[str, str],
    source_indices: Mapping[str, int],
    structural_pool_ids: frozenset[str],
    total_group_count: int,
    policy: KeyframeSelectionPolicy,
    pair_scores: Mapping[tuple[str, str], float],
) -> tuple[float, float, float, float, float, float]:
    selected = tuple(selected_ids)
    if not selected:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    utility = _q(sum(_candidate_utility(candidates[item], structures[item]) for item in selected) / len(selected))
    pair_values = [
        pair_scores[tuple(sorted((left, right)))]
        for left_index, left in enumerate(selected)
        for right in selected[left_index + 1 :]
    ]
    diversity = _q(sum(pair_values) / len(pair_values)) if pair_values else 1.0
    all_indices = tuple(source_indices.values())
    if len(all_indices) <= 1:
        temporal = 1.0
    else:
        span = max(all_indices) - min(all_indices)
        selected_span = max(source_indices[item] for item in selected) - min(
            source_indices[item] for item in selected
        )
        span_score = 1.0 if span == 0 else selected_span / span
        ordered = sorted(source_indices[item] for item in selected)
        if len(ordered) <= 1 or span == 0:
            spacing_score = span_score
        else:
            gaps = [right - left for left, right in zip(ordered, ordered[1:])]
            ideal = span / max(1, len(ordered) - 1)
            deviation = sum(abs(gap - ideal) for gap in gaps) / max(1e-12, span)
            spacing_score = max(0.0, 1.0 - deviation / max(1, len(gaps)))
        temporal = _q(0.65 * span_score + 0.35 * spacing_score)
    structural = _q(
        len(set(selected) & structural_pool_ids) / max(1, len(structural_pool_ids))
    ) if structural_pool_ids else 1.0
    group_coverage = _q(
        len({group_ids[item] for item in selected}) / max(1, min(len(selected), total_group_count))
    )
    objective = _q(
        policy.utility_weight * utility
        + policy.diversity_weight * diversity
        + policy.temporal_coverage_weight * temporal
        + policy.structural_coverage_weight * structural
        + policy.group_coverage_weight * group_coverage
    )
    return objective, utility, diversity, temporal, structural, group_coverage


def _selection_tie_key(ids: Sequence[str], source_indices: Mapping[str, int]) -> tuple[tuple[int, str], ...]:
    return tuple(sorted((source_indices[item], item) for item in ids))


def _select_exact(
    pool_ids: tuple[str, ...],
    mandatory_ids: frozenset[str],
    target_count: int,
    *,
    candidates: Mapping[str, WavetableCandidate],
    structures: Mapping[str, CandidateUsefulnessAnalysis],
    group_ids: Mapping[str, str],
    source_indices: Mapping[str, int],
    structural_pool_ids: frozenset[str],
    total_group_count: int,
    policy: KeyframeSelectionPolicy,
    pair_scores: Mapping[tuple[str, str], float],
) -> tuple[tuple[str, ...], tuple[float, float, float, float, float, float]]:
    optional = tuple(item for item in pool_ids if item not in mandatory_ids)
    needed = target_count - len(mandatory_ids)
    best_ids: tuple[str, ...] | None = None
    best_scores: tuple[float, float, float, float, float, float] | None = None
    best_tie: tuple[tuple[int, str], ...] | None = None
    for choice in combinations(optional, needed):
        ids = tuple(mandatory_ids) + choice
        scores = _objective(
            ids,
            candidates=candidates,
            structures=structures,
            group_ids=group_ids,
            source_indices=source_indices,
            structural_pool_ids=structural_pool_ids,
            total_group_count=total_group_count,
            policy=policy,
            pair_scores=pair_scores,
        )
        tie = _selection_tie_key(ids, source_indices)
        if (
            best_scores is None
            or scores > best_scores
            or (scores == best_scores and tie < best_tie)
        ):
            best_ids = tuple(item for _, item in tie)
            best_scores = scores
            best_tie = tie
    if best_ids is None or best_scores is None:
        raise WavetableContractError("exact keyframe selection produced no solution")
    return best_ids, best_scores


def _select_greedy(
    pool_ids: tuple[str, ...],
    mandatory_ids: frozenset[str],
    target_count: int,
    *,
    candidates: Mapping[str, WavetableCandidate],
    structures: Mapping[str, CandidateUsefulnessAnalysis],
    group_ids: Mapping[str, str],
    source_indices: Mapping[str, int],
    structural_pool_ids: frozenset[str],
    total_group_count: int,
    policy: KeyframeSelectionPolicy,
    pair_scores: Mapping[tuple[str, str], float],
) -> tuple[tuple[str, ...], tuple[float, float, float, float, float, float]]:
    selected = set(mandatory_ids)
    while len(selected) < target_count:
        best_candidate: str | None = None
        best_scores: tuple[float, float, float, float, float, float] | None = None
        for candidate_id in pool_ids:
            if candidate_id in selected:
                continue
            scores = _objective(
                tuple(selected) + (candidate_id,),
                candidates=candidates,
                structures=structures,
                group_ids=group_ids,
                source_indices=source_indices,
                structural_pool_ids=structural_pool_ids,
                total_group_count=total_group_count,
                policy=policy,
                pair_scores=pair_scores,
            )
            if (
                best_scores is None
                or scores > best_scores
                or (
                    scores == best_scores
                    and (source_indices[candidate_id], candidate_id)
                    < (source_indices[best_candidate], best_candidate)
                )
            ):
                best_candidate = candidate_id
                best_scores = scores
        if best_candidate is None:
            raise WavetableContractError("greedy keyframe selection exhausted the pool")
        selected.add(best_candidate)
    ordered = tuple(sorted(selected, key=lambda item: (source_indices[item], item)))
    return ordered, _objective(
        ordered,
        candidates=candidates,
        structures=structures,
        group_ids=group_ids,
        source_indices=source_indices,
        structural_pool_ids=structural_pool_ids,
        total_group_count=total_group_count,
        policy=policy,
        pair_scores=pair_scores,
    )


def evaluate_keyframe_subset(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    candidate_ids: Sequence[str],
    policy: KeyframeSelectionPolicy = DEFAULT_KEYFRAME_SELECTION_POLICY,
) -> KeyframeSelectionScore:
    """Evaluate one explicit candidate subset with the V8-C objective."""

    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(v8b_analysis, CodeV8BAnalysis):
        raise WavetableContractError("v8b_analysis must be CodeV8BAnalysis")
    if not isinstance(policy, KeyframeSelectionPolicy):
        raise WavetableContractError("policy must be KeyframeSelectionPolicy")
    if v8b_analysis.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("V8-B analysis does not link to the request")
    selected = _entries(candidate_ids, name="candidate_ids", allow_empty=False)
    candidate_by_id = {candidate.candidate_id: candidate for candidate in request.candidates}
    source_order = v8b_analysis.structure.source_order_candidate_ids
    if any(candidate_id not in candidate_by_id for candidate_id in selected):
        raise WavetableContractError("candidate_ids contain an unknown candidate")
    structure_by_id = {item.candidate_id: item for item in v8b_analysis.structure.candidates}
    dedup_by_id = {item.candidate_id: item for item in v8b_analysis.deduplication.candidates}
    source_indices = {candidate_id: index for index, candidate_id in enumerate(source_order)}
    group_ids = {candidate_id: dedup_by_id[candidate_id].group_id for candidate_id in source_order}
    structural_pool_ids = frozenset(
        candidate_id
        for candidate_id in source_order
        if structure_by_id[candidate_id].structure_class
        in {
            CandidateStructureClass.BREAKPOINT,
            CandidateStructureClass.EXTREME,
            CandidateStructureClass.STRUCTURAL,
        }
    )
    ordered = tuple(sorted(selected, key=lambda item: (source_indices[item], item)))
    pair_scores = _pair_score_cache(ordered, candidate_by_id)
    scores = _objective(
        ordered,
        candidates=candidate_by_id,
        structures=structure_by_id,
        group_ids=group_ids,
        source_indices=source_indices,
        structural_pool_ids=structural_pool_ids,
        total_group_count=v8b_analysis.distinct_wave_count,
        policy=policy,
        pair_scores=pair_scores,
    )
    return KeyframeSelectionScore(
        schema_version=WAVETABLE_SELECTION_SCHEMA_VERSION,
        selected_candidate_ids=ordered,
        objective_score=scores[0],
        utility_score=scores[1],
        diversity_score=scores[2],
        temporal_coverage_score=scores[3],
        structural_coverage_score=scores[4],
        group_coverage_score=scores[5],
    )


def select_wavetable_keyframes(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    policy: KeyframeSelectionPolicy = DEFAULT_KEYFRAME_SELECTION_POLICY,
) -> CodeV8CAnalysis:
    """Select the final V8-C keyframe set without assigning table positions.

    The returned candidate IDs are serialized in V8-B source order only. That
    canonical serialization order is not a final Wavetable ordering or a slot
    assignment; both remain V8-D responsibilities.
    """

    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(v8b_analysis, CodeV8BAnalysis):
        raise WavetableContractError("v8b_analysis must be CodeV8BAnalysis")
    if not isinstance(policy, KeyframeSelectionPolicy):
        raise WavetableContractError("policy must be KeyframeSelectionPolicy")
    if v8b_analysis.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("V8-B analysis does not link to the request")

    source_order = v8b_analysis.structure.source_order_candidate_ids
    candidate_by_id = {candidate.candidate_id: candidate for candidate in request.candidates}
    structure_by_id = {
        item.candidate_id: item for item in v8b_analysis.structure.candidates
    }
    dedup_by_id = {
        item.candidate_id: item for item in v8b_analysis.deduplication.candidates
    }
    source_indices = {candidate_id: index for index, candidate_id in enumerate(source_order)}
    if set(candidate_by_id) != set(source_order) or set(structure_by_id) != set(source_order) or set(dedup_by_id) != set(source_order):
        raise WavetableContractError("V8-A and V8-B candidate inventories disagree")

    forced_ids = frozenset(_required_candidate_ids(request))
    endpoint_ids = frozenset(_source_endpoint_ids(v8b_analysis)) if policy.preserve_source_endpoints else frozenset()
    candidate_pool = tuple(
        candidate_id
        for candidate_id in source_order
        if dedup_by_id[candidate_id].group_id
        and (not dedup_by_id[candidate_id].removable or candidate_id in forced_ids)
    )
    if not candidate_pool:
        raise WavetableContractError("V8-C candidate pool is empty")
    pool_set = frozenset(candidate_pool)
    if not forced_ids.issubset(pool_set):
        raise WavetableContractError("required candidates are absent from the V8-C pool")
    mandatory_ids = forced_ids | (endpoint_ids & pool_set)
    available_target = min(policy.maximum_keyframes, len(candidate_pool))
    if policy.requested_keyframe_count is None:
        target_count = available_target
    else:
        target_count = min(policy.requested_keyframe_count, len(candidate_pool))

    warnings = list(v8b_analysis.warnings)
    if policy.requested_keyframe_count is not None and policy.requested_keyframe_count > len(candidate_pool):
        warnings.append(
            "requested keyframe count exceeds the non-removable candidate pool; all available candidates were selected"
        )
    if len(candidate_pool) > policy.maximum_keyframes:
        warnings.append(
            f"V8-C reduced {len(candidate_pool)} non-removable candidates to the {policy.maximum_keyframes}-keyframe capacity"
        )

    group_ids = {candidate_id: dedup_by_id[candidate_id].group_id for candidate_id in source_order}
    structural_pool_ids = frozenset(
        candidate_id
        for candidate_id in candidate_pool
        if structure_by_id[candidate_id].structure_class
        in {
            CandidateStructureClass.BREAKPOINT,
            CandidateStructureClass.EXTREME,
            CandidateStructureClass.STRUCTURAL,
        }
    )

    blockers: list[str] = []
    if len(mandatory_ids) > policy.maximum_keyframes:
        blockers.append(
            f"{len(mandatory_ids)} required or endpoint candidates exceed the {policy.maximum_keyframes}-keyframe capacity"
        )
    if len(mandatory_ids) > target_count:
        blockers.append(
            f"effective target {target_count} is smaller than {len(mandatory_ids)} mandatory candidates"
        )

    exact_search_used = False
    selected_ids: tuple[str, ...] = ()
    scores: tuple[float, float, float, float, float, float] | None = None
    pair_scores: Mapping[tuple[str, str], float] = {}
    if not blockers:
        pair_scores = _pair_score_cache(candidate_pool, candidate_by_id)
        if target_count == len(candidate_pool):
            selected_ids = candidate_pool
            scores = _objective(
                selected_ids,
                candidates=candidate_by_id,
                structures=structure_by_id,
                group_ids=group_ids,
                source_indices=source_indices,
                structural_pool_ids=structural_pool_ids,
                total_group_count=v8b_analysis.distinct_wave_count,
                policy=policy,
                pair_scores=pair_scores,
            )
        else:
            optional_count = len(candidate_pool) - len(mandatory_ids)
            needed = target_count - len(mandatory_ids)
            combination_count = math.comb(optional_count, needed)
            exact_search_used = (
                len(candidate_pool) <= policy.exact_search_candidate_limit
                and combination_count <= policy.exact_search_combination_limit
            )
            if exact_search_used:
                selected_ids, scores = _select_exact(
                    candidate_pool,
                    mandatory_ids,
                    target_count,
                    candidates=candidate_by_id,
                    structures=structure_by_id,
                    group_ids=group_ids,
                    source_indices=source_indices,
                    structural_pool_ids=structural_pool_ids,
                    total_group_count=v8b_analysis.distinct_wave_count,
                    policy=policy,
                    pair_scores=pair_scores,
                )
            else:
                selected_ids, scores = _select_greedy(
                    candidate_pool,
                    mandatory_ids,
                    target_count,
                    candidates=candidate_by_id,
                    structures=structure_by_id,
                    group_ids=group_ids,
                    source_indices=source_indices,
                    structural_pool_ids=structural_pool_ids,
                    total_group_count=v8b_analysis.distinct_wave_count,
                    policy=policy,
                    pair_scores=pair_scores,
                )

    selected_set = frozenset(selected_ids)
    endpoint_selected = endpoint_ids & selected_set
    essential_set = frozenset(
        candidate_id
        for candidate_id in selected_ids
        if candidate_id in mandatory_ids
        or candidate_id in endpoint_selected
        or structure_by_id[candidate_id].structure_class
        in {CandidateStructureClass.BREAKPOINT, CandidateStructureClass.EXTREME}
    )
    if selected_ids and not essential_set:
        essential_set = frozenset({selected_ids[0]})

    selection_rank = {candidate_id: index + 1 for index, candidate_id in enumerate(selected_ids)}
    decisions: list[CandidateSelectionDecision] = []
    for candidate_id in source_order:
        structure = structure_by_id[candidate_id]
        dedup = dedup_by_id[candidate_id]
        kinds: list[SelectionEvidenceKind] = []
        evidence: list[str] = []
        if any(
            lock.candidate_id == candidate_id and lock.strength is ConstraintStrength.REQUIRED
            for lock in request.position_locks
        ):
            kinds.append(SelectionEvidenceKind.REQUIRED_LOCK)
            evidence.append("candidate is referenced by a required position lock")
        if any(
            constraint.strength is ConstraintStrength.REQUIRED
            and candidate_id in {constraint.before_candidate_id, constraint.after_candidate_id}
            for constraint in request.chronology_constraints
        ):
            kinds.append(SelectionEvidenceKind.REQUIRED_CHRONOLOGY)
            evidence.append("candidate participates in required chronology")
        if candidate_id in endpoint_ids:
            kinds.append(SelectionEvidenceKind.SOURCE_ENDPOINT)
            evidence.append("candidate represents a source-order endpoint group")
        if structure.structure_class is CandidateStructureClass.BREAKPOINT:
            kinds.append(SelectionEvidenceKind.BREAKPOINT)
            evidence.append("V8-B classified the candidate as a breakpoint")
        if structure.structure_class is CandidateStructureClass.EXTREME:
            kinds.append(SelectionEvidenceKind.FEATURE_EXTREME)
            evidence.append("V8-B classified the candidate as a feature extreme")
        if structure.structure_class is CandidateStructureClass.STRUCTURAL:
            kinds.append(SelectionEvidenceKind.STRUCTURAL)
            evidence.append("V8-B classified the candidate as structural")
        if not dedup.redundant:
            kinds.append(SelectionEvidenceKind.GROUP_REPRESENTATIVE)
            evidence.append("candidate is the complete-link group representative")
        if dedup.protected and dedup.redundant:
            kinds.append(SelectionEvidenceKind.PROTECTED_REDUNDANT)
            evidence.append("redundant candidate is protected by a required constraint")
        if candidate_id in selected_set:
            kinds.extend((SelectionEvidenceKind.UTILITY, SelectionEvidenceKind.DIVERSITY))
            evidence.append("candidate contributes deterministic utility and diversity")
            if candidate_id not in mandatory_ids:
                kinds.append(SelectionEvidenceKind.TEMPORAL_COVERAGE)
                evidence.append("candidate contributes source-order coverage")
            reason = "Candidate selected as a final V8-C keyframe without position assignment."
        elif dedup.removable:
            kinds.append(SelectionEvidenceKind.OMITTED_REDUNDANT)
            evidence.append("candidate is removable inside its complete-link group")
            reason = "Candidate omitted as an unprotected complete-link duplicate."
        else:
            kinds.append(SelectionEvidenceKind.OMITTED_CAPACITY)
            evidence.append("candidate remained outside the 61-keyframe capacity")
            reason = "Candidate omitted by deterministic capacity-limited selection."
        unique_kinds = tuple(dict.fromkeys(kinds))
        if not evidence:
            evidence.append("candidate retained for explicit V8-C decision accounting")
        decisions.append(
            CandidateSelectionDecision(
                schema_version=WAVETABLE_SELECTION_SCHEMA_VERSION,
                candidate_id=candidate_id,
                group_id=dedup.group_id,
                source_order_index=source_indices[candidate_id],
                selected=candidate_id in selected_set,
                essential=candidate_id in essential_set,
                forced=candidate_id in forced_ids and not blockers,
                source_endpoint=candidate_id in endpoint_ids,
                group_representative=not dedup.redundant,
                protected=dedup.protected,
                removable=dedup.removable,
                structure_class=structure.structure_class,
                utility_score=_candidate_utility(candidate_by_id[candidate_id], structure),
                structural_priority=_structural_priority(structure),
                selected_source_order_rank=selection_rank.get(candidate_id),
                evidence_kinds=unique_kinds,
                evidence=tuple(dict.fromkeys(evidence)),
                reason=reason,
            )
        )

    if blockers:
        status = KeyframeSelectionStatus.REJECTED
        selected_ids = ()
        essential_ids: tuple[str, ...] = ()
        forced_output: tuple[str, ...] = ()
        scores = None
        decisions = [
            CandidateSelectionDecision(
                schema_version=item.schema_version,
                candidate_id=item.candidate_id,
                group_id=item.group_id,
                source_order_index=item.source_order_index,
                selected=False,
                essential=False,
                forced=False,
                source_endpoint=item.source_endpoint,
                group_representative=item.group_representative,
                protected=item.protected,
                removable=item.removable,
                structure_class=item.structure_class,
                utility_score=item.utility_score,
                structural_priority=item.structural_priority,
                selected_source_order_rank=None,
                evidence_kinds=tuple(
                    kind
                    for kind in item.evidence_kinds
                    if kind
                    not in {
                        SelectionEvidenceKind.UTILITY,
                        SelectionEvidenceKind.DIVERSITY,
                        SelectionEvidenceKind.TEMPORAL_COVERAGE,
                    }
                ) or (SelectionEvidenceKind.OMITTED_CAPACITY,),
                evidence=item.evidence,
                reason="Selection rejected before exposing partial keyframes.",
            )
            for item in decisions
        ]
        reason = "CODE V8-C rejected the infeasible keyframe-selection request."
    else:
        status = KeyframeSelectionStatus.COMPLETE
        essential_ids = tuple(item for item in selected_ids if item in essential_set)
        forced_output = tuple(item for item in selected_ids if item in forced_ids)
        reason = (
            "CODE V8-C selected final structural keyframes in canonical source order; "
            "V8-D remains responsible for final ordering, placement, chronology solving and variants."
        )

    omitted_ids = tuple(item for item in source_order if item not in set(selected_ids))
    selection = WavetableKeyframeSelection(
        schema_version=WAVETABLE_SELECTION_SCHEMA_VERSION,
        status=status,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        policy=policy,
        available_candidate_count=len(source_order),
        candidate_pool_count=len(candidate_pool),
        target_keyframe_count=target_count,
        selected_candidate_ids=selected_ids,
        essential_candidate_ids=essential_ids,
        forced_candidate_ids=forced_output,
        omitted_candidate_ids=omitted_ids,
        decisions=tuple(decisions),
        exact_search_used=exact_search_used if status is KeyframeSelectionStatus.COMPLETE else False,
        objective_score=None if scores is None else scores[0],
        utility_score=None if scores is None else scores[1],
        diversity_score=None if scores is None else scores[2],
        temporal_coverage_score=None if scores is None else scores[3],
        structural_coverage_score=None if scores is None else scores[4],
        group_coverage_score=None if scores is None else scores[5],
        warnings=tuple(dict.fromkeys(warnings)),
        blockers=tuple(blockers),
        reason=reason,
    )
    return CodeV8CAnalysis(
        schema_version=WAVETABLE_SELECTION_SCHEMA_VERSION,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        selection=selection,
        warnings=selection.warnings,
        reason=(
            "CODE V8-C final keyframe-selection aggregate linked to immutable V8-A and V8-B evidence."
            if status is KeyframeSelectionStatus.COMPLETE
            else "CODE V8-C explicit rejection aggregate with no partial selection."
        ),
    )


__all__ = [
    "DEFAULT_KEYFRAME_SELECTION_POLICY",
    "WAVETABLE_SELECTION_SCHEMA_VERSION",
    "CandidateSelectionDecision",
    "CodeV8CAnalysis",
    "KeyframeSelectionPolicy",
    "KeyframeSelectionScore",
    "KeyframeSelectionStatus",
    "SelectionEvidenceKind",
    "WavetableKeyframeSelection",
    "evaluate_keyframe_subset",
    "select_wavetable_keyframes",
]
