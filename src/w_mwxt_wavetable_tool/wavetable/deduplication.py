from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .metrics import WavePairDistance, compare_wave_shapes
from .models import ConstraintStrength, WavetableBuildRequest, WavetableCandidate, WavetableContractError
from .usefulness import (
    DEFAULT_USEFULNESS_THRESHOLDS,
    UsefulnessThresholds,
    WavetableStructureAnalysis,
    analyze_candidate_structure,
)

WAVETABLE_DEDUPLICATION_SCHEMA_VERSION = 1
_DEDUPLICATION_PRECISION = 12


def _q(value: float) -> float:
    return round(float(value), _DEDUPLICATION_PRECISION)


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


class DuplicateKind(str, Enum):
    EXACT = "exact"
    POLARITY_EQUIVALENT = "polarity_equivalent"
    NEAR = "near"
    DISTINCT = "distinct"


@dataclass(frozen=True, slots=True)
class DeduplicationThresholds:
    schema_version: int = WAVETABLE_DEDUPLICATION_SCHEMA_VERSION
    near_perceptual_distance: float = 0.065
    near_spectral_distance: float = 0.090
    near_feature_distance: float = 0.090
    minimum_absolute_correlation: float = 0.930
    polarity_perceptual_distance: float = 0.015

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_DEDUPLICATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported deduplication-threshold schema version")
        for name in (
            "near_perceptual_distance",
            "near_spectral_distance",
            "near_feature_distance",
            "minimum_absolute_correlation",
            "polarity_perceptual_distance",
        ):
            _ratio(getattr(self, name), name=name)
        if self.polarity_perceptual_distance > self.near_perceptual_distance:
            raise WavetableContractError(
                "polarity_perceptual_distance must not exceed near_perceptual_distance"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "near_perceptual_distance": self.near_perceptual_distance,
            "near_spectral_distance": self.near_spectral_distance,
            "near_feature_distance": self.near_feature_distance,
            "minimum_absolute_correlation": self.minimum_absolute_correlation,
            "polarity_perceptual_distance": self.polarity_perceptual_distance,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_DEDUPLICATION_THRESHOLDS = DeduplicationThresholds()


@dataclass(frozen=True, slots=True)
class DuplicatePairAnalysis:
    schema_version: int
    left_candidate_id: str
    right_candidate_id: str
    duplicate_kind: DuplicateKind
    distance: WavePairDistance
    protected_pair: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_DEDUPLICATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported duplicate-pair schema version")
        _normalized(self.left_candidate_id, name="left_candidate_id")
        _normalized(self.right_candidate_id, name="right_candidate_id")
        if self.left_candidate_id == self.right_candidate_id:
            raise WavetableContractError("duplicate pair must contain distinct candidates")
        if not isinstance(self.duplicate_kind, DuplicateKind):
            raise WavetableContractError("duplicate_kind must be DuplicateKind")
        if not isinstance(self.distance, WavePairDistance):
            raise WavetableContractError("distance must be WavePairDistance")
        if not isinstance(self.protected_pair, bool):
            raise WavetableContractError("protected_pair must be boolean")
        if self.duplicate_kind is DuplicateKind.EXACT and not self.distance.exact_match:
            raise WavetableContractError("exact duplicate kind requires exact_match")
        if self.duplicate_kind is DuplicateKind.POLARITY_EQUIVALENT and not self.distance.polarity_equivalent:
            raise WavetableContractError(
                "polarity-equivalent kind requires polarity_equivalent distance"
            )
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "left_candidate_id": self.left_candidate_id,
            "right_candidate_id": self.right_candidate_id,
            "duplicate_kind": self.duplicate_kind.value,
            "distance": self.distance.to_dict(),
            "protected_pair": self.protected_pair,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class DuplicateGroupAnalysis:
    schema_version: int
    group_id: str
    representative_candidate_id: str
    member_candidate_ids: tuple[str, ...]
    redundant_candidate_ids: tuple[str, ...]
    protected_candidate_ids: tuple[str, ...]
    removable_candidate_ids: tuple[str, ...]
    strongest_duplicate_kind: DuplicateKind
    maximum_perceptual_distance: float
    source_time_span_seconds: float | None
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_DEDUPLICATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported duplicate-group schema version")
        _normalized(self.group_id, name="group_id")
        _normalized(self.representative_candidate_id, name="representative_candidate_id")
        members = _entries(self.member_candidate_ids, name="member_candidate_ids", allow_empty=False)
        redundant = _entries(self.redundant_candidate_ids, name="redundant_candidate_ids")
        protected = _entries(self.protected_candidate_ids, name="protected_candidate_ids")
        removable = _entries(self.removable_candidate_ids, name="removable_candidate_ids")
        object.__setattr__(self, "member_candidate_ids", members)
        object.__setattr__(self, "redundant_candidate_ids", redundant)
        object.__setattr__(self, "protected_candidate_ids", protected)
        object.__setattr__(self, "removable_candidate_ids", removable)
        member_set = set(members)
        if self.representative_candidate_id not in member_set:
            raise WavetableContractError("representative must belong to the group")
        if set(redundant) != member_set - {self.representative_candidate_id}:
            raise WavetableContractError("redundant members must be every non-representative member")
        if not set(protected).issubset(member_set):
            raise WavetableContractError("protected members must belong to the group")
        if set(removable) != set(redundant) - set(protected):
            raise WavetableContractError("removable members must be redundant and unprotected")
        if not isinstance(self.strongest_duplicate_kind, DuplicateKind):
            raise WavetableContractError("strongest_duplicate_kind must be DuplicateKind")
        if len(members) == 1 and self.strongest_duplicate_kind is not DuplicateKind.DISTINCT:
            raise WavetableContractError("singleton groups must be distinct")
        if len(members) > 1 and self.strongest_duplicate_kind is DuplicateKind.DISTINCT:
            raise WavetableContractError("duplicate groups cannot be distinct")
        _ratio(self.maximum_perceptual_distance, name="maximum_perceptual_distance")
        if self.source_time_span_seconds is not None and (
            not math.isfinite(float(self.source_time_span_seconds))
            or self.source_time_span_seconds < 0.0
        ):
            raise WavetableContractError("source_time_span_seconds must be non-negative")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "group_id": self.group_id,
            "representative_candidate_id": self.representative_candidate_id,
            "member_candidate_ids": list(self.member_candidate_ids),
            "redundant_candidate_ids": list(self.redundant_candidate_ids),
            "protected_candidate_ids": list(self.protected_candidate_ids),
            "removable_candidate_ids": list(self.removable_candidate_ids),
            "strongest_duplicate_kind": self.strongest_duplicate_kind.value,
            "maximum_perceptual_distance": self.maximum_perceptual_distance,
            "source_time_span_seconds": self.source_time_span_seconds,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class CandidateDeduplicationAnalysis:
    schema_version: int
    candidate_id: str
    group_id: str
    representative_candidate_id: str
    duplicate_kind: DuplicateKind
    redundant: bool
    protected: bool
    removable: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_DEDUPLICATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported candidate-deduplication schema version")
        for name in ("candidate_id", "group_id", "representative_candidate_id"):
            _normalized(getattr(self, name), name=name)
        if not isinstance(self.duplicate_kind, DuplicateKind):
            raise WavetableContractError("duplicate_kind must be DuplicateKind")
        for name in ("redundant", "protected", "removable"):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        if self.removable and (not self.redundant or self.protected):
            raise WavetableContractError("removable requires redundant and unprotected")
        if not self.redundant and self.candidate_id != self.representative_candidate_id:
            raise WavetableContractError("non-redundant candidate must be the representative")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "group_id": self.group_id,
            "representative_candidate_id": self.representative_candidate_id,
            "duplicate_kind": self.duplicate_kind.value,
            "redundant": self.redundant,
            "protected": self.protected,
            "removable": self.removable,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class WavetableDeduplicationAnalysis:
    schema_version: int
    request_sha256: str
    structure_analysis_sha256: str
    thresholds: DeduplicationThresholds
    groups: tuple[DuplicateGroupAnalysis, ...]
    candidates: tuple[CandidateDeduplicationAnalysis, ...]
    duplicate_pairs: tuple[DuplicatePairAnalysis, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_DEDUPLICATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported deduplication-analysis schema version")
        for name in ("request_sha256", "structure_analysis_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
        if not isinstance(self.thresholds, DeduplicationThresholds):
            raise WavetableContractError("thresholds must be DeduplicationThresholds")
        groups = tuple(self.groups)
        candidates = tuple(self.candidates)
        pairs = tuple(self.duplicate_pairs)
        warnings = _entries(self.warnings, name="warnings")
        object.__setattr__(self, "groups", groups)
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "duplicate_pairs", pairs)
        object.__setattr__(self, "warnings", warnings)
        if not groups or not candidates:
            raise WavetableContractError("deduplication analysis requires groups and candidates")
        if any(not isinstance(item, DuplicateGroupAnalysis) for item in groups):
            raise WavetableContractError("groups must contain DuplicateGroupAnalysis")
        if any(not isinstance(item, CandidateDeduplicationAnalysis) for item in candidates):
            raise WavetableContractError("candidates must contain CandidateDeduplicationAnalysis")
        if any(not isinstance(item, DuplicatePairAnalysis) for item in pairs):
            raise WavetableContractError("duplicate_pairs must contain DuplicatePairAnalysis")
        member_ids = tuple(candidate_id for group in groups for candidate_id in group.member_candidate_ids)
        candidate_ids = tuple(item.candidate_id for item in candidates)
        if len(set(member_ids)) != len(member_ids) or set(member_ids) != set(candidate_ids):
            raise WavetableContractError("groups must partition the candidate inventory")
        if len({group.group_id for group in groups}) != len(groups):
            raise WavetableContractError("group IDs must be unique")
        _normalized(self.reason, name="reason")

    @property
    def distinct_wave_count(self) -> int:
        return len(self.groups)

    @property
    def redundant_candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_id for item in self.candidates if item.redundant)

    @property
    def protected_redundant_candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            item.candidate_id
            for item in self.candidates
            if item.redundant and item.protected
        )

    @property
    def removable_candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_id for item in self.candidates if item.removable)

    @property
    def representative_candidate_ids(self) -> tuple[str, ...]:
        return tuple(group.representative_candidate_id for group in self.groups)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request_sha256,
            "structure_analysis_sha256": self.structure_analysis_sha256,
            "thresholds": self.thresholds.to_dict(),
            "groups": [item.to_dict() for item in self.groups],
            "candidates": [item.to_dict() for item in self.candidates],
            "duplicate_pairs": [item.to_dict() for item in self.duplicate_pairs],
            "distinct_wave_count": self.distinct_wave_count,
            "representative_candidate_ids": list(self.representative_candidate_ids),
            "redundant_candidate_ids": list(self.redundant_candidate_ids),
            "protected_redundant_candidate_ids": list(self.protected_redundant_candidate_ids),
            "removable_candidate_ids": list(self.removable_candidate_ids),
            "warnings": list(self.warnings),
            "reason": self.reason,
            "boundaries": {
                "removes_candidates": False,
                "selects_keyframes": False,
                "assigns_user_positions": False,
                "orders_final_table": False,
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
class CodeV8BAnalysis:
    schema_version: int
    request_sha256: str
    structure: WavetableStructureAnalysis
    deduplication: WavetableDeduplicationAnalysis
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_DEDUPLICATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-B schema version")
        if not isinstance(self.request_sha256, str) or len(self.request_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.request_sha256
        ):
            raise WavetableContractError("request_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.structure, WavetableStructureAnalysis):
            raise WavetableContractError("structure must be WavetableStructureAnalysis")
        if not isinstance(self.deduplication, WavetableDeduplicationAnalysis):
            raise WavetableContractError("deduplication must be WavetableDeduplicationAnalysis")
        if self.structure.request_sha256 != self.request_sha256:
            raise WavetableContractError("structure analysis does not link to the request")
        if self.deduplication.request_sha256 != self.request_sha256:
            raise WavetableContractError("deduplication analysis does not link to the request")
        if self.deduplication.structure_analysis_sha256 != self.structure.analysis_sha256:
            raise WavetableContractError("deduplication analysis does not link to structure analysis")
        warnings = _entries(self.warnings, name="warnings")
        object.__setattr__(self, "warnings", warnings)
        _normalized(self.reason, name="reason")

    @property
    def distinct_wave_count(self) -> int:
        return self.deduplication.distinct_wave_count

    @property
    def structural_candidate_ids(self) -> tuple[str, ...]:
        return self.structure.structural_candidate_ids

    @property
    def breakpoint_candidate_ids(self) -> tuple[str, ...]:
        return self.structure.breakpoint_candidate_ids

    @property
    def transition_candidate_ids(self) -> tuple[str, ...]:
        return self.structure.transition_candidate_ids

    @property
    def redundant_candidate_ids(self) -> tuple[str, ...]:
        return self.deduplication.redundant_candidate_ids

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request_sha256,
            "structure": self.structure.to_dict(),
            "deduplication": self.deduplication.to_dict(),
            "distinct_wave_count": self.distinct_wave_count,
            "structural_candidate_ids": list(self.structural_candidate_ids),
            "breakpoint_candidate_ids": list(self.breakpoint_candidate_ids),
            "transition_candidate_ids": list(self.transition_candidate_ids),
            "redundant_candidate_ids": list(self.redundant_candidate_ids),
            "warnings": list(self.warnings),
            "reason": self.reason,
            "boundaries": {
                "selects_final_keyframes": False,
                "builds_61_position_table": False,
                "orders_final_table": False,
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


def _protected_candidate_ids(request: WavetableBuildRequest) -> frozenset[str]:
    protected = {
        lock.candidate_id
        for lock in request.position_locks
        if lock.strength is ConstraintStrength.REQUIRED
    }
    for constraint in request.chronology_constraints:
        if constraint.strength is ConstraintStrength.REQUIRED:
            protected.add(constraint.before_candidate_id)
            protected.add(constraint.after_candidate_id)
    return frozenset(protected)


def _duplicate_kind(
    distance: WavePairDistance,
    thresholds: DeduplicationThresholds,
) -> DuplicateKind:
    if distance.exact_match:
        return DuplicateKind.EXACT
    if distance.polarity_equivalent and distance.perceptual_distance <= thresholds.polarity_perceptual_distance:
        return DuplicateKind.POLARITY_EQUIVALENT
    if (
        distance.perceptual_distance <= thresholds.near_perceptual_distance
        and distance.spectral_distance <= thresholds.near_spectral_distance
        and distance.feature_distance <= thresholds.near_feature_distance
        and distance.absolute_correlation >= thresholds.minimum_absolute_correlation
    ):
        return DuplicateKind.NEAR
    return DuplicateKind.DISTINCT


def _kind_strength(kind: DuplicateKind) -> int:
    return {
        DuplicateKind.EXACT: 3,
        DuplicateKind.POLARITY_EQUIVALENT: 2,
        DuplicateKind.NEAR: 1,
        DuplicateKind.DISTINCT: 0,
    }[kind]


def _candidate_rank(
    candidate: WavetableCandidate,
    structure: WavetableStructureAnalysis,
    protected: frozenset[str],
) -> tuple[object, ...]:
    entry = next(item for item in structure.candidates if item.candidate_id == candidate.candidate_id)
    return (
        candidate.candidate_id not in protected,
        -entry.structural_score,
        -entry.effective_usefulness_score,
        -candidate.metrics.quality_score,
        -candidate.metrics.source_fidelity,
        -candidate.metrics.xt_compatibility,
        entry.source_order_index,
        candidate.candidate_id,
    )


def analyze_candidate_deduplication(
    request: WavetableBuildRequest,
    structure: WavetableStructureAnalysis,
    thresholds: DeduplicationThresholds = DEFAULT_DEDUPLICATION_THRESHOLDS,
) -> WavetableDeduplicationAnalysis:
    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(structure, WavetableStructureAnalysis):
        raise WavetableContractError("structure must be WavetableStructureAnalysis")
    if structure.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("structure analysis does not link to request")
    if not isinstance(thresholds, DeduplicationThresholds):
        raise WavetableContractError("thresholds must be DeduplicationThresholds")

    by_id = {candidate.candidate_id: candidate for candidate in request.candidates}
    source_order = structure.source_order_candidate_ids
    protected = _protected_candidate_ids(request)
    distance_cache: dict[tuple[str, str], WavePairDistance] = {}
    kind_cache: dict[tuple[str, str], DuplicateKind] = {}
    duplicate_pairs: list[DuplicatePairAnalysis] = []

    def pair_key(left_id: str, right_id: str) -> tuple[str, str]:
        return tuple(sorted((left_id, right_id)))  # type: ignore[return-value]

    def pair_distance(left_id: str, right_id: str) -> WavePairDistance:
        key = pair_key(left_id, right_id)
        if key not in distance_cache:
            distance_cache[key] = compare_wave_shapes(by_id[key[0]], by_id[key[1]])
            kind_cache[key] = _duplicate_kind(distance_cache[key], thresholds)
        return distance_cache[key]

    for left_index, left_id in enumerate(source_order):
        for right_id in source_order[left_index + 1 :]:
            distance = pair_distance(left_id, right_id)
            kind = kind_cache[pair_key(left_id, right_id)]
            if kind is DuplicateKind.DISTINCT:
                continue
            duplicate_pairs.append(
                DuplicatePairAnalysis(
                    schema_version=WAVETABLE_DEDUPLICATION_SCHEMA_VERSION,
                    left_candidate_id=left_id,
                    right_candidate_id=right_id,
                    duplicate_kind=kind,
                    distance=distance,
                    protected_pair=left_id in protected or right_id in protected,
                    reason=(
                        "Candidate pair is acoustically redundant but remains analysis-only; V8-C controls final retention."
                    ),
                )
            )

    groups_members: list[list[str]] = []
    for candidate_id in source_order:
        placed = False
        for members in groups_members:
            if all(
                kind_cache.get(pair_key(candidate_id, member), DuplicateKind.DISTINCT)
                is not DuplicateKind.DISTINCT
                for member in members
            ):
                members.append(candidate_id)
                placed = True
                break
        if not placed:
            groups_members.append([candidate_id])

    groups: list[DuplicateGroupAnalysis] = []
    candidate_analyses: list[CandidateDeduplicationAnalysis] = []
    for group_index, members_list in enumerate(groups_members, start=1):
        members = tuple(members_list)
        representative = min(
            (by_id[candidate_id] for candidate_id in members),
            key=lambda candidate: _candidate_rank(candidate, structure, protected),
        ).candidate_id
        redundant = tuple(candidate_id for candidate_id in members if candidate_id != representative)
        protected_members = tuple(candidate_id for candidate_id in members if candidate_id in protected)
        removable = tuple(candidate_id for candidate_id in redundant if candidate_id not in protected)
        pair_kinds: list[DuplicateKind] = []
        pair_distances: list[float] = []
        for left_index, left_id in enumerate(members):
            for right_id in members[left_index + 1 :]:
                key = pair_key(left_id, right_id)
                pair_kinds.append(kind_cache[key])
                pair_distances.append(distance_cache[key].perceptual_distance)
        strongest = (
            max(pair_kinds, key=_kind_strength)
            if pair_kinds
            else DuplicateKind.DISTINCT
        )
        times = [by_id[candidate_id].source_time_seconds for candidate_id in members]
        available_times = [value for value in times if value is not None]
        time_span = (
            _q(max(available_times) - min(available_times))
            if len(available_times) >= 2
            else None
        )
        group_id = f"duplicate-group-{group_index:04d}"
        groups.append(
            DuplicateGroupAnalysis(
                schema_version=WAVETABLE_DEDUPLICATION_SCHEMA_VERSION,
                group_id=group_id,
                representative_candidate_id=representative,
                member_candidate_ids=members,
                redundant_candidate_ids=redundant,
                protected_candidate_ids=protected_members,
                removable_candidate_ids=removable,
                strongest_duplicate_kind=strongest,
                maximum_perceptual_distance=_q(max(pair_distances, default=0.0)),
                source_time_span_seconds=time_span,
                reason=(
                    "Complete-link deterministic group; no transitive near-duplicate chaining is allowed."
                ),
            )
        )
        for candidate_id in members:
            if candidate_id == representative:
                kind = DuplicateKind.DISTINCT
                reason = "Canonical analysis representative; final V8-C selection remains deferred."
            else:
                kind = kind_cache[pair_key(candidate_id, representative)]
                reason = (
                    "Redundant candidate is protected by a required constraint."
                    if candidate_id in protected
                    else "Redundant candidate may be omitted by V8-C after explicit selection logic."
                )
            candidate_analyses.append(
                CandidateDeduplicationAnalysis(
                    schema_version=WAVETABLE_DEDUPLICATION_SCHEMA_VERSION,
                    candidate_id=candidate_id,
                    group_id=group_id,
                    representative_candidate_id=representative,
                    duplicate_kind=kind,
                    redundant=candidate_id != representative,
                    protected=candidate_id in protected,
                    removable=candidate_id != representative and candidate_id not in protected,
                    reason=reason,
                )
            )

    candidate_order = {candidate_id: index for index, candidate_id in enumerate(source_order)}
    candidate_analyses.sort(key=lambda item: candidate_order[item.candidate_id])
    warnings: list[str] = []
    protected_redundant = [
        item.candidate_id for item in candidate_analyses if item.redundant and item.protected
    ]
    if protected_redundant:
        warnings.append(
            "Required constraints protect acoustically redundant candidates: "
            + ", ".join(protected_redundant)
        )
    if len(groups) > 61:
        warnings.append(
            "Distinct-wave count exceeds 61; V8-C must select structural keyframes."
        )

    return WavetableDeduplicationAnalysis(
        schema_version=WAVETABLE_DEDUPLICATION_SCHEMA_VERSION,
        request_sha256=request.analysis_sha256,
        structure_analysis_sha256=structure.analysis_sha256,
        thresholds=thresholds,
        groups=tuple(groups),
        candidates=tuple(candidate_analyses),
        duplicate_pairs=tuple(duplicate_pairs),
        warnings=tuple(warnings),
        reason=(
            "Measured exact, polarity-equivalent and near redundancy using complete-link groups without deleting or selecting candidates."
        ),
    )


def analyze_wavetable_candidates(
    request: WavetableBuildRequest,
    *,
    usefulness_thresholds: UsefulnessThresholds = DEFAULT_USEFULNESS_THRESHOLDS,
    deduplication_thresholds: DeduplicationThresholds = DEFAULT_DEDUPLICATION_THRESHOLDS,
) -> CodeV8BAnalysis:
    structure = analyze_candidate_structure(request, usefulness_thresholds)
    deduplication = analyze_candidate_deduplication(
        request,
        structure,
        deduplication_thresholds,
    )
    warnings = tuple(dict.fromkeys(structure.warnings + deduplication.warnings))
    return CodeV8BAnalysis(
        schema_version=WAVETABLE_DEDUPLICATION_SCHEMA_VERSION,
        request_sha256=request.analysis_sha256,
        structure=structure,
        deduplication=deduplication,
        warnings=warnings,
        reason=(
            "CODE V8-B classifies usefulness, stable regions, transitions, breakpoints, structure and redundancy while deferring final keyframe selection to V8-C."
        ),
    )
