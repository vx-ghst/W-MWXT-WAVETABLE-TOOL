from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .continuity import (
    DEFAULT_CONTINUITY_THRESHOLDS,
    ContinuityStatus,
    ContinuityThresholds,
    WavetableContinuityReport,
    analyze_wavetable_continuity,
)
from .deduplication import CodeV8BAnalysis
from .interpolation import (
    DEFAULT_INTERPOLATION_POLICY,
    InterpolatedWave,
    InterpolationPolicy,
    progression_value,
    select_interpolation_method,
)
from .metrics import analyze_wave_shape, compare_wave_shapes
from .models import (
    GenerationMethod,
    USER_POSITION_COUNT,
    WAVETABLE_BUILD_SCHEMA_VERSION,
    WaveOrigin,
    WaveRole,
    WavetableBuild,
    WavetableBuildRequest,
    WavetableBuildSet,
    WavetableBuildStatus,
    WavetableCandidate,
    WavetableContractError,
    WavetableSlot,
)
from .selection import CodeV8CAnalysis
from .usefulness import CandidateStructureClass
from .variants import (
    CodeV8DAnalysis,
    CodeV8DStatus,
    WavetablePlacementVariant,
)

WAVETABLE_BUILDER_SCHEMA_VERSION = 1
_BUILDER_PRECISION = 12


def _q(value: float) -> float:
    return round(float(value), _BUILDER_PRECISION)


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


class CodeV8EStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


class TransitionPositionKind(str, Enum):
    INTERPOLATED = "interpolated"
    REPEATED_STAGE = "repeated_stage"
    EDGE_HOLD = "edge_hold"


@dataclass(frozen=True, slots=True)
class TransitionDensityPolicy:
    schema_version: int = WAVETABLE_BUILDER_SCHEMA_VERSION
    minimum_active_steps_per_interval: int = 1
    base_active_fraction: float = 0.25
    complexity_weight: float = 0.75
    complexity_exponent: float = 1.10

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILDER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported density-policy schema version")
        value = self.minimum_active_steps_per_interval
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise WavetableContractError(
                "minimum_active_steps_per_interval must be a positive integer"
            )
        for name in ("base_active_fraction", "complexity_weight"):
            _ratio(getattr(self, name), name=name)
        if self.base_active_fraction + self.complexity_weight > 1.0 + 1e-12:
            raise WavetableContractError(
                "base_active_fraction plus complexity_weight cannot exceed one"
            )
        exponent = float(self.complexity_exponent)
        if not math.isfinite(exponent) or exponent <= 0.0:
            raise WavetableContractError("complexity_exponent must be positive and finite")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "minimum_active_steps_per_interval": self.minimum_active_steps_per_interval,
            "base_active_fraction": self.base_active_fraction,
            "complexity_weight": self.complexity_weight,
            "complexity_exponent": self.complexity_exponent,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_TRANSITION_DENSITY_POLICY = TransitionDensityPolicy()


@dataclass(frozen=True, slots=True)
class TransitionIntervalPlan:
    schema_version: int
    left_candidate_id: str
    right_candidate_id: str
    left_position: int
    right_position: int
    open_positions: tuple[int, ...]
    complexity_score: float
    target_active_fraction: float
    active_step_count: int
    progress_values: tuple[float, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILDER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported transition-interval schema version")
        for name in ("left_candidate_id", "right_candidate_id"):
            _normalized(getattr(self, name), name=name)
        if self.left_candidate_id == self.right_candidate_id:
            raise WavetableContractError("transition interval endpoints must be distinct")
        for name in ("left_position", "right_position"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 61:
                raise WavetableContractError(f"{name} must be an integer in 0..60")
        if self.right_position <= self.left_position:
            raise WavetableContractError("right_position must follow left_position")
        positions = tuple(self.open_positions)
        object.__setattr__(self, "open_positions", positions)
        expected = tuple(range(self.left_position + 1, self.right_position))
        if positions != expected:
            raise WavetableContractError("open_positions must exactly fill the anchor interval")
        _ratio(self.complexity_score, name="complexity_score")
        _ratio(self.target_active_fraction, name="target_active_fraction")
        if (
            isinstance(self.active_step_count, bool)
            or not isinstance(self.active_step_count, int)
            or self.active_step_count < 0
            or self.active_step_count > len(positions)
        ):
            raise WavetableContractError("active_step_count is outside interval capacity")
        values = tuple(self.progress_values)
        object.__setattr__(self, "progress_values", values)
        if len(values) != len(positions):
            raise WavetableContractError("progress_values must match open_positions")
        if any(not 0.0 < value < 1.0 for value in values):
            raise WavetableContractError("transition progress values must be inside (0, 1)")
        if values != tuple(sorted(values)):
            raise WavetableContractError("progress_values must be non-decreasing")
        if len(set(values)) != self.active_step_count:
            raise WavetableContractError("active_step_count must equal distinct progress count")
        _normalized(self.reason, name="reason")

    @property
    def capacity(self) -> int:
        return len(self.open_positions)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "left_candidate_id": self.left_candidate_id,
            "right_candidate_id": self.right_candidate_id,
            "left_position": self.left_position,
            "left_display_position": self.left_position + 1,
            "right_position": self.right_position,
            "right_display_position": self.right_position + 1,
            "open_positions": list(self.open_positions),
            "display_open_positions": [item + 1 for item in self.open_positions],
            "capacity": self.capacity,
            "complexity_score": self.complexity_score,
            "target_active_fraction": self.target_active_fraction,
            "active_step_count": self.active_step_count,
            "progress_values": list(self.progress_values),
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
class TransitionPositionRecord:
    schema_version: int
    position: int
    kind: TransitionPositionKind
    source_candidate_ids: tuple[str, ...]
    raw_progress: float | None
    shaped_progress: float | None
    method: GenerationMethod | None
    stored_samples_sha256: str
    active_stage: bool
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILDER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported transition-position schema version")
        if (
            isinstance(self.position, bool)
            or not isinstance(self.position, int)
            or not 0 <= self.position < USER_POSITION_COUNT
        ):
            raise WavetableContractError("position must be an integer in 0..60")
        if not isinstance(self.kind, TransitionPositionKind):
            raise WavetableContractError("kind must be TransitionPositionKind")
        source_ids = tuple(self.source_candidate_ids)
        object.__setattr__(self, "source_candidate_ids", source_ids)
        if not source_ids or len(set(source_ids)) != len(source_ids):
            raise WavetableContractError("source_candidate_ids must be non-empty and unique")
        for item in source_ids:
            _normalized(item, name="source_candidate_id")
        if self.kind is TransitionPositionKind.EDGE_HOLD:
            if len(source_ids) != 1 or self.raw_progress is not None or self.shaped_progress is not None or self.method is not None:
                raise WavetableContractError("edge hold requires one source and no interpolation data")
        else:
            if len(source_ids) != 2 or self.raw_progress is None or self.shaped_progress is None:
                raise WavetableContractError("transition stages require two sources and progress")
            _ratio(self.raw_progress, name="raw_progress")
            _ratio(self.shaped_progress, name="shaped_progress")
            if self.method is None or not self.method.is_interpolation:
                raise WavetableContractError("transition stage requires an interpolation method")
        _sha256(self.stored_samples_sha256, name="stored_samples_sha256")
        if not isinstance(self.active_stage, bool):
            raise WavetableContractError("active_stage must be boolean")
        if self.kind is TransitionPositionKind.REPEATED_STAGE and self.active_stage:
            raise WavetableContractError("repeated stages cannot be active_stage")
        if self.kind is TransitionPositionKind.INTERPOLATED and not self.active_stage:
            raise WavetableContractError("interpolated stages must be active_stage")
        if self.kind is TransitionPositionKind.EDGE_HOLD and self.active_stage:
            raise WavetableContractError("edge holds cannot be active_stage")
        object.__setattr__(self, "evidence", _entries(self.evidence, name="evidence", allow_empty=False))
        _normalized(self.reason, name="reason")

    @property
    def display_position(self) -> int:
        return self.position + 1

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "position": self.position,
            "display_position": self.display_position,
            "kind": self.kind.value,
            "source_candidate_ids": list(self.source_candidate_ids),
            "raw_progress": self.raw_progress,
            "shaped_progress": self.shaped_progress,
            "method": None if self.method is None else self.method.value,
            "stored_samples_sha256": self.stored_samples_sha256,
            "active_stage": self.active_stage,
            "evidence": list(self.evidence),
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
class WavetableTransitionMap:
    schema_version: int
    v8d_variant_id: str
    placement_sha256: str
    density_policy: TransitionDensityPolicy
    intervals: tuple[TransitionIntervalPlan, ...]
    records: tuple[TransitionPositionRecord, ...]
    open_position_count: int
    active_transition_count: int
    repeated_transition_count: int
    edge_hold_count: int
    density_fit_score: float
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILDER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported transition-map schema version")
        _normalized(self.v8d_variant_id, name="v8d_variant_id")
        _sha256(self.placement_sha256, name="placement_sha256")
        if not isinstance(self.density_policy, TransitionDensityPolicy):
            raise WavetableContractError("density_policy must be TransitionDensityPolicy")
        intervals = tuple(self.intervals)
        records = tuple(self.records)
        object.__setattr__(self, "intervals", intervals)
        object.__setattr__(self, "records", records)
        if any(not isinstance(item, TransitionIntervalPlan) for item in intervals):
            raise WavetableContractError("intervals contain invalid values")
        if any(not isinstance(item, TransitionPositionRecord) for item in records):
            raise WavetableContractError("records contain invalid values")
        positions = tuple(item.position for item in records)
        if positions != tuple(sorted(positions)) or len(set(positions)) != len(positions):
            raise WavetableContractError("transition records must be unique and sorted")
        counts = (
            self.open_position_count,
            self.active_transition_count,
            self.repeated_transition_count,
            self.edge_hold_count,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
            raise WavetableContractError("transition counts must be non-negative integers")
        if self.open_position_count != len(records):
            raise WavetableContractError("open_position_count disagrees with records")
        if self.active_transition_count != sum(item.kind is TransitionPositionKind.INTERPOLATED for item in records):
            raise WavetableContractError("active_transition_count disagrees with records")
        if self.repeated_transition_count != sum(item.kind is TransitionPositionKind.REPEATED_STAGE for item in records):
            raise WavetableContractError("repeated_transition_count disagrees with records")
        if self.edge_hold_count != sum(item.kind is TransitionPositionKind.EDGE_HOLD for item in records):
            raise WavetableContractError("edge_hold_count disagrees with records")
        if self.active_transition_count + self.repeated_transition_count + self.edge_hold_count != self.open_position_count:
            raise WavetableContractError("transition record kinds must partition open positions")
        _ratio(self.density_fit_score, name="density_fit_score")
        _normalized(self.reason, name="reason")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "v8d_variant_id": self.v8d_variant_id,
            "placement_sha256": self.placement_sha256,
            "density_policy": self.density_policy.to_dict(),
            "intervals": [item.to_dict() for item in self.intervals],
            "records": [item.to_dict() for item in self.records],
            "open_position_count": self.open_position_count,
            "active_transition_count": self.active_transition_count,
            "repeated_transition_count": self.repeated_transition_count,
            "edge_hold_count": self.edge_hold_count,
            "density_fit_score": self.density_fit_score,
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
class CodeV8EVariant:
    schema_version: int
    variant_id: str
    rank: int
    v8d_variant_id: str
    v8d_rank: int
    build: WavetableBuild
    transition_map: WavetableTransitionMap
    continuity: WavetableContinuityReport
    objective_score: float
    placement_score: float
    density_score: float
    continuity_score: float
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILDER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-E variant schema version")
        for name in ("variant_id", "v8d_variant_id"):
            _normalized(getattr(self, name), name=name)
        for name in ("rank", "v8d_rank"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise WavetableContractError(f"{name} must be a positive integer")
        if not isinstance(self.build, WavetableBuild) or self.build.status is not WavetableBuildStatus.COMPLETE:
            raise WavetableContractError("V8-E variant requires a complete WavetableBuild")
        if self.build.variant_id != self.variant_id:
            raise WavetableContractError("build variant_id must match V8-E variant_id")
        if not isinstance(self.transition_map, WavetableTransitionMap):
            raise WavetableContractError("transition_map must be WavetableTransitionMap")
        if self.transition_map.v8d_variant_id != self.v8d_variant_id:
            raise WavetableContractError("transition map does not link to V8-D variant")
        if not isinstance(self.continuity, WavetableContinuityReport):
            raise WavetableContractError("continuity must be WavetableContinuityReport")
        if self.continuity.status is ContinuityStatus.FAIL:
            raise WavetableContractError("V8-E variants cannot retain failed continuity")
        if self.continuity.build_sha256 != self.build.analysis_sha256:
            raise WavetableContractError("continuity report does not link to build")
        for name in (
            "objective_score",
            "placement_score",
            "density_score",
            "continuity_score",
        ):
            _ratio(getattr(self, name), name=name)
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        _normalized(self.reason, name="reason")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "rank": self.rank,
            "v8d_variant_id": self.v8d_variant_id,
            "v8d_rank": self.v8d_rank,
            "build": self.build.to_dict(),
            "transition_map": self.transition_map.to_dict(),
            "continuity": self.continuity.to_dict(),
            "objective_score": self.objective_score,
            "placement_score": self.placement_score,
            "density_score": self.density_score,
            "continuity_score": self.continuity_score,
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
class CodeV8EAnalysis:
    schema_version: int
    status: CodeV8EStatus
    request_sha256: str
    v8b_analysis_sha256: str
    v8c_analysis_sha256: str
    v8d_analysis_sha256: str
    interpolation_policy: InterpolationPolicy
    density_policy: TransitionDensityPolicy
    continuity_thresholds: ContinuityThresholds
    variants: tuple[CodeV8EVariant, ...]
    primary_variant_id: str | None
    build_set: WavetableBuildSet | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILDER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-E schema version")
        if not isinstance(self.status, CodeV8EStatus):
            raise WavetableContractError("status must be CodeV8EStatus")
        for name in (
            "request_sha256",
            "v8b_analysis_sha256",
            "v8c_analysis_sha256",
            "v8d_analysis_sha256",
        ):
            _sha256(getattr(self, name), name=name)
        if not isinstance(self.interpolation_policy, InterpolationPolicy):
            raise WavetableContractError("interpolation_policy must be InterpolationPolicy")
        if not isinstance(self.density_policy, TransitionDensityPolicy):
            raise WavetableContractError("density_policy must be TransitionDensityPolicy")
        if not isinstance(self.continuity_thresholds, ContinuityThresholds):
            raise WavetableContractError("continuity_thresholds must be ContinuityThresholds")
        variants = tuple(self.variants)
        object.__setattr__(self, "variants", variants)
        if any(not isinstance(item, CodeV8EVariant) for item in variants):
            raise WavetableContractError("variants contain invalid values")
        if tuple(item.rank for item in variants) != tuple(range(1, len(variants) + 1)):
            raise WavetableContractError("V8-E variant ranks must be canonical")
        if len({item.variant_id for item in variants}) != len(variants):
            raise WavetableContractError("V8-E variant IDs must be unique")
        scores = tuple(item.objective_score for item in variants)
        if scores != tuple(sorted(scores, reverse=True)):
            raise WavetableContractError("V8-E variants must be ranked by objective score")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        object.__setattr__(self, "blockers", _entries(self.blockers, name="blockers"))
        _normalized(self.reason, name="reason")
        if self.status is CodeV8EStatus.COMPLETE:
            if self.blockers:
                raise WavetableContractError("complete V8-E analysis cannot contain blockers")
            if not variants or self.primary_variant_id is None or self.build_set is None:
                raise WavetableContractError("complete V8-E analysis requires variants and build_set")
            if variants[0].variant_id != self.primary_variant_id:
                raise WavetableContractError("primary V8-E variant must have rank one")
            if self.build_set.primary_variant_id != self.primary_variant_id:
                raise WavetableContractError("build_set primary variant disagrees")
            if tuple(build.variant_id for build in self.build_set.builds) != tuple(item.variant_id for item in variants):
                raise WavetableContractError("build_set builds disagree with V8-E variants")
        else:
            if not self.blockers:
                raise WavetableContractError("rejected V8-E analysis requires blockers")
            if variants or self.primary_variant_id is not None or self.build_set is not None:
                raise WavetableContractError("rejected V8-E analysis cannot expose partial variants")

    @property
    def produced_variant_count(self) -> int:
        return len(self.variants)

    @property
    def primary_variant(self) -> CodeV8EVariant | None:
        return None if not self.variants else self.variants[0]

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "v8b_analysis_sha256": self.v8b_analysis_sha256,
            "v8c_analysis_sha256": self.v8c_analysis_sha256,
            "v8d_analysis_sha256": self.v8d_analysis_sha256,
            "interpolation_policy": self.interpolation_policy.to_dict(),
            "density_policy": self.density_policy.to_dict(),
            "continuity_thresholds": self.continuity_thresholds.to_dict(),
            "produced_variant_count": self.produced_variant_count,
            "primary_variant_id": self.primary_variant_id,
            "variants": [item.to_dict() for item in self.variants],
            "build_set": None if self.build_set is None else self.build_set.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "fills_all_61_positions": self.status is CodeV8EStatus.COMPLETE,
                "generates_transition_waves": True,
                "allocates_adaptive_density": True,
                "evaluates_continuity": True,
                "applies_factory_style": False,
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


def _fundamental_delta(left: WavetableCandidate, right: WavetableCandidate) -> float:
    left_shape = analyze_wave_shape(left)
    right_shape = analyze_wave_shape(right)
    return min(1.0, abs(left_shape.harmonic_concentration - right_shape.harmonic_concentration))


def _interval_complexity(left: WavetableCandidate, right: WavetableCandidate) -> float:
    distance = compare_wave_shapes(left, right)
    left_shape = analyze_wave_shape(left)
    right_shape = analyze_wave_shape(right)
    level_delta = abs(left_shape.rms - right_shape.rms)
    endpoint_complexity = 0.5 * (left_shape.complexity + right_shape.complexity)
    value = (
        0.32 * distance.perceptual_distance
        + 0.22 * distance.spectral_distance
        + 0.14 * distance.maximum_sample_distance
        + 0.14 * endpoint_complexity
        + 0.10 * level_delta
        + 0.08 * _fundamental_delta(left, right)
    )
    return _q(max(0.0, min(1.0, value)))


def _progress_values(capacity: int, active_steps: int) -> tuple[float, ...]:
    if capacity == 0:
        return ()
    if not 1 <= active_steps <= capacity:
        raise WavetableContractError("active steps must be between one and interval capacity")
    result = []
    for index in range(capacity):
        stage = min(active_steps, (index * active_steps) // capacity + 1)
        result.append(_q(stage / (active_steps + 1)))
    return tuple(result)


def plan_transition_density(
    request: WavetableBuildRequest,
    variant: WavetablePlacementVariant,
    policy: TransitionDensityPolicy = DEFAULT_TRANSITION_DENSITY_POLICY,
) -> tuple[TransitionIntervalPlan, ...]:
    """Plan active interpolation stages inside the fixed V8-D anchor intervals."""

    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(variant, WavetablePlacementVariant):
        raise WavetableContractError("variant must be WavetablePlacementVariant")
    if not isinstance(policy, TransitionDensityPolicy):
        raise WavetableContractError("policy must be TransitionDensityPolicy")
    if variant.placement.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("V8-D placement does not link to request")
    candidates = {item.candidate_id: item for item in request.candidates}
    assignments = tuple(sorted(variant.placement.assignments, key=lambda item: item.position))
    plans: list[TransitionIntervalPlan] = []
    for left_assignment, right_assignment in zip(assignments, assignments[1:]):
        positions = tuple(range(left_assignment.position + 1, right_assignment.position))
        if not positions:
            continue
        left = candidates[left_assignment.candidate_id]
        right = candidates[right_assignment.candidate_id]
        complexity = _interval_complexity(left, right)
        target_fraction = _q(
            min(
                1.0,
                policy.base_active_fraction
                + policy.complexity_weight * (complexity ** policy.complexity_exponent),
            )
        )
        active = max(
            policy.minimum_active_steps_per_interval,
            int(math.ceil(len(positions) * target_fraction)),
        )
        active = min(len(positions), active)
        plans.append(
            TransitionIntervalPlan(
                schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
                left_candidate_id=left.candidate_id,
                right_candidate_id=right.candidate_id,
                left_position=left_assignment.position,
                right_position=right_assignment.position,
                open_positions=positions,
                complexity_score=complexity,
                target_active_fraction=target_fraction,
                active_step_count=active,
                progress_values=_progress_values(len(positions), active),
                reason="Adaptive density derived from endpoint distance and interval complexity.",
            )
        )
    return tuple(plans)


def _role_for_assignment(assignment) -> tuple[WaveRole, bool]:
    if assignment.essential:
        return WaveRole.ESSENTIAL, True
    if assignment.structure_class is CandidateStructureClass.BREAKPOINT:
        return WaveRole.BREAKPOINT, True
    if assignment.structure_class is CandidateStructureClass.EXTREME:
        return WaveRole.EXTREME, True
    if assignment.structure_class is CandidateStructureClass.STRUCTURAL:
        return WaveRole.STRUCTURAL, True
    return WaveRole.STABLE, False


def _keyframe_slot(candidate: WavetableCandidate, assignment) -> WavetableSlot:
    role, structural = _role_for_assignment(assignment)
    return WavetableSlot(
        schema_version=WAVETABLE_BUILD_SCHEMA_VERSION,
        position=assignment.position,
        stored_samples=candidate.stored_samples,
        role=role,
        origin=candidate.origin,
        generation_method=candidate.generation_method,
        metrics=candidate.metrics,
        source_candidate_ids=(candidate.candidate_id,),
        source_time_seconds=candidate.source_time_seconds,
        locked=assignment.required_locked or assignment.preference_locked,
        structural=structural,
        transition=False,
        redundant=False,
        evidence=(
            f"V8-D assignment {assignment.analysis_sha256}",
            f"candidate {candidate.candidate_sha256}",
        ),
        reason="Immutable V8-C keyframe preserved exactly at its V8-D position.",
    )


def _edge_hold_slot(
    position: int,
    candidate: WavetableCandidate,
    assignment,
) -> WavetableSlot:
    return WavetableSlot(
        schema_version=WAVETABLE_BUILD_SCHEMA_VERSION,
        position=position,
        stored_samples=candidate.stored_samples,
        role=WaveRole.REDUNDANT,
        origin=candidate.origin,
        generation_method=candidate.generation_method,
        metrics=candidate.metrics,
        source_candidate_ids=(candidate.candidate_id,),
        source_time_seconds=candidate.source_time_seconds,
        locked=False,
        structural=False,
        transition=False,
        redundant=True,
        evidence=(
            f"nearest edge keyframe assignment {assignment.analysis_sha256}",
            "edge hold preserves endpoint waveform without extrapolation",
        ),
        reason="Open edge position filled by deterministic endpoint hold.",
    )


def _transition_slot(
    position: int,
    left: WavetableCandidate,
    right: WavetableCandidate,
    wave: InterpolatedWave,
    source_time_seconds: float | None,
    evidence: Sequence[str],
) -> WavetableSlot:
    return WavetableSlot(
        schema_version=WAVETABLE_BUILD_SCHEMA_VERSION,
        position=position,
        stored_samples=wave.stored_samples,
        role=WaveRole.TRANSITION,
        origin=WaveOrigin.INTERPOLATED_TRANSITION,
        generation_method=wave.method,
        metrics=wave.metrics,
        source_candidate_ids=(left.candidate_id, right.candidate_id),
        source_time_seconds=source_time_seconds,
        locked=False,
        structural=False,
        transition=True,
        redundant=False,
        evidence=tuple(dict.fromkeys(tuple(evidence) + (f"interpolation {wave.analysis_sha256}",))),
        reason="Adaptive V8-E transition wave between immutable V8-D keyframes.",
    )


def _source_time(left: WavetableCandidate, right: WavetableCandidate, progress: float) -> float | None:
    if left.source_time_seconds is None or right.source_time_seconds is None:
        return None
    return _q(
        (1.0 - progress) * left.source_time_seconds
        + progress * right.source_time_seconds
    )


def _build_variant(
    request: WavetableBuildRequest,
    variant: WavetablePlacementVariant,
    interpolation_policy: InterpolationPolicy,
    density_policy: TransitionDensityPolicy,
    continuity_thresholds: ContinuityThresholds,
) -> tuple[WavetableBuild, WavetableTransitionMap, WavetableContinuityReport]:
    candidates = {item.candidate_id: item for item in request.candidates}
    assignments = tuple(sorted(variant.placement.assignments, key=lambda item: item.position))
    if not assignments:
        raise WavetableContractError("V8-D variant contains no keyframe assignments")
    slots: dict[int, WavetableSlot] = {}
    for assignment in assignments:
        candidate = candidates[assignment.candidate_id]
        slots[assignment.position] = _keyframe_slot(candidate, assignment)
    plans = plan_transition_density(request, variant, density_policy)
    plan_by_position = {
        position: (plan, raw_progress)
        for plan in plans
        for position, raw_progress in zip(plan.open_positions, plan.progress_values)
    }
    allowed_methods = tuple(request.policy.allowed_interpolation_methods)
    unsupported = tuple(method for method in allowed_methods if not method.is_interpolation)
    if unsupported:
        raise WavetableContractError("request contains a non-interpolation generation method")
    records: list[TransitionPositionRecord] = []
    variant_warnings = list(request.warnings)
    previous_key: tuple[str, str, float] | None = None
    for position in range(assignments[0].position):
        assignment = assignments[0]
        candidate = candidates[assignment.candidate_id]
        slot = _edge_hold_slot(position, candidate, assignment)
        slots[position] = slot
        records.append(
            TransitionPositionRecord(
                schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
                position=position,
                kind=TransitionPositionKind.EDGE_HOLD,
                source_candidate_ids=(candidate.candidate_id,),
                raw_progress=None,
                shaped_progress=None,
                method=None,
                stored_samples_sha256=slot.stored_samples_sha256,
                active_stage=False,
                evidence=("leading edge hold",),
                reason="Leading open position preserves the first keyframe.",
            )
        )
    for position in range(assignments[0].position + 1, assignments[-1].position):
        if position in slots:
            previous_key = None
            continue
        plan, raw_progress = plan_by_position[position]
        left = candidates[plan.left_candidate_id]
        right = candidates[plan.right_candidate_id]
        shaped = progression_value(
            raw_progress,
            request.policy.progression_curve,
            plan.complexity_score,
        )
        wave = select_interpolation_method(
            left,
            right,
            shaped,
            allowed_methods,
            interpolation_policy,
        )
        variant_warnings.extend(wave.warnings)
        key = (left.candidate_id, right.candidate_id, shaped)
        active = key != previous_key
        kind = (
            TransitionPositionKind.INTERPOLATED
            if active
            else TransitionPositionKind.REPEATED_STAGE
        )
        slot = _transition_slot(
            position,
            left,
            right,
            wave,
            _source_time(left, right, shaped),
            (
                f"density plan {plan.analysis_sha256}",
                f"raw progress {raw_progress:.12f}",
                f"shaped progress {shaped:.12f}",
            ),
        )
        slots[position] = slot
        records.append(
            TransitionPositionRecord(
                schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
                position=position,
                kind=kind,
                source_candidate_ids=(left.candidate_id, right.candidate_id),
                raw_progress=raw_progress,
                shaped_progress=shaped,
                method=wave.method,
                stored_samples_sha256=slot.stored_samples_sha256,
                active_stage=active,
                evidence=(
                    f"density plan {plan.analysis_sha256}",
                    f"interpolation {wave.analysis_sha256}",
                ),
                reason=(
                    "Active adaptive interpolation stage."
                    if active
                    else "Repeated adaptive stage used to retain a low transition density."
                ),
            )
        )
        previous_key = key
    for position in range(assignments[-1].position + 1, USER_POSITION_COUNT):
        assignment = assignments[-1]
        candidate = candidates[assignment.candidate_id]
        slot = _edge_hold_slot(position, candidate, assignment)
        slots[position] = slot
        records.append(
            TransitionPositionRecord(
                schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
                position=position,
                kind=TransitionPositionKind.EDGE_HOLD,
                source_candidate_ids=(candidate.candidate_id,),
                raw_progress=None,
                shaped_progress=None,
                method=None,
                stored_samples_sha256=slot.stored_samples_sha256,
                active_stage=False,
                evidence=("trailing edge hold",),
                reason="Trailing open position preserves the final keyframe.",
            )
        )
    if set(slots) != set(range(USER_POSITION_COUNT)):
        missing = sorted(set(range(USER_POSITION_COUNT)) - set(slots))
        raise WavetableContractError(f"V8-E left unfilled positions: {missing}")
    for assignment in assignments:
        candidate = candidates[assignment.candidate_id]
        if slots[assignment.position].stored_samples != candidate.stored_samples:
            raise WavetableContractError("V8-E changed an immutable V8-D keyframe")
    ordered_slots = tuple(slots[position] for position in range(USER_POSITION_COUNT))
    build = WavetableBuild(
        schema_version=WAVETABLE_BUILD_SCHEMA_VERSION,
        tool_version=request.tool_version,
        request_sha256=request.analysis_sha256,
        preflight_analysis_sha256=request.preflight_analysis_sha256,
        variant_id=variant.variant_id,
        status=WavetableBuildStatus.COMPLETE,
        slots=ordered_slots,
        fixed_tail=request.fixed_tail,
        blockers=(),
        warnings=tuple(dict.fromkeys(variant_warnings)),
        reason="CODE V8-E filled all 61 editable positions without materializing WCTD.",
    )
    continuity = analyze_wavetable_continuity(
        build,
        continuity_thresholds,
        intentional_break_positions=() if not request.policy.allow_intentional_breaks else tuple(
            item.position
            for item in ordered_slots[:-1]
            if item.role is WaveRole.BREAKPOINT
        ),
    )
    interval_fit_values = []
    for plan in plans:
        realized = 0.0 if plan.capacity == 0 else plan.active_step_count / plan.capacity
        interval_fit_values.append(1.0 - abs(realized - plan.target_active_fraction))
    density_fit = _q(
        1.0 if not interval_fit_values else sum(interval_fit_values) / len(interval_fit_values)
    )
    records_tuple = tuple(sorted(records, key=lambda item: item.position))
    transition_map = WavetableTransitionMap(
        schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
        v8d_variant_id=variant.variant_id,
        placement_sha256=variant.placement.analysis_sha256,
        density_policy=density_policy,
        intervals=plans,
        records=records_tuple,
        open_position_count=len(records_tuple),
        active_transition_count=sum(item.kind is TransitionPositionKind.INTERPOLATED for item in records_tuple),
        repeated_transition_count=sum(item.kind is TransitionPositionKind.REPEATED_STAGE for item in records_tuple),
        edge_hold_count=sum(item.kind is TransitionPositionKind.EDGE_HOLD for item in records_tuple),
        density_fit_score=density_fit,
        reason="Explicit V8-E transition and edge-hold map for every V8-D open position.",
    )
    return build, transition_map, continuity


def build_wavetable_transitions(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
    v8d_analysis: CodeV8DAnalysis,
    interpolation_policy: InterpolationPolicy = DEFAULT_INTERPOLATION_POLICY,
    density_policy: TransitionDensityPolicy = DEFAULT_TRANSITION_DENSITY_POLICY,
    continuity_thresholds: ContinuityThresholds = DEFAULT_CONTINUITY_THRESHOLDS,
) -> CodeV8EAnalysis:
    """Fill all V8-D open positions and rank complete V8-E transition builds."""

    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(v8b_analysis, CodeV8BAnalysis):
        raise WavetableContractError("v8b_analysis must be CodeV8BAnalysis")
    if not isinstance(v8c_analysis, CodeV8CAnalysis):
        raise WavetableContractError("v8c_analysis must be CodeV8CAnalysis")
    if not isinstance(v8d_analysis, CodeV8DAnalysis):
        raise WavetableContractError("v8d_analysis must be CodeV8DAnalysis")
    if not isinstance(interpolation_policy, InterpolationPolicy):
        raise WavetableContractError("interpolation_policy must be InterpolationPolicy")
    if not isinstance(density_policy, TransitionDensityPolicy):
        raise WavetableContractError("density_policy must be TransitionDensityPolicy")
    if not isinstance(continuity_thresholds, ContinuityThresholds):
        raise WavetableContractError("continuity_thresholds must be ContinuityThresholds")
    if v8b_analysis.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("V8-B analysis does not link to request")
    if v8c_analysis.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("V8-C analysis does not link to request")
    if v8c_analysis.v8b_analysis_sha256 != v8b_analysis.analysis_sha256:
        raise WavetableContractError("V8-C analysis does not link to V8-B")
    if v8d_analysis.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("V8-D analysis does not link to request")
    if v8d_analysis.v8b_analysis_sha256 != v8b_analysis.analysis_sha256:
        raise WavetableContractError("V8-D analysis does not link to V8-B")
    if v8d_analysis.v8c_analysis_sha256 != v8c_analysis.analysis_sha256:
        raise WavetableContractError("V8-D analysis does not link to V8-C")
    if v8d_analysis.status is not CodeV8DStatus.COMPLETE:
        return CodeV8EAnalysis(
            schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
            status=CodeV8EStatus.REJECTED,
            request_sha256=request.analysis_sha256,
            v8b_analysis_sha256=v8b_analysis.analysis_sha256,
            v8c_analysis_sha256=v8c_analysis.analysis_sha256,
            v8d_analysis_sha256=v8d_analysis.analysis_sha256,
            interpolation_policy=interpolation_policy,
            density_policy=density_policy,
            continuity_thresholds=continuity_thresholds,
            variants=(),
            primary_variant_id=None,
            build_set=None,
            warnings=tuple(dict.fromkeys(v8d_analysis.warnings)),
            blockers=tuple(dict.fromkeys(v8d_analysis.blockers)) or (
                "V8-D analysis is rejected",
            ),
            reason="CODE V8-E rejected the input before exposing partial transition builds.",
        )
    allowed = tuple(request.policy.allowed_interpolation_methods)
    if not any(method in interpolation_policy.method_priority for method in allowed):
        return CodeV8EAnalysis(
            schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
            status=CodeV8EStatus.REJECTED,
            request_sha256=request.analysis_sha256,
            v8b_analysis_sha256=v8b_analysis.analysis_sha256,
            v8c_analysis_sha256=v8c_analysis.analysis_sha256,
            v8d_analysis_sha256=v8d_analysis.analysis_sha256,
            interpolation_policy=interpolation_policy,
            density_policy=density_policy,
            continuity_thresholds=continuity_thresholds,
            variants=(),
            primary_variant_id=None,
            build_set=None,
            warnings=tuple(dict.fromkeys(v8d_analysis.warnings)),
            blockers=("request and V8-E policy have no common interpolation method",),
            reason="CODE V8-E rejected the interpolation policy without partial output.",
        )
    built: list[tuple[WavetablePlacementVariant, WavetableBuild, WavetableTransitionMap, WavetableContinuityReport, float]] = []
    failures: list[str] = []
    warnings = list(v8d_analysis.warnings)
    for variant in v8d_analysis.variants:
        try:
            build, transition_map, continuity = _build_variant(
                request,
                variant,
                interpolation_policy,
                density_policy,
                continuity_thresholds,
            )
        except WavetableContractError as exc:
            failures.append(f"{variant.variant_id}: {exc}")
            continue
        placement_score = variant.objective_score
        continuity_score = _q(
            0.65 * continuity.mean_continuity_score
            + 0.35 * continuity.minimum_continuity_score
        )
        objective = _q(
            0.50 * continuity_score
            + 0.25 * placement_score
            + 0.20 * transition_map.density_fit_score
            + 0.05 * (1.0 if continuity.status is not ContinuityStatus.FAIL else 0.0)
        )
        warnings.extend(build.warnings)
        warnings.extend(continuity.warnings)
        if continuity.status is ContinuityStatus.FAIL:
            failures.extend(
                f"{variant.variant_id}: {blocker}" for blocker in continuity.blockers
            )
            continue
        built.append((variant, build, transition_map, continuity, objective))
    if not built:
        return CodeV8EAnalysis(
            schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
            status=CodeV8EStatus.REJECTED,
            request_sha256=request.analysis_sha256,
            v8b_analysis_sha256=v8b_analysis.analysis_sha256,
            v8c_analysis_sha256=v8c_analysis.analysis_sha256,
            v8d_analysis_sha256=v8d_analysis.analysis_sha256,
            interpolation_policy=interpolation_policy,
            density_policy=density_policy,
            continuity_thresholds=continuity_thresholds,
            variants=(),
            primary_variant_id=None,
            build_set=None,
            warnings=tuple(dict.fromkeys(warnings)),
            blockers=tuple(dict.fromkeys(failures)) or (
                "no complete V8-E transition build was produced",
            ),
            reason="CODE V8-E rejected all variants without exposing partial builds.",
        )
    built.sort(
        key=lambda item: (
            -item[4],
            item[0].rank,
            item[0].variant_id,
            item[1].analysis_sha256,
        )
    )
    variants: list[CodeV8EVariant] = []
    for rank, (v8d_variant, build, transition_map, continuity, objective) in enumerate(built, 1):
        variants.append(
            CodeV8EVariant(
                schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
                variant_id=build.variant_id,
                rank=rank,
                v8d_variant_id=v8d_variant.variant_id,
                v8d_rank=v8d_variant.rank,
                build=build,
                transition_map=transition_map,
                continuity=continuity,
                objective_score=objective,
                placement_score=v8d_variant.objective_score,
                density_score=transition_map.density_fit_score,
                continuity_score=_q(
                    0.65 * continuity.mean_continuity_score
                    + 0.35 * continuity.minimum_continuity_score
                ),
                warnings=tuple(dict.fromkeys(build.warnings + continuity.warnings)),
                reason=(
                    "Primary V8-E transition build selected by continuity, placement and density evidence."
                    if rank == 1
                    else "Alternative V8-E transition build retained with complete evidence."
                ),
            )
        )
    primary_id = variants[0].variant_id
    build_set = WavetableBuildSet(
        schema_version=WAVETABLE_BUILD_SCHEMA_VERSION,
        request_sha256=request.analysis_sha256,
        builds=tuple(item.build for item in variants),
        primary_variant_id=primary_id,
        reason="Complete V8-E 61-slot build set without WCTD materialization.",
    )
    return CodeV8EAnalysis(
        schema_version=WAVETABLE_BUILDER_SCHEMA_VERSION,
        status=CodeV8EStatus.COMPLETE,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        v8d_analysis_sha256=v8d_analysis.analysis_sha256,
        interpolation_policy=interpolation_policy,
        density_policy=density_policy,
        continuity_thresholds=continuity_thresholds,
        variants=tuple(variants),
        primary_variant_id=primary_id,
        build_set=build_set,
        warnings=tuple(dict.fromkeys(warnings + failures)),
        blockers=(),
        reason="CODE V8-E filled and evaluated all 61 editable positions while deferring WCTD and hardware gates.",
    )


__all__ = [
    "DEFAULT_TRANSITION_DENSITY_POLICY",
    "WAVETABLE_BUILDER_SCHEMA_VERSION",
    "CodeV8EAnalysis",
    "CodeV8EStatus",
    "CodeV8EVariant",
    "TransitionDensityPolicy",
    "TransitionIntervalPlan",
    "TransitionPositionKind",
    "TransitionPositionRecord",
    "WavetableTransitionMap",
    "build_wavetable_transitions",
    "plan_transition_density",
]
