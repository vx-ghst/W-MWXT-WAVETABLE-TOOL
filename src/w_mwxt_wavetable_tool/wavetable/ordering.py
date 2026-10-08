from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from itertools import permutations
import json
import math
from typing import Mapping, Sequence

from .deduplication import CodeV8BAnalysis
from .metrics import WavePairDistance, compare_wave_shapes
from .models import (
    ConstraintStrength,
    USER_POSITION_COUNT,
    WavetableBuildRequest,
    WavetableCandidate,
    WavetableContractError,
)
from .selection import CodeV8CAnalysis, KeyframeSelectionStatus
from .usefulness import CandidateStructureClass

WAVETABLE_ORDERING_SCHEMA_VERSION = 1
_ORDERING_PRECISION = 12


def _q(value: float) -> float:
    return round(float(value), _ORDERING_PRECISION)


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


def _entries(
    values: Sequence[str], *, name: str, allow_empty: bool = True
) -> tuple[str, ...]:
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


class OrderingStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


class OrderingStrategy(str, Enum):
    BALANCED = "balanced"
    SOURCE_FIDELITY = "source_fidelity"
    SCAN_SMOOTHNESS = "scan_smoothness"
    HARMONIC_DIVERSITY = "harmonic_diversity"
    BASS_STRENGTH = "bass_strength"
    DISCONTINUITY_AVOIDANCE = "discontinuity_avoidance"


class PlacementConstraintKind(str, Enum):
    POSITION_LOCK = "position_lock"
    CHRONOLOGY = "chronology"
    CAPACITY = "capacity"


class ConstraintOutcomeStatus(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class OrderingPolicy:
    schema_version: int = WAVETABLE_ORDERING_SCHEMA_VERSION
    source_fidelity_weight: float = 0.24
    scan_smoothness_weight: float = 0.30
    harmonic_diversity_weight: float = 0.14
    bass_strength_weight: float = 0.12
    discontinuity_avoidance_weight: float = 0.20
    exact_search_candidate_limit: int = 7
    exact_search_permutation_limit: int = 50000
    preserve_preference_chronology: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_ORDERING_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported ordering-policy schema version")
        weights = (
            "source_fidelity_weight",
            "scan_smoothness_weight",
            "harmonic_diversity_weight",
            "bass_strength_weight",
            "discontinuity_avoidance_weight",
        )
        for name in weights:
            _ratio(getattr(self, name), name=name)
        if abs(sum(getattr(self, name) for name in weights) - 1.0) > 1e-9:
            raise WavetableContractError("ordering objective weights must sum to one")
        for name in ("exact_search_candidate_limit", "exact_search_permutation_limit"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise WavetableContractError(f"{name} must be a positive integer")
        if not isinstance(self.preserve_preference_chronology, bool):
            raise WavetableContractError(
                "preserve_preference_chronology must be boolean"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_fidelity_weight": self.source_fidelity_weight,
            "scan_smoothness_weight": self.scan_smoothness_weight,
            "harmonic_diversity_weight": self.harmonic_diversity_weight,
            "bass_strength_weight": self.bass_strength_weight,
            "discontinuity_avoidance_weight": self.discontinuity_avoidance_weight,
            "exact_search_candidate_limit": self.exact_search_candidate_limit,
            "exact_search_permutation_limit": self.exact_search_permutation_limit,
            "preserve_preference_chronology": self.preserve_preference_chronology,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_ORDERING_POLICY = OrderingPolicy()


def ordering_policy_for_strategy(strategy: OrderingStrategy) -> OrderingPolicy:
    if not isinstance(strategy, OrderingStrategy):
        raise WavetableContractError("strategy must be OrderingStrategy")
    weights = {
        OrderingStrategy.BALANCED: (0.24, 0.30, 0.14, 0.12, 0.20),
        OrderingStrategy.SOURCE_FIDELITY: (0.56, 0.16, 0.08, 0.08, 0.12),
        OrderingStrategy.SCAN_SMOOTHNESS: (0.12, 0.52, 0.08, 0.08, 0.20),
        OrderingStrategy.HARMONIC_DIVERSITY: (0.14, 0.18, 0.44, 0.08, 0.16),
        OrderingStrategy.BASS_STRENGTH: (0.14, 0.18, 0.08, 0.44, 0.16),
        OrderingStrategy.DISCONTINUITY_AVOIDANCE: (0.12, 0.26, 0.08, 0.08, 0.46),
    }[strategy]
    return OrderingPolicy(
        source_fidelity_weight=weights[0],
        scan_smoothness_weight=weights[1],
        harmonic_diversity_weight=weights[2],
        bass_strength_weight=weights[3],
        discontinuity_avoidance_weight=weights[4],
    )


@dataclass(frozen=True, slots=True)
class ConstraintOutcome:
    schema_version: int
    constraint_id: str
    kind: PlacementConstraintKind
    strength: ConstraintStrength
    candidate_ids: tuple[str, ...]
    target_position: int | None
    status: ConstraintOutcomeStatus
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_ORDERING_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported constraint-outcome schema version")
        _normalized(self.constraint_id, name="constraint_id")
        if not isinstance(self.kind, PlacementConstraintKind):
            raise WavetableContractError("kind must be PlacementConstraintKind")
        if not isinstance(self.strength, ConstraintStrength):
            raise WavetableContractError("strength must be ConstraintStrength")
        candidate_ids = _entries(
            self.candidate_ids, name="candidate_ids", allow_empty=False
        )
        object.__setattr__(self, "candidate_ids", candidate_ids)
        expected_count = 1 if self.kind is PlacementConstraintKind.POSITION_LOCK else 2
        if self.kind is PlacementConstraintKind.CAPACITY:
            expected_count = len(candidate_ids)
        if len(candidate_ids) != expected_count:
            raise WavetableContractError("constraint candidate count is inconsistent")
        if self.target_position is not None and (
            isinstance(self.target_position, bool)
            or not isinstance(self.target_position, int)
            or not 0 <= self.target_position < USER_POSITION_COUNT
        ):
            raise WavetableContractError("target_position must be 0..60 or None")
        if self.kind is PlacementConstraintKind.POSITION_LOCK and self.target_position is None:
            raise WavetableContractError("position-lock outcome requires target_position")
        if self.kind is not PlacementConstraintKind.POSITION_LOCK and self.target_position is not None:
            raise WavetableContractError("only position-lock outcomes use target_position")
        if not isinstance(self.status, ConstraintOutcomeStatus):
            raise WavetableContractError("status must be ConstraintOutcomeStatus")
        evidence = _entries(self.evidence, name="evidence", allow_empty=False)
        object.__setattr__(self, "evidence", evidence)
        _normalized(self.reason, name="reason")
        if (
            self.strength is ConstraintStrength.REQUIRED
            and self.status is ConstraintOutcomeStatus.VIOLATED
        ):
            raise WavetableContractError(
                "required violations must be represented as blocked outcomes"
            )

    @property
    def satisfied(self) -> bool:
        return self.status is ConstraintOutcomeStatus.SATISFIED

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "constraint_id": self.constraint_id,
            "kind": self.kind.value,
            "strength": self.strength.value,
            "candidate_ids": list(self.candidate_ids),
            "target_position": self.target_position,
            "display_target_position": (
                None if self.target_position is None else self.target_position + 1
            ),
            "status": self.status.value,
            "satisfied": self.satisfied,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class OrderingScore:
    schema_version: int
    ordered_candidate_ids: tuple[str, ...]
    objective_score: float
    source_fidelity_score: float
    scan_smoothness_score: float
    harmonic_diversity_score: float
    bass_strength_score: float
    discontinuity_avoidance_score: float
    preference_chronology_score: float

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_ORDERING_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported ordering-score schema version")
        ordered = _entries(
            self.ordered_candidate_ids,
            name="ordered_candidate_ids",
            allow_empty=False,
        )
        object.__setattr__(self, "ordered_candidate_ids", ordered)
        if len(ordered) > USER_POSITION_COUNT:
            raise WavetableContractError("ordering score cannot exceed 61 candidates")
        for name in (
            "objective_score",
            "source_fidelity_score",
            "scan_smoothness_score",
            "harmonic_diversity_score",
            "bass_strength_score",
            "discontinuity_avoidance_score",
            "preference_chronology_score",
        ):
            _ratio(getattr(self, name), name=name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ordered_candidate_ids": list(self.ordered_candidate_ids),
            "objective_score": self.objective_score,
            "source_fidelity_score": self.source_fidelity_score,
            "scan_smoothness_score": self.scan_smoothness_score,
            "harmonic_diversity_score": self.harmonic_diversity_score,
            "bass_strength_score": self.bass_strength_score,
            "discontinuity_avoidance_score": self.discontinuity_avoidance_score,
            "preference_chronology_score": self.preference_chronology_score,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class OrderedCandidate:
    schema_version: int
    candidate_id: str
    order_index: int
    source_order_index: int
    essential: bool
    forced: bool
    structure_class: CandidateStructureClass
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_ORDERING_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported ordered-candidate schema version")
        _normalized(self.candidate_id, name="candidate_id")
        for name in ("order_index", "source_order_index"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise WavetableContractError(f"{name} must be non-negative")
        for name in ("essential", "forced"):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        if not isinstance(self.structure_class, CandidateStructureClass):
            raise WavetableContractError("structure_class must be CandidateStructureClass")
        evidence = _entries(self.evidence, name="evidence", allow_empty=False)
        object.__setattr__(self, "evidence", evidence)
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "order_index": self.order_index,
            "order_rank": self.order_index + 1,
            "source_order_index": self.source_order_index,
            "source_order_rank": self.source_order_index + 1,
            "essential": self.essential,
            "forced": self.forced,
            "structure_class": self.structure_class.value,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class WavetableOrdering:
    schema_version: int
    status: OrderingStatus
    request_sha256: str
    v8b_analysis_sha256: str
    v8c_analysis_sha256: str
    strategy: OrderingStrategy
    policy: OrderingPolicy
    ordered_candidate_ids: tuple[str, ...]
    entries: tuple[OrderedCandidate, ...]
    score: OrderingScore | None
    exact_search_used: bool
    constraint_outcomes: tuple[ConstraintOutcome, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_ORDERING_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported wavetable-ordering schema version")
        if not isinstance(self.status, OrderingStatus):
            raise WavetableContractError("status must be OrderingStatus")
        for name in ("request_sha256", "v8b_analysis_sha256", "v8c_analysis_sha256"):
            _sha256(getattr(self, name), name=name)
        if not isinstance(self.strategy, OrderingStrategy):
            raise WavetableContractError("strategy must be OrderingStrategy")
        if not isinstance(self.policy, OrderingPolicy):
            raise WavetableContractError("policy must be OrderingPolicy")
        ordered = _entries(self.ordered_candidate_ids, name="ordered_candidate_ids")
        entries = tuple(self.entries)
        outcomes = tuple(self.constraint_outcomes)
        warnings = _entries(self.warnings, name="warnings")
        blockers = _entries(self.blockers, name="blockers")
        object.__setattr__(self, "ordered_candidate_ids", ordered)
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "constraint_outcomes", outcomes)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "blockers", blockers)
        if any(not isinstance(item, OrderedCandidate) for item in entries):
            raise WavetableContractError("entries must contain OrderedCandidate")
        if any(not isinstance(item, ConstraintOutcome) for item in outcomes):
            raise WavetableContractError("constraint_outcomes contain invalid values")
        if not isinstance(self.exact_search_used, bool):
            raise WavetableContractError("exact_search_used must be boolean")
        _normalized(self.reason, name="reason")
        entry_ids = tuple(item.candidate_id for item in entries)
        if entry_ids != ordered:
            raise WavetableContractError("ordered entries disagree with candidate IDs")
        if tuple(item.order_index for item in entries) != tuple(range(len(entries))):
            raise WavetableContractError("ordered entries require canonical order indices")
        if self.status is OrderingStatus.COMPLETE:
            if blockers:
                raise WavetableContractError("complete ordering cannot contain blockers")
            if not ordered or self.score is None:
                raise WavetableContractError("complete ordering requires candidates and score")
            if self.score.ordered_candidate_ids != ordered:
                raise WavetableContractError("ordering score IDs disagree with ordering")
            if any(
                item.strength is ConstraintStrength.REQUIRED
                and item.status is not ConstraintOutcomeStatus.SATISFIED
                for item in outcomes
                if item.kind is PlacementConstraintKind.CHRONOLOGY
            ):
                raise WavetableContractError("complete ordering violates required chronology")
        else:
            if not blockers:
                raise WavetableContractError("rejected ordering requires blockers")
            if ordered or entries or self.score is not None:
                raise WavetableContractError("rejected ordering cannot expose partial order")
            if self.exact_search_used:
                raise WavetableContractError("rejected ordering cannot claim exact search")

    @property
    def ordered_candidate_count(self) -> int:
        return len(self.ordered_candidate_ids)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "v8b_analysis_sha256": self.v8b_analysis_sha256,
            "v8c_analysis_sha256": self.v8c_analysis_sha256,
            "strategy": self.strategy.value,
            "policy": self.policy.to_dict(),
            "ordered_candidate_count": self.ordered_candidate_count,
            "ordered_candidate_ids": list(self.ordered_candidate_ids),
            "entries": [item.to_dict() for item in self.entries],
            "score": None if self.score is None else self.score.to_dict(),
            "exact_search_used": self.exact_search_used,
            "constraint_outcomes": [item.to_dict() for item in self.constraint_outcomes],
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "orders_final_keyframes": True,
                "assigns_user_positions": False,
                "solves_required_chronology": True,
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
            self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ) + "\n"


def _validate_inputs(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
) -> None:
    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(v8b_analysis, CodeV8BAnalysis):
        raise WavetableContractError("v8b_analysis must be CodeV8BAnalysis")
    if not isinstance(v8c_analysis, CodeV8CAnalysis):
        raise WavetableContractError("v8c_analysis must be CodeV8CAnalysis")
    if v8b_analysis.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("V8-B analysis does not link to the request")
    if v8c_analysis.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("V8-C analysis does not link to the request")
    if v8c_analysis.v8b_analysis_sha256 != v8b_analysis.analysis_sha256:
        raise WavetableContractError("V8-C analysis does not link to V8-B")


def _selected_maps(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
) -> tuple[
    tuple[str, ...],
    dict[str, WavetableCandidate],
    dict[str, int],
    dict[str, CandidateStructureClass],
    frozenset[str],
    frozenset[str],
]:
    selected = v8c_analysis.selected_candidate_ids
    candidate_by_id = {item.candidate_id: item for item in request.candidates}
    source_index = {
        candidate_id: index
        for index, candidate_id in enumerate(
            v8b_analysis.structure.source_order_candidate_ids
        )
    }
    structure_class = {
        item.candidate_id: item.structure_class
        for item in v8b_analysis.structure.candidates
    }
    if any(item not in candidate_by_id for item in selected):
        raise WavetableContractError("V8-C selected an unknown candidate")
    if any(item not in source_index or item not in structure_class for item in selected):
        raise WavetableContractError("V8-B evidence is incomplete for V8-C selection")
    return (
        selected,
        candidate_by_id,
        source_index,
        structure_class,
        frozenset(v8c_analysis.essential_candidate_ids),
        frozenset(v8c_analysis.selection.forced_candidate_ids),
    )


def _required_edges(
    request: WavetableBuildRequest, selected: frozenset[str]
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (item.before_candidate_id, item.after_candidate_id)
        for item in request.chronology_constraints
        if item.strength is ConstraintStrength.REQUIRED
        and item.before_candidate_id in selected
        and item.after_candidate_id in selected
    )


def _lock_order_feasible(
    order: Sequence[str], request: WavetableBuildRequest
) -> bool:
    rank = {candidate_id: index for index, candidate_id in enumerate(order)}
    anchors = sorted(
        (
            rank[lock.candidate_id],
            lock.position,
        )
        for lock in request.position_locks
        if lock.strength is ConstraintStrength.REQUIRED
        and lock.candidate_id in rank
    )
    if not anchors:
        return True
    if any(
        left_rank >= right_rank or left_position >= right_position
        for (left_rank, left_position), (right_rank, right_position) in zip(
            anchors, anchors[1:]
        )
    ):
        return False
    first_rank, first_position = anchors[0]
    if first_rank > first_position:
        return False
    for (left_rank, left_position), (right_rank, right_position) in zip(
        anchors, anchors[1:]
    ):
        if right_rank - left_rank > right_position - left_position:
            return False
    last_rank, last_position = anchors[-1]
    if len(order) - 1 - last_rank > USER_POSITION_COUNT - 1 - last_position:
        return False
    return True


def _chronology_satisfied(
    order: Sequence[str], before: str, after: str
) -> bool:
    rank = {candidate_id: index for index, candidate_id in enumerate(order)}
    return before in rank and after in rank and rank[before] < rank[after]


def _pair_cache(
    selected: Sequence[str], candidates: Mapping[str, WavetableCandidate]
) -> dict[tuple[str, str], WavePairDistance]:
    result: dict[tuple[str, str], WavePairDistance] = {}
    for left_index, left in enumerate(selected):
        for right in selected[left_index + 1 :]:
            result[tuple(sorted((left, right)))] = compare_wave_shapes(
                candidates[left], candidates[right]
            )
    return result


def _distance(
    left: str,
    right: str,
    pair_cache: Mapping[tuple[str, str], WavePairDistance],
) -> WavePairDistance:
    return pair_cache[tuple(sorted((left, right)))]


def _source_fidelity(
    order: Sequence[str],
    source_index: Mapping[str, int],
    request: WavetableBuildRequest,
    policy: OrderingPolicy,
) -> tuple[float, float]:
    source_order = tuple(sorted(order, key=lambda item: (source_index[item], item)))
    source_rank = {candidate_id: index for index, candidate_id in enumerate(source_order)}
    n = len(order)
    if n <= 1:
        footrule_score = 1.0
    else:
        footrule = sum(abs(index - source_rank[item]) for index, item in enumerate(order))
        maximum = sum(abs(index - (n - 1 - index)) for index in range(n))
        footrule_score = 1.0 if maximum == 0 else max(0.0, 1.0 - footrule / maximum)
    preference = tuple(
        item
        for item in request.chronology_constraints
        if item.strength is ConstraintStrength.PREFERENCE
        and item.before_candidate_id in source_rank
        and item.after_candidate_id in source_rank
    )
    if not preference or not policy.preserve_preference_chronology:
        preference_score = 1.0
    else:
        preference_score = sum(
            _chronology_satisfied(
                order, item.before_candidate_id, item.after_candidate_id
            )
            for item in preference
        ) / len(preference)
    return _q(0.82 * footrule_score + 0.18 * preference_score), _q(
        preference_score
    )


def _score_order(
    order: Sequence[str],
    *,
    candidates: Mapping[str, WavetableCandidate],
    source_index: Mapping[str, int],
    structure_class: Mapping[str, CandidateStructureClass],
    request: WavetableBuildRequest,
    policy: OrderingPolicy,
    pair_cache: Mapping[tuple[str, str], WavePairDistance],
) -> OrderingScore:
    ordered = tuple(order)
    source_fidelity, preference_score = _source_fidelity(
        ordered, source_index, request, policy
    )
    if len(ordered) <= 1:
        smoothness = 1.0
        harmonic = 1.0
        discontinuity = 1.0
        bass_continuity = 1.0
    else:
        pair_distances = [
            _distance(left, right, pair_cache)
            for left, right in zip(ordered, ordered[1:])
        ]
        perceptual = [item.perceptual_distance for item in pair_distances]
        smoothness = 1.0 - sum(perceptual) / len(perceptual)
        harmonic_values = [
            0.65
            * abs(
                candidates[left].metrics.harmonic_richness
                - candidates[right].metrics.harmonic_richness
            )
            + 0.35
            * abs(
                candidates[left].metrics.brightness
                - candidates[right].metrics.brightness
            )
            for left, right in zip(ordered, ordered[1:])
        ]
        harmonic = sum(harmonic_values) / len(harmonic_values)
        bass_jumps = [
            abs(
                candidates[left].metrics.bass_power
                - candidates[right].metrics.bass_power
            )
            for left, right in zip(ordered, ordered[1:])
        ]
        bass_continuity = 1.0 - sum(bass_jumps) / len(bass_jumps)
        effective_discontinuities: list[float] = []
        for left, right, distance in zip(
            ordered, ordered[1:], perceptual
        ):
            intentional = (
                request.policy.allow_intentional_breaks
                and (
                    structure_class[left] is CandidateStructureClass.BREAKPOINT
                    or structure_class[right] is CandidateStructureClass.BREAKPOINT
                )
            )
            effective_discontinuities.append(distance * (0.35 if intentional else 1.0))
        discontinuity = 1.0 - max(effective_discontinuities)
    mean_bass = sum(candidates[item].metrics.bass_power for item in ordered) / len(
        ordered
    )
    bass_strength = 0.72 * mean_bass + 0.28 * bass_continuity
    components = (
        _q(max(0.0, min(1.0, source_fidelity))),
        _q(max(0.0, min(1.0, smoothness))),
        _q(max(0.0, min(1.0, harmonic))),
        _q(max(0.0, min(1.0, bass_strength))),
        _q(max(0.0, min(1.0, discontinuity))),
    )
    objective = _q(
        policy.source_fidelity_weight * components[0]
        + policy.scan_smoothness_weight * components[1]
        + policy.harmonic_diversity_weight * components[2]
        + policy.bass_strength_weight * components[3]
        + policy.discontinuity_avoidance_weight * components[4]
    )
    return OrderingScore(
        schema_version=WAVETABLE_ORDERING_SCHEMA_VERSION,
        ordered_candidate_ids=ordered,
        objective_score=objective,
        source_fidelity_score=components[0],
        scan_smoothness_score=components[1],
        harmonic_diversity_score=components[2],
        bass_strength_score=components[3],
        discontinuity_avoidance_score=components[4],
        preference_chronology_score=preference_score,
    )


def _required_chronology_valid(
    order: Sequence[str], request: WavetableBuildRequest
) -> bool:
    return all(
        _chronology_satisfied(order, before, after)
        for before, after in _required_edges(request, frozenset(order))
    )


def evaluate_wavetable_order(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
    ordered_candidate_ids: Sequence[str],
    policy: OrderingPolicy = DEFAULT_ORDERING_POLICY,
) -> OrderingScore:
    """Evaluate one explicit V8-D keyframe order with all public score terms."""

    _validate_inputs(request, v8b_analysis, v8c_analysis)
    if not isinstance(policy, OrderingPolicy):
        raise WavetableContractError("policy must be OrderingPolicy")
    if v8c_analysis.status is not KeyframeSelectionStatus.COMPLETE:
        raise WavetableContractError("V8-C selection must be complete")
    order = _entries(
        ordered_candidate_ids,
        name="ordered_candidate_ids",
        allow_empty=False,
    )
    selected, candidates, source_index, structure_class, _, _ = _selected_maps(
        request, v8b_analysis, v8c_analysis
    )
    if set(order) != set(selected) or len(order) != len(selected):
        raise WavetableContractError(
            "ordered_candidate_ids must be a permutation of V8-C selection"
        )
    if not _required_chronology_valid(order, request):
        raise WavetableContractError("order violates required chronology")
    if not _lock_order_feasible(order, request):
        raise WavetableContractError("order cannot satisfy required position locks")
    pair_cache = _pair_cache(selected, candidates)
    return _score_order(
        order,
        candidates=candidates,
        source_index=source_index,
        structure_class=structure_class,
        request=request,
        policy=policy,
        pair_cache=pair_cache,
    )


def _topological_greedy(
    selected: tuple[str, ...],
    *,
    candidates: Mapping[str, WavetableCandidate],
    source_index: Mapping[str, int],
    structure_class: Mapping[str, CandidateStructureClass],
    request: WavetableBuildRequest,
    policy: OrderingPolicy,
    pair_cache: Mapping[tuple[str, str], WavePairDistance],
) -> tuple[str, ...]:
    selected_set = frozenset(selected)
    predecessors: dict[str, set[str]] = {item: set() for item in selected}
    for before, after in _required_edges(request, selected_set):
        predecessors[after].add(before)
    required_locks = sorted(
        (
            lock.position,
            lock.candidate_id,
        )
        for lock in request.position_locks
        if lock.strength is ConstraintStrength.REQUIRED
        and lock.candidate_id in selected_set
    )
    for (_, left), (_, right) in zip(required_locks, required_locks[1:]):
        predecessors[right].add(left)

    preference_edges = tuple(
        (item.before_candidate_id, item.after_candidate_id)
        for item in request.chronology_constraints
        if item.strength is ConstraintStrength.PREFERENCE
        and item.before_candidate_id in selected_set
        and item.after_candidate_id in selected_set
    )
    required_lock_target = {
        lock.candidate_id: lock.position / (USER_POSITION_COUNT - 1)
        for lock in request.position_locks
        if lock.strength is ConstraintStrength.REQUIRED
        and lock.candidate_id in selected_set
    }
    preference_lock_target = {
        lock.candidate_id: lock.position / (USER_POSITION_COUNT - 1)
        for lock in request.position_locks
        if lock.strength is ConstraintStrength.PREFERENCE
        and lock.candidate_id in selected_set
    }
    source_selected = tuple(sorted(selected, key=lambda item: (source_index[item], item)))
    source_rank = {item: index for index, item in enumerate(source_selected)}
    n = len(selected)
    ordered: list[str] = []
    remaining = set(selected)
    while remaining:
        available = sorted(
            (
                item
                for item in remaining
                if predecessors[item].issubset(set(ordered))
            ),
            key=lambda item: (source_index[item], item),
        )
        if not available:
            raise WavetableContractError("required chronology produced no topological order")
        progress = 0.5 if n <= 1 else len(ordered) / (n - 1)

        def key(candidate_id: str) -> tuple[float, float, float, float, int, str]:
            source_target = 0.5 if n <= 1 else source_rank[candidate_id] / (n - 1)
            source_fit = 1.0 - abs(progress - source_target)
            if ordered:
                pair = _distance(ordered[-1], candidate_id, pair_cache)
                smooth = 1.0 - pair.perceptual_distance
                discontinuity = 1.0 - pair.perceptual_distance
                harmonic = 0.65 * abs(
                    candidates[ordered[-1]].metrics.harmonic_richness
                    - candidates[candidate_id].metrics.harmonic_richness
                ) + 0.35 * abs(
                    candidates[ordered[-1]].metrics.brightness
                    - candidates[candidate_id].metrics.brightness
                )
            else:
                smooth = 1.0
                discontinuity = 1.0
                harmonic = 0.0
            bass = candidates[candidate_id].metrics.bass_power
            lock_target = required_lock_target.get(
                candidate_id, preference_lock_target.get(candidate_id, source_target)
            )
            lock_fit = 1.0 - abs(progress - lock_target)
            preference = sum(
                before in ordered
                for before, after in preference_edges
                if after == candidate_id
            ) - sum(
                after in remaining
                for before, after in preference_edges
                if before == candidate_id
            )
            score = (
                policy.source_fidelity_weight * source_fit
                + policy.scan_smoothness_weight * smooth
                + policy.harmonic_diversity_weight * harmonic
                + policy.bass_strength_weight * bass
                + policy.discontinuity_avoidance_weight * discontinuity
                + 0.35 * lock_fit
                + 0.03 * preference
            )
            structural = {
                CandidateStructureClass.BREAKPOINT: 1.0,
                CandidateStructureClass.EXTREME: 0.9,
                CandidateStructureClass.STRUCTURAL: 0.75,
                CandidateStructureClass.TRANSITION: 0.5,
                CandidateStructureClass.STABLE: 0.3,
                CandidateStructureClass.INELIGIBLE: 0.0,
            }[structure_class[candidate_id]]
            return (
                -_q(score),
                -_q(lock_fit),
                -_q(structural),
                abs(progress - source_target),
                source_index[candidate_id],
                candidate_id,
            )

        chosen = min(available, key=key)
        ordered.append(chosen)
        remaining.remove(chosen)
    return tuple(ordered)


def _constraint_outcomes_for_order(
    request: WavetableBuildRequest,
    selected: frozenset[str],
    order: Sequence[str] | None,
    blockers: bool,
) -> tuple[ConstraintOutcome, ...]:
    outcomes: list[ConstraintOutcome] = []
    for index, constraint in enumerate(request.chronology_constraints):
        applicable = (
            constraint.before_candidate_id in selected
            and constraint.after_candidate_id in selected
        )
        if not applicable:
            status = (
                ConstraintOutcomeStatus.BLOCKED
                if constraint.strength is ConstraintStrength.REQUIRED
                else ConstraintOutcomeStatus.NOT_APPLICABLE
            )
            reason = "Chronology references a candidate outside the V8-C selection."
        elif blockers or order is None:
            status = ConstraintOutcomeStatus.BLOCKED
            reason = "Chronology could not be evaluated because ordering was rejected."
        elif _chronology_satisfied(
            order, constraint.before_candidate_id, constraint.after_candidate_id
        ):
            status = ConstraintOutcomeStatus.SATISFIED
            reason = "Chronology is satisfied by the final keyframe order."
        else:
            status = (
                ConstraintOutcomeStatus.BLOCKED
                if constraint.strength is ConstraintStrength.REQUIRED
                else ConstraintOutcomeStatus.VIOLATED
            )
            reason = "Chronology is not satisfied by this keyframe order."
        outcomes.append(
            ConstraintOutcome(
                schema_version=WAVETABLE_ORDERING_SCHEMA_VERSION,
                constraint_id=f"chronology-{index:03d}",
                kind=PlacementConstraintKind.CHRONOLOGY,
                strength=constraint.strength,
                candidate_ids=(
                    constraint.before_candidate_id,
                    constraint.after_candidate_id,
                ),
                target_position=None,
                status=status,
                evidence=(constraint.reason,),
                reason=reason,
            )
        )
    return tuple(outcomes)


def order_wavetable_keyframes(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
    strategy: OrderingStrategy = OrderingStrategy.BALANCED,
    policy: OrderingPolicy | None = None,
) -> WavetableOrdering:
    """Create one deterministic V8-D keyframe order without assigning positions."""

    _validate_inputs(request, v8b_analysis, v8c_analysis)
    if not isinstance(strategy, OrderingStrategy):
        raise WavetableContractError("strategy must be OrderingStrategy")
    effective_policy = ordering_policy_for_strategy(strategy) if policy is None else policy
    if not isinstance(effective_policy, OrderingPolicy):
        raise WavetableContractError("policy must be OrderingPolicy or None")
    selected = frozenset(v8c_analysis.selected_candidate_ids)
    blockers: list[str] = []
    warnings = list(v8c_analysis.warnings)
    if v8c_analysis.status is not KeyframeSelectionStatus.COMPLETE:
        blockers.append("V8-C selection is rejected; V8-D cannot expose a partial order")
    for lock in request.position_locks:
        if lock.strength is ConstraintStrength.REQUIRED and lock.candidate_id not in selected:
            blockers.append(
                f"required position lock candidate {lock.candidate_id} is absent from V8-C selection"
            )
    for constraint in request.chronology_constraints:
        if constraint.strength is ConstraintStrength.REQUIRED and (
            constraint.before_candidate_id not in selected
            or constraint.after_candidate_id not in selected
        ):
            blockers.append("required chronology participant is absent from V8-C selection")
    if not selected and not blockers:
        blockers.append("V8-C selection contains no keyframes")

    order: tuple[str, ...] = ()
    score: OrderingScore | None = None
    exact_search_used = False
    entries: tuple[OrderedCandidate, ...] = ()
    if not blockers:
        (
            selected_in_source_order,
            candidates,
            source_index,
            structure_class,
            essential,
            forced,
        ) = _selected_maps(request, v8b_analysis, v8c_analysis)
        pair_cache = _pair_cache(selected_in_source_order, candidates)
        permutation_count = math.factorial(len(selected_in_source_order))
        exact_search_used = (
            len(selected_in_source_order)
            <= effective_policy.exact_search_candidate_limit
            and permutation_count <= effective_policy.exact_search_permutation_limit
        )
        if exact_search_used:
            best_score: OrderingScore | None = None
            best_order: tuple[str, ...] | None = None
            for candidate_order in permutations(selected_in_source_order):
                if not _required_chronology_valid(candidate_order, request):
                    continue
                if not _lock_order_feasible(candidate_order, request):
                    continue
                candidate_score = _score_order(
                    candidate_order,
                    candidates=candidates,
                    source_index=source_index,
                    structure_class=structure_class,
                    request=request,
                    policy=effective_policy,
                    pair_cache=pair_cache,
                )
                tie = tuple((source_index[item], item) for item in candidate_order)
                best_tie = (
                    None
                    if best_order is None
                    else tuple((source_index[item], item) for item in best_order)
                )
                if (
                    best_score is None
                    or candidate_score.objective_score > best_score.objective_score
                    or (
                        candidate_score.objective_score == best_score.objective_score
                        and tie < best_tie
                    )
                ):
                    best_score = candidate_score
                    best_order = tuple(candidate_order)
            if best_order is None or best_score is None:
                blockers.append(
                    "no exact ordering can satisfy required chronology and position-lock capacity"
                )
            else:
                order, score = best_order, best_score
        else:
            try:
                candidate_order = _topological_greedy(
                    selected_in_source_order,
                    candidates=candidates,
                    source_index=source_index,
                    structure_class=structure_class,
                    request=request,
                    policy=effective_policy,
                    pair_cache=pair_cache,
                )
                if not _lock_order_feasible(candidate_order, request):
                    blockers.append(
                        "greedy ordering cannot satisfy required position-lock capacity"
                    )
                else:
                    order = candidate_order
                    score = _score_order(
                        order,
                        candidates=candidates,
                        source_index=source_index,
                        structure_class=structure_class,
                        request=request,
                        policy=effective_policy,
                        pair_cache=pair_cache,
                    )
            except WavetableContractError as exc:
                blockers.append(str(exc))
        if order:
            decision_by_id = {
                item.candidate_id: item
                for item in v8c_analysis.selection.decisions
            }
            entries = tuple(
                OrderedCandidate(
                    schema_version=WAVETABLE_ORDERING_SCHEMA_VERSION,
                    candidate_id=candidate_id,
                    order_index=index,
                    source_order_index=source_index[candidate_id],
                    essential=candidate_id in essential,
                    forced=candidate_id in forced,
                    structure_class=structure_class[candidate_id],
                    evidence=(
                        f"V8-C decision {decision_by_id[candidate_id].analysis_sha256}",
                        f"V8-B source order index {source_index[candidate_id]}",
                    ),
                    reason="Candidate is present in the deterministic V8-D order.",
                )
                for index, candidate_id in enumerate(order)
            )
    outcomes = _constraint_outcomes_for_order(
        request, selected, order if order else None, bool(blockers)
    )
    if any(
        item.strength is ConstraintStrength.REQUIRED
        and item.status is not ConstraintOutcomeStatus.SATISFIED
        for item in outcomes
    ) and not blockers:
        blockers.append("required chronology is not satisfied")
        order, entries, score = (), (), None
        exact_search_used = False
        outcomes = _constraint_outcomes_for_order(request, selected, None, True)

    status = OrderingStatus.REJECTED if blockers else OrderingStatus.COMPLETE
    reason = (
        "CODE V8-D rejected ordering before exposing a partial keyframe order."
        if blockers
        else "CODE V8-D produced a deterministic explainable keyframe order; position assignment remains a separate V8-D step."
    )
    return WavetableOrdering(
        schema_version=WAVETABLE_ORDERING_SCHEMA_VERSION,
        status=status,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        strategy=strategy,
        policy=effective_policy,
        ordered_candidate_ids=order,
        entries=entries,
        score=score,
        exact_search_used=exact_search_used if not blockers else False,
        constraint_outcomes=outcomes,
        warnings=tuple(dict.fromkeys(warnings)),
        blockers=tuple(dict.fromkeys(blockers)),
        reason=reason,
    )


__all__ = [
    "DEFAULT_ORDERING_POLICY",
    "WAVETABLE_ORDERING_SCHEMA_VERSION",
    "ConstraintOutcome",
    "ConstraintOutcomeStatus",
    "OrderedCandidate",
    "OrderingPolicy",
    "OrderingScore",
    "OrderingStatus",
    "OrderingStrategy",
    "PlacementConstraintKind",
    "WavetableOrdering",
    "evaluate_wavetable_order",
    "order_wavetable_keyframes",
    "ordering_policy_for_strategy",
]
