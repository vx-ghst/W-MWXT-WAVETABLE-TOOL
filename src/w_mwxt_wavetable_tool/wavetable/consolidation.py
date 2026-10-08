from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .metrics import WavePairDistance, compare_wave_shapes
from .models import (
    USER_POSITION_COUNT,
    WAVETABLE_BUILD_SCHEMA_VERSION,
    GenerationMethod,
    WaveBuildMetrics,
    WaveOrigin,
    WaveRole,
    WavetableBuild,
    WavetableBuildStatus,
    WavetableContractError,
    WavetableSlot,
    stored_samples_sha256,
)

WAVETABLE_CONSOLIDATION_SCHEMA_VERSION = 1
_PRECISION = 12


def _q(value: float) -> float:
    return round(float(value), _PRECISION)


def _canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


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


def _strings(values: Sequence[str], *, name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence of strings")
    result = tuple(values)
    if not allow_empty and not result:
        raise WavetableContractError(f"{name} must not be empty")
    if any(not isinstance(item, str) or not item or item.strip() != item for item in result):
        raise WavetableContractError(f"{name} must contain normalized strings")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


class ConsolidationStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


class ConsolidationMatchKind(str, Enum):
    EXACT = "exact"
    NEAR = "near"
    POLARITY_EQUIVALENT = "polarity_equivalent"
    DISTINCT = "distinct"


class FinalSlotClass(str, Enum):
    STRUCTURAL = "structural"
    TRANSITION = "transition"
    REDUNDANT = "redundant"


@dataclass(frozen=True, slots=True)
class ConsolidationPolicy:
    schema_version: int = WAVETABLE_CONSOLIDATION_SCHEMA_VERSION
    allow_near_duplicates: bool = False
    near_perceptual_distance: float = 0.020
    near_spectral_distance: float = 0.025
    near_feature_distance: float = 0.025
    near_maximum_sample_distance: float = 0.040
    minimum_absolute_correlation: float = 0.990
    maximum_usefulness_delta: float = 0.025
    maximum_continuity_degradation: float = 0.010
    merge_polarity_equivalent: bool = False
    protect_locked: bool = True
    protect_essential: bool = True
    protect_breakpoint: bool = True
    protect_structural: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported consolidation policy schema version")
        for name in (
            "allow_near_duplicates",
            "merge_polarity_equivalent",
            "protect_locked",
            "protect_essential",
            "protect_breakpoint",
            "protect_structural",
        ):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        for name in (
            "near_perceptual_distance",
            "near_spectral_distance",
            "near_feature_distance",
            "near_maximum_sample_distance",
            "minimum_absolute_correlation",
            "maximum_usefulness_delta",
            "maximum_continuity_degradation",
        ):
            _ratio(getattr(self, name), name=name)
        if self.near_perceptual_distance > 0.10:
            raise WavetableContractError("near_perceptual_distance is too permissive")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "allow_near_duplicates": self.allow_near_duplicates,
            "near_perceptual_distance": self.near_perceptual_distance,
            "near_spectral_distance": self.near_spectral_distance,
            "near_feature_distance": self.near_feature_distance,
            "near_maximum_sample_distance": self.near_maximum_sample_distance,
            "minimum_absolute_correlation": self.minimum_absolute_correlation,
            "maximum_usefulness_delta": self.maximum_usefulness_delta,
            "maximum_continuity_degradation": self.maximum_continuity_degradation,
            "merge_polarity_equivalent": self.merge_polarity_equivalent,
            "protect_locked": self.protect_locked,
            "protect_essential": self.protect_essential,
            "protect_breakpoint": self.protect_breakpoint,
            "protect_structural": self.protect_structural,
            "polarity_equivalence_default": "diagnostic_only",
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_CONSOLIDATION_POLICY = ConsolidationPolicy()


@dataclass(frozen=True, slots=True)
class LogicalWavetable61:
    schema_version: int
    source_build_sha256: str
    slots: tuple[WavetableSlot, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported logical wavetable schema version")
        _sha256(self.source_build_sha256, name="source_build_sha256")
        slots = tuple(self.slots)
        object.__setattr__(self, "slots", slots)
        if len(slots) != USER_POSITION_COUNT:
            raise WavetableContractError("Logical wavetable must contain exactly 61 slots")
        if any(not isinstance(item, WavetableSlot) for item in slots):
            raise WavetableContractError("Logical wavetable slots must be WavetableSlot values")
        if tuple(item.position for item in slots) != tuple(range(USER_POSITION_COUNT)):
            raise WavetableContractError("Logical wavetable positions must be canonical 0..60")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_build_sha256": self.source_build_sha256,
            "slots": [item.to_dict() for item in self.slots],
            "logical_position_count": USER_POSITION_COUNT,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class PhysicalWaveMetricsSummary:
    schema_version: int
    minimum: WaveBuildMetrics
    maximum: WaveBuildMetrics
    mean: WaveBuildMetrics

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported physical metrics summary schema version")
        for name in ("minimum", "maximum", "mean"):
            if not isinstance(getattr(self, name), WaveBuildMetrics):
                raise WavetableContractError(f"{name} must be WaveBuildMetrics")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "minimum": self.minimum.to_dict(),
            "maximum": self.maximum.to_dict(),
            "mean": self.mean.to_dict(),
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class PhysicalWave:
    schema_version: int
    physical_index: int
    wave_id: str
    representative_position: int
    stored_samples: tuple[int, ...]
    logical_positions: tuple[int, ...]
    logical_slot_sha256s: tuple[str, ...]
    source_candidate_ids: tuple[str, ...]
    origins: tuple[WaveOrigin, ...]
    generation_methods: tuple[GenerationMethod, ...]
    roles: tuple[WaveRole, ...]
    metrics_summary: PhysicalWaveMetricsSummary
    exact_group: bool
    near_group: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported physical wave schema version")
        if isinstance(self.physical_index, bool) or not isinstance(self.physical_index, int) or self.physical_index < 0:
            raise WavetableContractError("physical_index must be a non-negative integer")
        if not isinstance(self.wave_id, str) or not self.wave_id:
            raise WavetableContractError("wave_id must not be empty")
        if isinstance(self.representative_position, bool) or not isinstance(self.representative_position, int) or not 0 <= self.representative_position < USER_POSITION_COUNT:
            raise WavetableContractError("representative_position must be in 0..60")
        samples = tuple(self.stored_samples)
        stored_samples_sha256(samples)
        object.__setattr__(self, "stored_samples", samples)
        positions = tuple(self.logical_positions)
        object.__setattr__(self, "logical_positions", positions)
        if not positions or tuple(sorted(set(positions))) != positions:
            raise WavetableContractError("logical_positions must be sorted, unique and non-empty")
        if self.representative_position not in positions:
            raise WavetableContractError("representative_position must belong to logical_positions")
        hashes = tuple(self.logical_slot_sha256s)
        object.__setattr__(self, "logical_slot_sha256s", hashes)
        if len(hashes) != len(positions):
            raise WavetableContractError("logical_slot_sha256s must align with logical_positions")
        for value in hashes:
            _sha256(value, name="logical_slot_sha256")
        object.__setattr__(self, "source_candidate_ids", _strings(self.source_candidate_ids, name="source_candidate_ids", allow_empty=False))
        origins = tuple(self.origins)
        methods = tuple(self.generation_methods)
        roles = tuple(self.roles)
        object.__setattr__(self, "origins", origins)
        object.__setattr__(self, "generation_methods", methods)
        object.__setattr__(self, "roles", roles)
        if not origins or any(not isinstance(item, WaveOrigin) for item in origins):
            raise WavetableContractError("origins must contain WaveOrigin values")
        if not methods or any(not isinstance(item, GenerationMethod) for item in methods):
            raise WavetableContractError("generation_methods must contain GenerationMethod values")
        if not roles or any(not isinstance(item, WaveRole) for item in roles):
            raise WavetableContractError("roles must contain WaveRole values")
        if not isinstance(self.metrics_summary, PhysicalWaveMetricsSummary):
            raise WavetableContractError("metrics_summary must be PhysicalWaveMetricsSummary")
        if not isinstance(self.exact_group, bool) or not isinstance(self.near_group, bool):
            raise WavetableContractError("group flags must be boolean")
        if self.exact_group and self.near_group:
            raise WavetableContractError("physical wave cannot be both exact and near group")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def stored_samples_sha256(self) -> str:
        return stored_samples_sha256(self.stored_samples)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "physical_index": self.physical_index,
            "wave_id": self.wave_id,
            "representative_position": self.representative_position,
            "display_representative_position": self.representative_position + 1,
            "stored_samples": list(self.stored_samples),
            "stored_samples_sha256": self.stored_samples_sha256,
            "logical_positions": list(self.logical_positions),
            "display_logical_positions": [item + 1 for item in self.logical_positions],
            "logical_slot_sha256s": list(self.logical_slot_sha256s),
            "source_candidate_ids": list(self.source_candidate_ids),
            "origins": [item.value for item in self.origins],
            "generation_methods": [item.value for item in self.generation_methods],
            "roles": [item.value for item in self.roles],
            "metrics_summary": self.metrics_summary.to_dict(),
            "exact_group": self.exact_group,
            "near_group": self.near_group,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class PhysicalWaveSet:
    schema_version: int
    waves: tuple[PhysicalWave, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported physical wave set schema version")
        waves = tuple(self.waves)
        object.__setattr__(self, "waves", waves)
        if not 1 <= len(waves) <= USER_POSITION_COUNT:
            raise WavetableContractError("Physical wave set size must be in 1..61")
        if any(not isinstance(item, PhysicalWave) for item in waves):
            raise WavetableContractError("waves must contain PhysicalWave values")
        if tuple(item.physical_index for item in waves) != tuple(range(len(waves))):
            raise WavetableContractError("physical wave indices must be canonical")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def physical_wave_count(self) -> int:
        return len(self.waves)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "physical_wave_count": self.physical_wave_count,
            "waves": [item.to_dict() for item in self.waves],
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class LogicalToPhysicalMapping:
    schema_version: int
    logical_to_physical: tuple[int, ...]
    physical_to_logical: tuple[tuple[int, ...], ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported logical-to-physical mapping schema version")
        forward = tuple(self.logical_to_physical)
        reverse = tuple(tuple(group) for group in self.physical_to_logical)
        object.__setattr__(self, "logical_to_physical", forward)
        object.__setattr__(self, "physical_to_logical", reverse)
        if len(forward) != USER_POSITION_COUNT:
            raise WavetableContractError("logical_to_physical must contain exactly 61 entries")
        if not reverse or len(reverse) > USER_POSITION_COUNT:
            raise WavetableContractError("physical_to_logical must contain 1..61 groups")
        if any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item < len(reverse) for item in forward):
            raise WavetableContractError("logical_to_physical contains invalid physical indices")
        expected = []
        for physical_index, group in enumerate(reverse):
            if not group or tuple(sorted(set(group))) != group:
                raise WavetableContractError("physical_to_logical groups must be sorted, unique and non-empty")
            expected.extend(group)
            if any(forward[position] != physical_index for position in group):
                raise WavetableContractError("forward and reverse mappings disagree")
        if sorted(expected) != list(range(USER_POSITION_COUNT)):
            raise WavetableContractError("reverse mapping must cover every logical position exactly once")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def physical_wave_count(self) -> int:
        return len(self.physical_to_logical)

    def physical_index_for(self, logical_position: int) -> int:
        if isinstance(logical_position, bool) or not isinstance(logical_position, int) or not 0 <= logical_position < USER_POSITION_COUNT:
            raise WavetableContractError("logical_position must be in 0..60")
        return self.logical_to_physical[logical_position]

    def logical_positions_for(self, physical_index: int) -> tuple[int, ...]:
        if isinstance(physical_index, bool) or not isinstance(physical_index, int) or not 0 <= physical_index < self.physical_wave_count:
            raise WavetableContractError("physical_index is outside the mapping")
        return self.physical_to_logical[physical_index]

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "logical_to_physical": list(self.logical_to_physical),
            "physical_to_logical": [list(item) for item in self.physical_to_logical],
            "logical_position_count": USER_POSITION_COUNT,
            "physical_wave_count": self.physical_wave_count,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class ConsolidationPairDecision:
    schema_version: int
    logical_position: int
    representative_position: int
    match_kind: ConsolidationMatchKind
    distance: WavePairDistance | None
    merged: bool
    protected: bool
    continuity_degradation: float
    usefulness_delta: float
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported consolidation pair decision schema version")
        for name in ("logical_position", "representative_position"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < USER_POSITION_COUNT:
                raise WavetableContractError(f"{name} must be in 0..60")
        if not isinstance(self.match_kind, ConsolidationMatchKind):
            raise WavetableContractError("match_kind must be ConsolidationMatchKind")
        if self.distance is not None and not isinstance(self.distance, WavePairDistance):
            raise WavetableContractError("distance must be WavePairDistance or None")
        if self.match_kind is ConsolidationMatchKind.DISTINCT and self.distance is not None:
            raise WavetableContractError("distinct decisions must not expose distance")
        for name in ("merged", "protected"):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        _ratio(self.continuity_degradation, name="continuity_degradation")
        _ratio(self.usefulness_delta, name="usefulness_delta")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "logical_position": self.logical_position,
            "display_logical_position": self.logical_position + 1,
            "representative_position": self.representative_position,
            "display_representative_position": self.representative_position + 1,
            "match_kind": self.match_kind.value,
            "distance": None if self.distance is None else self.distance.to_dict(),
            "merged": self.merged,
            "protected": self.protected,
            "continuity_degradation": self.continuity_degradation,
            "usefulness_delta": self.usefulness_delta,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class FinalUsefulnessAnalysis:
    schema_version: int
    slot_classes: tuple[FinalSlotClass, ...]
    structural_positions: tuple[int, ...]
    transition_positions: tuple[int, ...]
    redundant_positions: tuple[int, ...]
    essential_positions_for_v9: tuple[int, ...]
    exact_duplicate_groups: tuple[tuple[int, ...], ...]
    near_duplicate_groups: tuple[tuple[int, ...], ...]
    polarity_equivalent_pairs: tuple[tuple[int, int], ...]
    physical_wave_count: int
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported final usefulness schema version")
        classes = tuple(self.slot_classes)
        object.__setattr__(self, "slot_classes", classes)
        if len(classes) != USER_POSITION_COUNT or any(not isinstance(item, FinalSlotClass) for item in classes):
            raise WavetableContractError("slot_classes must classify all 61 positions")
        groups = (
            (FinalSlotClass.STRUCTURAL, tuple(self.structural_positions)),
            (FinalSlotClass.TRANSITION, tuple(self.transition_positions)),
            (FinalSlotClass.REDUNDANT, tuple(self.redundant_positions)),
        )
        covered: list[int] = []
        for expected_class, positions in groups:
            if tuple(sorted(set(positions))) != positions:
                raise WavetableContractError("final position groups must be sorted and unique")
            if any(classes[position] is not expected_class for position in positions):
                raise WavetableContractError("slot classes and position groups disagree")
            covered.extend(positions)
        if sorted(covered) != list(range(USER_POSITION_COUNT)):
            raise WavetableContractError("final usefulness groups must cover every position exactly once")
        essential = tuple(self.essential_positions_for_v9)
        object.__setattr__(self, "essential_positions_for_v9", essential)
        if tuple(sorted(set(essential))) != essential:
            raise WavetableContractError("essential positions must be sorted and unique")
        exact_groups = tuple(tuple(item) for item in self.exact_duplicate_groups)
        near_groups = tuple(tuple(item) for item in self.near_duplicate_groups)
        polarity_pairs = tuple(tuple(item) for item in self.polarity_equivalent_pairs)
        object.__setattr__(self, "exact_duplicate_groups", exact_groups)
        object.__setattr__(self, "near_duplicate_groups", near_groups)
        object.__setattr__(self, "polarity_equivalent_pairs", polarity_pairs)
        for group in exact_groups + near_groups:
            if len(group) < 2 or tuple(sorted(set(group))) != group:
                raise WavetableContractError("duplicate groups must contain at least two sorted positions")
        for pair in polarity_pairs:
            if len(pair) != 2 or pair[0] >= pair[1]:
                raise WavetableContractError("polarity pairs must be canonical ordered pairs")
        if isinstance(self.physical_wave_count, bool) or not isinstance(self.physical_wave_count, int) or not 1 <= self.physical_wave_count <= USER_POSITION_COUNT:
            raise WavetableContractError("physical_wave_count must be in 1..61")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "slot_classes": [item.value for item in self.slot_classes],
            "structural_positions": list(self.structural_positions),
            "transition_positions": list(self.transition_positions),
            "redundant_positions": list(self.redundant_positions),
            "essential_positions_for_v9": list(self.essential_positions_for_v9),
            "exact_duplicate_groups": [list(item) for item in self.exact_duplicate_groups],
            "near_duplicate_groups": [list(item) for item in self.near_duplicate_groups],
            "polarity_equivalent_pairs": [list(item) for item in self.polarity_equivalent_pairs],
            "physical_wave_count": self.physical_wave_count,
            "cdc_use_004_status": "prepared_for_v9",
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class ConsolidationReport:
    schema_version: int
    source_build_sha256: str
    policy_sha256: str
    decisions: tuple[ConsolidationPairDecision, ...]
    exact_group_count: int
    near_group_count: int
    polarity_diagnostic_count: int
    protected_positions: tuple[int, ...]
    continuity_score_before: float
    continuity_score_after: float
    maximum_continuity_degradation: float
    physical_wave_count: int
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported consolidation report schema version")
        _sha256(self.source_build_sha256, name="source_build_sha256")
        _sha256(self.policy_sha256, name="policy_sha256")
        decisions = tuple(self.decisions)
        object.__setattr__(self, "decisions", decisions)
        if len(decisions) != USER_POSITION_COUNT:
            raise WavetableContractError("report must contain one decision per logical position")
        if tuple(item.logical_position for item in decisions) != tuple(range(USER_POSITION_COUNT)):
            raise WavetableContractError("report decisions must use canonical position order")
        for name in ("exact_group_count", "near_group_count", "polarity_diagnostic_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise WavetableContractError(f"{name} must be a non-negative integer")
        protected = tuple(self.protected_positions)
        object.__setattr__(self, "protected_positions", protected)
        if tuple(sorted(set(protected))) != protected:
            raise WavetableContractError("protected_positions must be sorted and unique")
        for name in (
            "continuity_score_before",
            "continuity_score_after",
            "maximum_continuity_degradation",
        ):
            _ratio(getattr(self, name), name=name)
        if isinstance(self.physical_wave_count, bool) or not isinstance(self.physical_wave_count, int) or not 1 <= self.physical_wave_count <= USER_POSITION_COUNT:
            raise WavetableContractError("physical_wave_count must be in 1..61")
        object.__setattr__(self, "warnings", _strings(self.warnings, name="warnings"))
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_build_sha256": self.source_build_sha256,
            "policy_sha256": self.policy_sha256,
            "decisions": [item.to_dict() for item in self.decisions],
            "exact_group_count": self.exact_group_count,
            "near_group_count": self.near_group_count,
            "polarity_diagnostic_count": self.polarity_diagnostic_count,
            "protected_positions": list(self.protected_positions),
            "continuity_score_before": self.continuity_score_before,
            "continuity_score_after": self.continuity_score_after,
            "maximum_continuity_degradation": self.maximum_continuity_degradation,
            "physical_wave_count": self.physical_wave_count,
            "warnings": list(self.warnings),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class WavetableConsolidationAnalysis:
    schema_version: int
    status: ConsolidationStatus
    source_build_sha256: str
    policy: ConsolidationPolicy
    logical_wavetable: LogicalWavetable61 | None
    physical_wave_set: PhysicalWaveSet | None
    mapping: LogicalToPhysicalMapping | None
    final_usefulness: FinalUsefulnessAnalysis | None
    report: ConsolidationReport | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONSOLIDATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported consolidation analysis schema version")
        if not isinstance(self.status, ConsolidationStatus):
            raise WavetableContractError("status must be ConsolidationStatus")
        _sha256(self.source_build_sha256, name="source_build_sha256")
        if not isinstance(self.policy, ConsolidationPolicy):
            raise WavetableContractError("policy must be ConsolidationPolicy")
        object.__setattr__(self, "blockers", _strings(self.blockers, name="blockers"))
        object.__setattr__(self, "warnings", _strings(self.warnings, name="warnings"))
        outputs = (
            self.logical_wavetable,
            self.physical_wave_set,
            self.mapping,
            self.final_usefulness,
            self.report,
        )
        if self.status is ConsolidationStatus.COMPLETE:
            if self.blockers or any(item is None for item in outputs):
                raise WavetableContractError("complete consolidation requires every output and no blocker")
            assert self.physical_wave_set is not None
            assert self.mapping is not None
            assert self.final_usefulness is not None
            assert self.report is not None
            if self.physical_wave_set.physical_wave_count != self.mapping.physical_wave_count:
                raise WavetableContractError("physical wave set and mapping disagree")
            if self.final_usefulness.physical_wave_count != self.mapping.physical_wave_count:
                raise WavetableContractError("final usefulness and mapping disagree")
            if self.report.physical_wave_count != self.mapping.physical_wave_count:
                raise WavetableContractError("report and mapping disagree")
        else:
            if not self.blockers or any(item is not None for item in outputs):
                raise WavetableContractError("rejected consolidation must expose blockers only")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "source_build_sha256": self.source_build_sha256,
            "policy": self.policy.to_dict(),
            "logical_wavetable": None if self.logical_wavetable is None else self.logical_wavetable.to_dict(),
            "physical_wave_set": None if self.physical_wave_set is None else self.physical_wave_set.to_dict(),
            "mapping": None if self.mapping is None else self.mapping.to_dict(),
            "final_usefulness": None if self.final_usefulness is None else self.final_usefulness.to_dict(),
            "report": None if self.report is None else self.report.to_dict(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "boundaries": {
                "inventory_allocated": False,
                "wctd_materialized": False,
                "sysex_generated": False,
                "midi_opened": False,
                "midi_transmitted": False,
            },
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _metrics_summary(slots: Sequence[WavetableSlot]) -> PhysicalWaveMetricsSummary:
    fields = (
        "quality_score",
        "usefulness_score",
        "stability_score",
        "harmonic_richness",
        "brightness",
        "bass_power",
        "source_fidelity",
        "xt_compatibility",
        "perceptual_novelty",
    )

    def make(kind: str) -> WaveBuildMetrics:
        values: dict[str, float] = {}
        for field in fields:
            sequence = [float(getattr(slot.metrics, field)) for slot in slots]
            if kind == "minimum":
                values[field] = _q(min(sequence))
            elif kind == "maximum":
                values[field] = _q(max(sequence))
            else:
                values[field] = _q(sum(sequence) / len(sequence))
        return WaveBuildMetrics(**values, reason=f"Physical-wave {kind} across logical slots.")

    return PhysicalWaveMetricsSummary(
        schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
        minimum=make("minimum"),
        maximum=make("maximum"),
        mean=make("mean"),
    )


def _protected(slot: WavetableSlot, policy: ConsolidationPolicy) -> bool:
    return bool(
        (policy.protect_locked and slot.locked)
        or (policy.protect_essential and slot.role is WaveRole.ESSENTIAL)
        or (policy.protect_breakpoint and slot.role is WaveRole.BREAKPOINT)
        or (
            policy.protect_structural
            and (slot.structural or slot.role in {WaveRole.STRUCTURAL, WaveRole.EXTREME})
        )
    )


def _usefulness_delta(left: WavetableSlot, right: WavetableSlot) -> float:
    fields = (
        "quality_score",
        "usefulness_score",
        "stability_score",
        "harmonic_richness",
        "brightness",
        "bass_power",
        "source_fidelity",
        "xt_compatibility",
        "perceptual_novelty",
    )
    return _q(max(abs(float(getattr(left.metrics, item)) - float(getattr(right.metrics, item))) for item in fields))


def _continuity_cost(samples: Sequence[tuple[int, ...]]) -> float:
    if len(samples) < 2:
        return 0.0
    distances = [compare_wave_shapes(left, right).perceptual_distance for left, right in zip(samples, samples[1:])]
    return _q(sum(distances) / len(distances))


def _tentative_continuity_degradation(
    slots: Sequence[WavetableSlot],
    mapping: Sequence[int],
    representatives: Sequence[int],
    logical_position: int,
    physical_index: int,
) -> float:
    before_samples = [item.stored_samples for item in slots]
    tentative = list(mapping)
    tentative[logical_position] = physical_index
    after_samples = [slots[representatives[index]].stored_samples for index in tentative]
    before = _continuity_cost(before_samples)
    after = _continuity_cost(after_samples)
    return _q(max(0.0, after - before))


def _near_eligible(distance: WavePairDistance, policy: ConsolidationPolicy) -> bool:
    return bool(
        distance.perceptual_distance <= policy.near_perceptual_distance
        and distance.spectral_distance <= policy.near_spectral_distance
        and distance.feature_distance <= policy.near_feature_distance
        and distance.maximum_sample_distance <= policy.near_maximum_sample_distance
        and distance.absolute_correlation >= policy.minimum_absolute_correlation
    )


def _classify_positions(
    slots: Sequence[WavetableSlot],
    mapping: LogicalToPhysicalMapping,
) -> tuple[tuple[FinalSlotClass, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    classes: list[FinalSlotClass] = []
    seen_physical: set[int] = set()
    for slot in slots:
        physical = mapping.logical_to_physical[slot.position]
        repeated = physical in seen_physical
        seen_physical.add(physical)
        if slot.transition:
            classes.append(FinalSlotClass.TRANSITION)
        elif repeated or slot.redundant:
            classes.append(FinalSlotClass.REDUNDANT)
        else:
            classes.append(FinalSlotClass.STRUCTURAL)
    result = tuple(classes)
    return (
        result,
        tuple(index for index, item in enumerate(result) if item is FinalSlotClass.STRUCTURAL),
        tuple(index for index, item in enumerate(result) if item is FinalSlotClass.TRANSITION),
        tuple(index for index, item in enumerate(result) if item is FinalSlotClass.REDUNDANT),
    )


def consolidate_wavetable_build(
    build: WavetableBuild,
    policy: ConsolidationPolicy = DEFAULT_CONSOLIDATION_POLICY,
) -> WavetableConsolidationAnalysis:
    """Consolidate a final 61-slot build into 1..61 physical XT waves.

    Logical positions and their complete metadata remain untouched.  Exact
    XT-native stored-sample duplicates are always shareable.  Near duplicates
    are opt-in and must satisfy sample, spectral, feature, usefulness,
    protection and continuity gates.  Polarity equivalence is diagnostic-only
    by default.
    """

    if not isinstance(build, WavetableBuild):
        raise WavetableContractError("build must be WavetableBuild")
    if not isinstance(policy, ConsolidationPolicy):
        raise WavetableContractError("policy must be ConsolidationPolicy")
    if build.status is not WavetableBuildStatus.COMPLETE:
        return WavetableConsolidationAnalysis(
            schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
            status=ConsolidationStatus.REJECTED,
            source_build_sha256=build.analysis_sha256,
            policy=policy,
            logical_wavetable=None,
            physical_wave_set=None,
            mapping=None,
            final_usefulness=None,
            report=None,
            blockers=("V8-I requires a complete 61-slot build",),
            warnings=(),
            reason="Consolidation rejected an incomplete build without partial output.",
        )

    slots = tuple(build.slots)
    representatives: list[int] = []
    mapping: list[int] = []
    group_kinds: list[ConsolidationMatchKind] = []
    decisions: list[ConsolidationPairDecision] = []
    polarity_pairs: list[tuple[int, int]] = []
    warnings: list[str] = []

    for position, slot in enumerate(slots):
        exact_index = next(
            (
                physical_index
                for physical_index, representative in enumerate(representatives)
                if slots[representative].stored_samples == slot.stored_samples
            ),
            None,
        )
        if exact_index is not None:
            representative = representatives[exact_index]
            mapping.append(exact_index)
            if group_kinds[exact_index] is ConsolidationMatchKind.DISTINCT:
                group_kinds[exact_index] = ConsolidationMatchKind.EXACT
            decisions.append(
                ConsolidationPairDecision(
                    schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
                    logical_position=position,
                    representative_position=representative,
                    match_kind=ConsolidationMatchKind.EXACT,
                    distance=compare_wave_shapes(slot.stored_samples, slots[representative].stored_samples),
                    merged=True,
                    protected=_protected(slot, policy) or _protected(slots[representative], policy),
                    continuity_degradation=0.0,
                    usefulness_delta=_usefulness_delta(slot, slots[representative]),
                    reason="Exact XT-native stored samples share one physical wave without information loss.",
                )
            )
            continue

        selected: tuple[int, int, WavePairDistance, float, float, ConsolidationMatchKind] | None = None
        for physical_index, representative in enumerate(representatives):
            representative_slot = slots[representative]
            polarity_equivalent = all(
                left == -right
                for left, right in zip(slot.stored_samples, representative_slot.stored_samples)
            )
            if polarity_equivalent:
                polarity_pairs.append((representative, position))
            if not policy.allow_near_duplicates and not policy.merge_polarity_equivalent:
                continue
            distance = compare_wave_shapes(slot.stored_samples, representative_slot.stored_samples)
            if distance.polarity_equivalent:
                if not policy.merge_polarity_equivalent:
                    continue
                kind = ConsolidationMatchKind.POLARITY_EQUIVALENT
            else:
                kind = ConsolidationMatchKind.NEAR
            if not policy.allow_near_duplicates and kind is ConsolidationMatchKind.NEAR:
                continue
            if not _near_eligible(distance, policy):
                continue
            protected_pair = _protected(slot, policy) or _protected(representative_slot, policy)
            if protected_pair:
                continue
            usefulness_delta = _usefulness_delta(slot, representative_slot)
            if usefulness_delta > policy.maximum_usefulness_delta:
                continue
            degradation = _tentative_continuity_degradation(
                slots, mapping + [len(representatives)], representatives + [position], position, physical_index
            )
            if degradation > policy.maximum_continuity_degradation:
                continue
            candidate = (
                physical_index,
                representative,
                distance,
                usefulness_delta,
                degradation,
                kind,
            )
            if selected is None or (
                candidate[2].perceptual_distance,
                candidate[1],
            ) < (
                selected[2].perceptual_distance,
                selected[1],
            ):
                selected = candidate

        if selected is None:
            physical_index = len(representatives)
            representatives.append(position)
            mapping.append(physical_index)
            group_kinds.append(ConsolidationMatchKind.DISTINCT)
            decisions.append(
                ConsolidationPairDecision(
                    schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
                    logical_position=position,
                    representative_position=position,
                    match_kind=ConsolidationMatchKind.DISTINCT,
                    distance=None,
                    merged=False,
                    protected=_protected(slot, policy),
                    continuity_degradation=0.0,
                    usefulness_delta=0.0,
                    reason="No eligible earlier representative; a distinct physical wave is retained.",
                )
            )
            continue

        physical_index, representative, distance, usefulness_delta, degradation, kind = selected
        mapping.append(physical_index)
        if kind in {ConsolidationMatchKind.NEAR, ConsolidationMatchKind.POLARITY_EQUIVALENT}:
            group_kinds[physical_index] = kind
        elif group_kinds[physical_index] is ConsolidationMatchKind.DISTINCT:
            group_kinds[physical_index] = kind
        decisions.append(
            ConsolidationPairDecision(
                schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
                logical_position=position,
                representative_position=representative,
                match_kind=kind,
                distance=distance,
                merged=True,
                protected=False,
                continuity_degradation=degradation,
                usefulness_delta=usefulness_delta,
                reason=(
                    "Near duplicate passed versioned sample, perceptual, metadata and continuity gates."
                    if kind is ConsolidationMatchKind.NEAR
                    else "Polarity-equivalent merge was explicitly enabled and passed all near-merge gates."
                ),
            )
        )

    reverse = tuple(
        tuple(position for position, physical_index in enumerate(mapping) if physical_index == index)
        for index in range(len(representatives))
    )
    mapping_model = LogicalToPhysicalMapping(
        schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
        logical_to_physical=tuple(mapping),
        physical_to_logical=reverse,
        reason="Canonical reversible mapping from 61 logical positions to N physical waves.",
    )

    physical_waves: list[PhysicalWave] = []
    for physical_index, representative in enumerate(representatives):
        positions = reverse[physical_index]
        members = tuple(slots[position] for position in positions)
        source_ids = tuple(dict.fromkeys(item for member in members for item in member.source_candidate_ids))
        origins = tuple(dict.fromkeys(member.origin for member in members))
        methods = tuple(dict.fromkeys(member.generation_method for member in members))
        roles = tuple(dict.fromkeys(member.role for member in members))
        kind = group_kinds[physical_index]
        sample_hash = stored_samples_sha256(slots[representative].stored_samples)
        physical_waves.append(
            PhysicalWave(
                schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
                physical_index=physical_index,
                wave_id=f"physical-{physical_index:02d}-{sample_hash[:12]}",
                representative_position=representative,
                stored_samples=slots[representative].stored_samples,
                logical_positions=positions,
                logical_slot_sha256s=tuple(item.slot_sha256 for item in members),
                source_candidate_ids=source_ids,
                origins=origins,
                generation_methods=methods,
                roles=roles,
                metrics_summary=_metrics_summary(members),
                exact_group=kind is ConsolidationMatchKind.EXACT,
                near_group=kind in {ConsolidationMatchKind.NEAR, ConsolidationMatchKind.POLARITY_EQUIVALENT},
                reason="Physical wave aggregates every logical position and preserves full per-slot provenance hashes.",
            )
        )

    physical_set = PhysicalWaveSet(
        schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
        waves=tuple(physical_waves),
        reason="Final physical XT wave inventory after post-interpolation and post-shaping consolidation.",
    )
    logical = LogicalWavetable61(
        schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
        source_build_sha256=build.analysis_sha256,
        slots=slots,
        reason="Immutable 61-position logical wavetable retained independently of physical sharing.",
    )

    classes, structural, transitions, redundant = _classify_positions(slots, mapping_model)
    exact_groups = tuple(
        group for index, group in enumerate(reverse) if len(group) > 1 and group_kinds[index] is ConsolidationMatchKind.EXACT
    )
    near_groups = tuple(
        group
        for index, group in enumerate(reverse)
        if len(group) > 1 and group_kinds[index] in {ConsolidationMatchKind.NEAR, ConsolidationMatchKind.POLARITY_EQUIVALENT}
    )
    essential_positions = tuple(
        slot.position
        for slot in slots
        if slot.locked
        or slot.role in {WaveRole.ESSENTIAL, WaveRole.BREAKPOINT}
        or (slot.structural and slot.role in {WaveRole.STRUCTURAL, WaveRole.EXTREME})
    )
    final_usefulness = FinalUsefulnessAnalysis(
        schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
        slot_classes=classes,
        structural_positions=structural,
        transition_positions=transitions,
        redundant_positions=redundant,
        essential_positions_for_v9=essential_positions,
        exact_duplicate_groups=exact_groups,
        near_duplicate_groups=near_groups,
        polarity_equivalent_pairs=tuple(sorted(set(polarity_pairs))),
        physical_wave_count=physical_set.physical_wave_count,
        reason="Every final logical slot is requalified while essential-slot data is prepared, not reported, for V9.",
    )

    before_samples = [item.stored_samples for item in slots]
    after_samples = [physical_waves[index].stored_samples for index in mapping]
    before_score = _q(max(0.0, 1.0 - _continuity_cost(before_samples)))
    after_score = _q(max(0.0, 1.0 - _continuity_cost(after_samples)))
    maximum_degradation = max((item.continuity_degradation for item in decisions), default=0.0)
    if polarity_pairs and not policy.merge_polarity_equivalent:
        warnings.append("Polarity-equivalent pairs were diagnosed but not merged by default.")
    report = ConsolidationReport(
        schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
        source_build_sha256=build.analysis_sha256,
        policy_sha256=policy.analysis_sha256,
        decisions=tuple(decisions),
        exact_group_count=len(exact_groups),
        near_group_count=len(near_groups),
        polarity_diagnostic_count=len(set(polarity_pairs)),
        protected_positions=tuple(position for position, slot in enumerate(slots) if _protected(slot, policy)),
        continuity_score_before=before_score,
        continuity_score_after=after_score,
        maximum_continuity_degradation=maximum_degradation,
        physical_wave_count=physical_set.physical_wave_count,
        warnings=tuple(warnings),
        reason="Deterministic final-table consolidation report with explicit merge and protection decisions.",
    )

    return WavetableConsolidationAnalysis(
        schema_version=WAVETABLE_CONSOLIDATION_SCHEMA_VERSION,
        status=ConsolidationStatus.COMPLETE,
        source_build_sha256=build.analysis_sha256,
        policy=policy,
        logical_wavetable=logical,
        physical_wave_set=physical_set,
        mapping=mapping_model,
        final_usefulness=final_usefulness,
        report=report,
        blockers=(),
        warnings=tuple(warnings),
        reason=(
            f"V8-I consolidated 61 logical positions into {physical_set.physical_wave_count} physical XT waves "
            "without inventory allocation or WCTD materialization."
        ),
    )


__all__ = [
    "WAVETABLE_CONSOLIDATION_SCHEMA_VERSION",
    "ConsolidationStatus",
    "ConsolidationMatchKind",
    "FinalSlotClass",
    "ConsolidationPolicy",
    "DEFAULT_CONSOLIDATION_POLICY",
    "LogicalWavetable61",
    "PhysicalWaveMetricsSummary",
    "PhysicalWave",
    "PhysicalWaveSet",
    "LogicalToPhysicalMapping",
    "ConsolidationPairDecision",
    "FinalUsefulnessAnalysis",
    "ConsolidationReport",
    "WavetableConsolidationAnalysis",
    "consolidate_wavetable_build",
]
