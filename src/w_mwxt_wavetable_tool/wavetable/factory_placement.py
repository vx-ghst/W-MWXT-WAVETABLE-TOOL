from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from ..profiles import OptimizationProfile, weights_for_profile
from .deduplication import CodeV8BAnalysis
from .models import (
    ConstraintStrength,
    USER_POSITION_COUNT,
    WavetableBuildRequest,
    WavetableContractError,
)
from .ordering import (
    ConstraintOutcome,
    ConstraintOutcomeStatus,
    PlacementConstraintKind,
    WAVETABLE_ORDERING_SCHEMA_VERSION,
)
from .placement import (
    PlacementScore,
    PlacementStatus,
    PositionAssignment,
    WavetablePlacement,
)
from .selection import CodeV8CAnalysis
from .transition_planner import AdaptiveSlotBudgetPlan
from .usefulness import CandidateStructureClass
from .variants import (
    CodeV8DAnalysis,
    CodeV8DStatus,
    WAVETABLE_VARIANTS_SCHEMA_VERSION,
    WavetablePlacementVariant,
)

FACTORY_PLACEMENT_SCHEMA_VERSION = 1
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


def _entries(values: Sequence[str], *, name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence")
    result = tuple(values)
    if not allow_empty and not result:
        raise WavetableContractError(f"{name} must not be empty")
    if any(not isinstance(item, str) or not item or item.strip() != item for item in result):
        raise WavetableContractError(f"{name} must contain normalized strings")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


class FactoryPlacementStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


class FactoryZone(str, Enum):
    STABLE = "stable_playable"
    EVOLUTION = "main_evolution"
    EXTREME = "extreme"


_ZONE_RANGES: dict[FactoryZone, tuple[int, int]] = {
    FactoryZone.STABLE: (0, 19),
    FactoryZone.EVOLUTION: (20, 44),
    FactoryZone.EXTREME: (45, 60),
}


@dataclass(frozen=True, slots=True)
class FactoryZoneTarget:
    schema_version: int
    zone: FactoryZone
    brightness: float
    density: float
    saturation: float
    bass_stability: float

    def __post_init__(self) -> None:
        if self.schema_version != FACTORY_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported Factory zone-target schema version")
        if not isinstance(self.zone, FactoryZone):
            raise WavetableContractError("zone must be FactoryZone")
        for name in ("brightness", "density", "saturation", "bass_stability"):
            _ratio(getattr(self, name), name=name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "zone": self.zone.value,
            "brightness": self.brightness,
            "density": self.density,
            "saturation": self.saturation,
            "bass_stability": self.bass_stability,
        }


@dataclass(frozen=True, slots=True)
class PlacementProfilePolicy:
    schema_version: int
    profile: OptimizationProfile
    factory_enabled: bool
    brightness_weight: float
    density_weight: float
    saturation_weight: float
    bass_stability_weight: float
    generic_ordering_weight: float
    trajectory_weight: float
    adjacency_weight: float
    source_fidelity_weight: float
    zone_count_weight: float
    zone_keyframe_fractions: tuple[float, float, float]
    targets: tuple[FactoryZoneTarget, FactoryZoneTarget, FactoryZoneTarget]
    honor_preference_locks: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != FACTORY_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported placement-profile schema version")
        if not isinstance(self.profile, OptimizationProfile):
            raise WavetableContractError("profile must be OptimizationProfile")
        for name in ("factory_enabled", "honor_preference_locks"):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        feature_weights = (
            self.brightness_weight,
            self.density_weight,
            self.saturation_weight,
            self.bass_stability_weight,
        )
        if not math.isclose(sum(feature_weights), 1.0, abs_tol=1e-9):
            raise WavetableContractError("profile feature weights must sum to one")
        objective_weights = (
            self.generic_ordering_weight,
            self.trajectory_weight,
            self.adjacency_weight,
            self.source_fidelity_weight,
            self.zone_count_weight,
        )
        if not math.isclose(sum(objective_weights), 1.0, abs_tol=1e-9):
            raise WavetableContractError("profile placement weights must sum to one")
        for index, value in enumerate(feature_weights + objective_weights):
            _ratio(value, name=f"policy weight {index}")
        fractions = tuple(float(value) for value in self.zone_keyframe_fractions)
        object.__setattr__(self, "zone_keyframe_fractions", fractions)
        if len(fractions) != 3 or any(value < 0.0 for value in fractions):
            raise WavetableContractError("zone_keyframe_fractions must contain three non-negative values")
        if not math.isclose(sum(fractions), 1.0, abs_tol=1e-9):
            raise WavetableContractError("zone_keyframe_fractions must sum to one")
        targets = tuple(self.targets)
        object.__setattr__(self, "targets", targets)
        if tuple(item.zone for item in targets) != tuple(FactoryZone):
            raise WavetableContractError("targets must cover Factory zones in canonical order")
        if not isinstance(self.reason, str) or not self.reason or self.reason.strip() != self.reason:
            raise WavetableContractError("reason must be normalized")

    @property
    def feature_weights(self) -> dict[str, float]:
        return {
            "brightness": self.brightness_weight,
            "density": self.density_weight,
            "saturation": self.saturation_weight,
            "bass_stability": self.bass_stability_weight,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile.value,
            "factory_enabled": self.factory_enabled,
            "feature_weights": self.feature_weights,
            "generic_ordering_weight": self.generic_ordering_weight,
            "trajectory_weight": self.trajectory_weight,
            "adjacency_weight": self.adjacency_weight,
            "source_fidelity_weight": self.source_fidelity_weight,
            "zone_count_weight": self.zone_count_weight,
            "zone_keyframe_fractions": list(self.zone_keyframe_fractions),
            "targets": [item.to_dict() for item in self.targets],
            "honor_preference_locks": self.honor_preference_locks,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


_PROFILE_TARGETS: dict[OptimizationProfile, tuple[tuple[float, float, float, float], ...]] = {
    OptimizationProfile.BASS_SUB: ((0.12, 0.22, 0.12, 0.92), (0.34, 0.48, 0.34, 0.85), (0.58, 0.72, 0.66, 0.72)),
    OptimizationProfile.LEAD: ((0.30, 0.34, 0.18, 0.58), (0.62, 0.64, 0.48, 0.52), (0.90, 0.86, 0.78, 0.42)),
    OptimizationProfile.PAD: ((0.22, 0.30, 0.14, 0.66), (0.52, 0.62, 0.38, 0.60), (0.76, 0.82, 0.62, 0.52)),
    OptimizationProfile.BELL_FM: ((0.34, 0.30, 0.20, 0.46), (0.70, 0.68, 0.54, 0.40), (0.96, 0.92, 0.86, 0.30)),
    OptimizationProfile.VOCAL_CHOIR: ((0.24, 0.34, 0.12, 0.62), (0.50, 0.62, 0.34, 0.58), (0.74, 0.82, 0.60, 0.48)),
    OptimizationProfile.TEXTURE: ((0.28, 0.38, 0.24, 0.48), (0.64, 0.76, 0.58, 0.42), (0.92, 0.96, 0.90, 0.32)),
    OptimizationProfile.DRONE: ((0.16, 0.26, 0.10, 0.88), (0.36, 0.50, 0.28, 0.82), (0.62, 0.72, 0.58, 0.70)),
    OptimizationProfile.PERCUSSIVE: ((0.30, 0.28, 0.24, 0.44), (0.68, 0.62, 0.56, 0.38), (0.94, 0.86, 0.88, 0.28)),
    OptimizationProfile.EXPERIMENTAL: ((0.20, 0.34, 0.28, 0.46), (0.62, 0.76, 0.68, 0.38), (0.98, 0.98, 0.98, 0.24)),
}


_PROFILE_ZONE_FRACTIONS: dict[OptimizationProfile, tuple[float, float, float]] = {
    OptimizationProfile.BASS_SUB: (0.42, 0.40, 0.18),
    OptimizationProfile.LEAD: (0.28, 0.44, 0.28),
    OptimizationProfile.PAD: (0.34, 0.46, 0.20),
    OptimizationProfile.BELL_FM: (0.24, 0.42, 0.34),
    OptimizationProfile.VOCAL_CHOIR: (0.34, 0.46, 0.20),
    OptimizationProfile.TEXTURE: (0.24, 0.44, 0.32),
    OptimizationProfile.DRONE: (0.42, 0.42, 0.16),
    OptimizationProfile.PERCUSSIVE: (0.26, 0.42, 0.32),
    OptimizationProfile.EXPERIMENTAL: (0.20, 0.42, 0.38),
}


def placement_profile_policy(
    profile: OptimizationProfile | str,
    *,
    factory_enabled: bool = True,
) -> PlacementProfilePolicy:
    try:
        selected = OptimizationProfile(profile)
    except (TypeError, ValueError) as exc:
        raise WavetableContractError("profile must be a supported OptimizationProfile") from exc
    weights = weights_for_profile(selected)
    raw_feature = {
        "brightness": weights.high_band + 0.55 * weights.mid_band + 0.45 * weights.spectral_fidelity,
        "density": weights.perceptual + weights.h2 + weights.h3 + 0.55 * weights.spectral_fidelity,
        "saturation": weights.aliasing + weights.ringing + 0.70 * weights.high_band,
        "bass_stability": weights.fundamental + weights.low_band + weights.amplitude + weights.phase_fidelity,
    }
    feature_total = sum(raw_feature.values())
    feature = {name: value / feature_total for name, value in raw_feature.items()}
    targets = tuple(
        FactoryZoneTarget(
            schema_version=FACTORY_PLACEMENT_SCHEMA_VERSION,
            zone=zone,
            brightness=values[0],
            density=values[1],
            saturation=values[2],
            bass_stability=values[3],
        )
        for zone, values in zip(FactoryZone, _PROFILE_TARGETS[selected])
    )
    return PlacementProfilePolicy(
        schema_version=FACTORY_PLACEMENT_SCHEMA_VERSION,
        profile=selected,
        factory_enabled=factory_enabled,
        brightness_weight=_q(feature["brightness"]),
        density_weight=_q(feature["density"]),
        saturation_weight=_q(feature["saturation"]),
        bass_stability_weight=_q(1.0 - _q(feature["brightness"]) - _q(feature["density"]) - _q(feature["saturation"])),
        generic_ordering_weight=0.24,
        trajectory_weight=0.30,
        adjacency_weight=0.18,
        source_fidelity_weight=0.13,
        zone_count_weight=0.15,
        zone_keyframe_fractions=_PROFILE_ZONE_FRACTIONS[selected],
        targets=targets,  # type: ignore[arg-type]
        honor_preference_locks=True,
        reason=(
            "Versioned profile-to-placement policy. Factory Style means three-zone keyframe placement; "
            "the metrics are engineering proxies and do not claim historical Waldorf reconstruction."
        ),
    )


@dataclass(frozen=True, slots=True)
class CandidateTrajectoryFeatures:
    schema_version: int
    candidate_id: str
    brightness: float
    density: float
    saturation: float
    bass_stability: float
    structure_class: CandidateStructureClass

    def __post_init__(self) -> None:
        if self.schema_version != FACTORY_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported candidate-trajectory schema version")
        if not isinstance(self.candidate_id, str) or not self.candidate_id:
            raise WavetableContractError("candidate_id must not be empty")
        for name in ("brightness", "density", "saturation", "bass_stability"):
            _ratio(getattr(self, name), name=name)
        if not isinstance(self.structure_class, CandidateStructureClass):
            raise WavetableContractError("structure_class must be CandidateStructureClass")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "brightness": self.brightness,
            "density": self.density,
            "saturation": self.saturation,
            "bass_stability": self.bass_stability,
            "structure_class": self.structure_class.value,
        }


@dataclass(frozen=True, slots=True)
class FactoryZoneAssignment:
    schema_version: int
    candidate_id: str
    order_index: int
    zone: FactoryZone
    position: int
    original_position: int
    zone_fit_score: float
    trajectory_error: float
    required_lock: bool
    preference_lock: bool
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != FACTORY_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported Factory zone-assignment schema version")
        if not isinstance(self.candidate_id, str) or not self.candidate_id:
            raise WavetableContractError("candidate_id must not be empty")
        if isinstance(self.order_index, bool) or not isinstance(self.order_index, int) or self.order_index < 0:
            raise WavetableContractError("order_index must be non-negative")
        if not isinstance(self.zone, FactoryZone):
            raise WavetableContractError("zone must be FactoryZone")
        for name in ("position", "original_position"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < USER_POSITION_COUNT:
                raise WavetableContractError(f"{name} must be in 0..60")
        start, end = _ZONE_RANGES[self.zone]
        if not start <= self.position <= end:
            raise WavetableContractError("position lies outside assigned Factory zone")
        _ratio(self.zone_fit_score, name="zone_fit_score")
        _ratio(self.trajectory_error, name="trajectory_error")
        for name in ("required_lock", "preference_lock"):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        object.__setattr__(self, "evidence", _entries(self.evidence, name="evidence", allow_empty=False))
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def display_position(self) -> int:
        return self.position + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "order_index": self.order_index,
            "zone": self.zone.value,
            "position": self.position,
            "display_position": self.display_position,
            "original_position": self.original_position,
            "display_original_position": self.original_position + 1,
            "zone_fit_score": self.zone_fit_score,
            "trajectory_error": self.trajectory_error,
            "required_lock": self.required_lock,
            "preference_lock": self.preference_lock,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class FactoryPlacementVariant:
    schema_version: int
    variant_id: str
    rank: int
    source_v8d_variant_sha256: str
    profiled_variant: WavetablePlacementVariant
    assignments: tuple[FactoryZoneAssignment, ...]
    zone_counts: tuple[int, int, int]
    trajectory_score: float
    adjacency_score: float
    source_fidelity_score: float
    zone_count_score: float
    objective_score: float
    moved_candidate_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != FACTORY_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported Factory placement-variant schema version")
        if not isinstance(self.profiled_variant, WavetablePlacementVariant):
            raise WavetableContractError("profiled_variant must be WavetablePlacementVariant")
        if self.variant_id != self.profiled_variant.variant_id:
            raise WavetableContractError("variant_id disagrees with profiled variant")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise WavetableContractError("rank must be positive")
        _sha256(self.source_v8d_variant_sha256, name="source_v8d_variant_sha256")
        assignments = tuple(self.assignments)
        object.__setattr__(self, "assignments", assignments)
        if tuple(item.order_index for item in assignments) != tuple(range(len(assignments))):
            raise WavetableContractError("Factory assignments require canonical order indices")
        if tuple(item.position for item in assignments) != tuple(sorted(item.position for item in assignments)):
            raise WavetableContractError("Factory positions must increase with order")
        counts = tuple(self.zone_counts)
        object.__setattr__(self, "zone_counts", counts)
        if len(counts) != 3 or sum(counts) != len(assignments):
            raise WavetableContractError("zone_counts disagree with assignments")
        observed = tuple(sum(item.zone is zone for item in assignments) for zone in FactoryZone)
        if counts != observed:
            raise WavetableContractError("zone_counts disagree with assigned zones")
        for name in (
            "trajectory_score",
            "adjacency_score",
            "source_fidelity_score",
            "zone_count_score",
            "objective_score",
        ):
            _ratio(getattr(self, name), name=name)
        object.__setattr__(self, "moved_candidate_ids", _entries(self.moved_candidate_ids, name="moved_candidate_ids"))
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        if not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "rank": self.rank,
            "source_v8d_variant_sha256": self.source_v8d_variant_sha256,
            "profiled_variant": self.profiled_variant.to_dict(),
            "assignments": [item.to_dict() for item in self.assignments],
            "zone_counts": {
                zone.value: count for zone, count in zip(FactoryZone, self.zone_counts)
            },
            "trajectory_score": self.trajectory_score,
            "adjacency_score": self.adjacency_score,
            "source_fidelity_score": self.source_fidelity_score,
            "zone_count_score": self.zone_count_score,
            "objective_score": self.objective_score,
            "moved_candidate_ids": list(self.moved_candidate_ids),
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
class FactoryPlacementAnalysis:
    schema_version: int
    status: FactoryPlacementStatus
    request_sha256: str
    v8b_analysis_sha256: str
    v8c_analysis_sha256: str
    v8d_analysis_sha256: str
    slot_budget_sha256: str
    policy: PlacementProfilePolicy
    applied: bool
    variants: tuple[FactoryPlacementVariant, ...]
    primary_variant_id: str | None
    profiled_v8d_analysis: CodeV8DAnalysis | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != FACTORY_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported Factory placement-analysis schema version")
        if not isinstance(self.status, FactoryPlacementStatus):
            raise WavetableContractError("status must be FactoryPlacementStatus")
        for name in (
            "request_sha256",
            "v8b_analysis_sha256",
            "v8c_analysis_sha256",
            "v8d_analysis_sha256",
            "slot_budget_sha256",
        ):
            _sha256(getattr(self, name), name=name)
        if not isinstance(self.policy, PlacementProfilePolicy):
            raise WavetableContractError("policy must be PlacementProfilePolicy")
        if not isinstance(self.applied, bool):
            raise WavetableContractError("applied must be boolean")
        object.__setattr__(self, "variants", tuple(self.variants))
        if any(not isinstance(item, FactoryPlacementVariant) for item in self.variants):
            raise WavetableContractError("variants must contain FactoryPlacementVariant values")
        if len({item.variant_id for item in self.variants}) != len(self.variants):
            raise WavetableContractError("Factory placement variant IDs must be unique")
        if self.variants and tuple(item.rank for item in self.variants) != tuple(
            range(1, len(self.variants) + 1)
        ):
            raise WavetableContractError("Factory placement ranks must be canonical")
        if self.variants and tuple(item.objective_score for item in self.variants) != tuple(
            sorted((item.objective_score for item in self.variants), reverse=True)
        ):
            raise WavetableContractError("Factory placement variants must be ranked by score")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        object.__setattr__(self, "blockers", _entries(self.blockers, name="blockers"))
        if self.status is FactoryPlacementStatus.COMPLETE:
            if self.blockers or not self.variants or self.profiled_v8d_analysis is None:
                raise WavetableContractError("complete Factory placement requires variants without blockers")
            if self.primary_variant_id != self.variants[0].variant_id:
                raise WavetableContractError("primary Factory variant must rank first")
            if self.profiled_v8d_analysis.primary_variant_id != self.primary_variant_id:
                raise WavetableContractError("profiled V8-D primary variant disagrees")
        else:
            if not self.blockers:
                raise WavetableContractError("rejected Factory placement requires blockers")
            if self.variants or self.primary_variant_id is not None or self.profiled_v8d_analysis is not None:
                raise WavetableContractError("rejected Factory placement cannot expose partial output")
        if not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def primary_variant(self) -> FactoryPlacementVariant | None:
        return self.variants[0] if self.variants else None

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "v8b_analysis_sha256": self.v8b_analysis_sha256,
            "v8c_analysis_sha256": self.v8c_analysis_sha256,
            "v8d_analysis_sha256": self.v8d_analysis_sha256,
            "slot_budget_sha256": self.slot_budget_sha256,
            "policy": self.policy.to_dict(),
            "applied": self.applied,
            "variants": [item.to_dict() for item in self.variants],
            "primary_variant_id": self.primary_variant_id,
            "profiled_v8d_analysis": None if self.profiled_v8d_analysis is None else self.profiled_v8d_analysis.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "factory_zones": {
                    "stable_playable": [1, 20],
                    "main_evolution": [21, 45],
                    "extreme": [46, 61],
                },
                "interpolates_transitions": False,
                "shapes_samples": False,
                "consolidates_physical_waves": False,
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
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _zone_for_position(position: int) -> FactoryZone:
    for zone, (start, end) in _ZONE_RANGES.items():
        if start <= position <= end:
            return zone
    raise WavetableContractError("position is outside Factory zones")


def _candidate_features(request: WavetableBuildRequest, v8b: CodeV8BAnalysis) -> dict[str, CandidateTrajectoryFeatures]:
    structure = {item.candidate_id: item for item in v8b.structure.candidates}
    result: dict[str, CandidateTrajectoryFeatures] = {}
    for candidate in request.candidates:
        item = structure[candidate.candidate_id]
        metrics = candidate.metrics
        density = _q(
            0.45 * metrics.harmonic_richness
            + 0.30 * metrics.perceptual_novelty
            + 0.25 * item.shape_metrics.complexity
        )
        saturation = _q(
            0.40 * metrics.brightness
            + 0.35 * metrics.harmonic_richness
            + 0.25 * (1.0 - metrics.stability_score)
        )
        bass_stability = _q(0.60 * metrics.bass_power + 0.40 * metrics.stability_score)
        result[candidate.candidate_id] = CandidateTrajectoryFeatures(
            schema_version=FACTORY_PLACEMENT_SCHEMA_VERSION,
            candidate_id=candidate.candidate_id,
            brightness=_q(metrics.brightness),
            density=density,
            saturation=saturation,
            bass_stability=bass_stability,
            structure_class=item.structure_class,
        )
    return result


def _zone_fit(features: CandidateTrajectoryFeatures, target: FactoryZoneTarget, policy: PlacementProfilePolicy) -> tuple[float, float]:
    error = (
        policy.brightness_weight * abs(features.brightness - target.brightness)
        + policy.density_weight * abs(features.density - target.density)
        + policy.saturation_weight * abs(features.saturation - target.saturation)
        + policy.bass_stability_weight * abs(features.bass_stability - target.bass_stability)
    )
    bonus = 0.0
    if target.zone is FactoryZone.STABLE and features.structure_class is CandidateStructureClass.STABLE:
        bonus = 0.08
    elif target.zone is FactoryZone.EVOLUTION and features.structure_class in {
        CandidateStructureClass.TRANSITION,
        CandidateStructureClass.BREAKPOINT,
    }:
        bonus = 0.08
    elif target.zone is FactoryZone.EXTREME and features.structure_class is CandidateStructureClass.EXTREME:
        bonus = 0.10
    fit = max(0.0, min(1.0, 1.0 - error + bonus))
    return _q(fit), _q(min(1.0, error))


def _budget_fractions(slot_budget: AdaptiveSlotBudgetPlan) -> tuple[float, float, float]:
    stable = 0
    evolution = 0
    extreme = 0
    for item in slot_budget.budgets:
        if item.kind.value in {"attack", "establishment", "sustain", "redundancy"}:
            stable += item.slot_count
        elif item.kind.value in {"evolution", "disappearance"}:
            evolution += item.slot_count
        elif item.kind.value in {"saturation", "noise"}:
            extreme += item.slot_count
    total = stable + evolution + extreme
    if total <= 0:
        return (20 / 61, 25 / 61, 16 / 61)
    return (stable / total, evolution / total, extreme / total)


def _desired_counts(count: int, policy: PlacementProfilePolicy, slot_budget: AdaptiveSlotBudgetPlan) -> tuple[int, int, int]:
    if count <= 0:
        return (0, 0, 0)
    budget = _budget_fractions(slot_budget)
    blended = tuple(0.70 * left + 0.30 * right for left, right in zip(policy.zone_keyframe_fractions, budget))
    minimum = 1 if count >= 3 else 0
    capacities = (20, 25, 16)
    raw = [count * value for value in blended]
    result = [min(capacities[index], max(minimum, int(math.floor(raw[index])))) for index in range(3)]
    while sum(result) > count:
        candidates = [index for index in range(3) if result[index] > minimum]
        if not candidates:
            break
        index = max(candidates, key=lambda value: (result[value] - raw[value], result[value], -value))
        result[index] -= 1
    while sum(result) < count:
        candidates = [index for index in range(3) if result[index] < capacities[index]]
        if not candidates:
            raise WavetableContractError("Factory zone capacities cannot hold selected keyframes")
        index = max(candidates, key=lambda value: (raw[value] - result[value], capacities[value] - result[value], -value))
        result[index] += 1
    return tuple(result)  # type: ignore[return-value]


def _select_zone_counts(
    ordered_ids: Sequence[str],
    fit: Mapping[str, Mapping[FactoryZone, tuple[float, float]]],
    required_zone: Mapping[str, FactoryZone],
    desired: tuple[int, int, int],
) -> tuple[int, int, int]:
    count = len(ordered_ids)
    capacities = (20, 25, 16)
    minimum = 1 if count >= 3 else 0
    best: tuple[float, tuple[int, int, int]] | None = None
    for stable_count in range(minimum, min(capacities[0], count) + 1):
        remaining = count - stable_count
        for evolution_count in range(minimum, min(capacities[1], remaining) + 1):
            extreme_count = remaining - evolution_count
            if extreme_count < minimum or extreme_count > capacities[2]:
                continue
            counts = (stable_count, evolution_count, extreme_count)
            score = 0.0
            feasible = True
            for index, candidate_id in enumerate(ordered_ids):
                zone = (
                    FactoryZone.STABLE
                    if index < stable_count
                    else FactoryZone.EVOLUTION
                    if index < stable_count + evolution_count
                    else FactoryZone.EXTREME
                )
                locked = required_zone.get(candidate_id)
                if locked is not None and locked is not zone:
                    feasible = False
                    break
                score += fit[candidate_id][zone][0]
            if not feasible:
                continue
            count_error = sum(abs(current - target) for current, target in zip(counts, desired)) / max(1, count)
            score = score / max(1, count) - 0.20 * count_error
            candidate = (_q(score), counts)
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and candidate[1] < best[1]):
                best = candidate
    if best is None:
        raise WavetableContractError("required position locks make Factory zones infeasible")
    return best[1]


def _assign_zone_positions(
    candidate_ids: Sequence[str],
    zone: FactoryZone,
    original_positions: Mapping[str, int],
    required_positions: Mapping[str, int],
    preference_positions: Mapping[str, int],
    honor_preferences: bool,
) -> tuple[dict[str, int], tuple[str, ...]]:
    if not candidate_ids:
        return {}, ()
    start, end = _ZONE_RANGES[zone]
    positions = tuple(range(start, end + 1))
    count = len(candidate_ids)
    if count > len(positions):
        raise WavetableContractError(f"too many keyframes for {zone.value} zone")
    ideals = {
        candidate_id: (
            (start + end) / 2.0
            if count == 1
            else start + index * (end - start) / (count - 1)
        )
        for index, candidate_id in enumerate(candidate_ids)
    }
    inf = float("inf")
    dp = [[inf] * (len(positions) + 1) for _ in range(count + 1)]
    parent: list[list[tuple[int, bool] | None]] = [[None] * (len(positions) + 1) for _ in range(count + 1)]
    dp[0] = [0.0] * (len(positions) + 1)
    for i in range(1, count + 1):
        candidate_id = candidate_ids[i - 1]
        required = required_positions.get(candidate_id)
        preferred = preference_positions.get(candidate_id) if honor_preferences else None
        for j in range(1, len(positions) + 1):
            position = positions[j - 1]
            if dp[i][j - 1] < dp[i][j]:
                dp[i][j] = dp[i][j - 1]
                parent[i][j] = (j - 1, False)
            if dp[i - 1][j - 1] == inf:
                continue
            if required is not None and position != required:
                continue
            cost = abs(position - ideals[candidate_id]) / max(1, end - start)
            cost += 0.20 * abs(position - original_positions[candidate_id]) / 60.0
            if preferred is not None:
                cost += 0.0 if position == preferred else 0.10
            candidate_cost = dp[i - 1][j - 1] + cost
            if candidate_cost < dp[i][j] - 1e-12:
                dp[i][j] = candidate_cost
                parent[i][j] = (j - 1, True)
    if dp[count][len(positions)] == inf:
        raise WavetableContractError(f"position locks are infeasible inside {zone.value} zone")
    result: dict[str, int] = {}
    i, j = count, len(positions)
    while i > 0:
        step = parent[i][j]
        if step is None:
            raise WavetableContractError("Factory placement solver lost its traceback")
        previous_j, assigned = step
        if assigned:
            result[candidate_ids[i - 1]] = positions[j - 1]
            i -= 1
        j = previous_j
    warnings = tuple(
        f"preference lock not honored for {candidate_id}"
        for candidate_id in candidate_ids
        if candidate_id in preference_positions and result[candidate_id] != preference_positions[candidate_id]
    )
    return result, warnings


def _constraint_outcomes(
    request: WavetableBuildRequest,
    candidate_ids: Sequence[str],
    positions: Mapping[str, int],
    honor_preference_locks: bool,
) -> tuple[ConstraintOutcome, ...]:
    selected = set(candidate_ids)
    outcomes: list[ConstraintOutcome] = []
    for index, lock in enumerate(request.position_locks):
        if lock.candidate_id not in selected:
            status = ConstraintOutcomeStatus.BLOCKED if lock.strength is ConstraintStrength.REQUIRED else ConstraintOutcomeStatus.NOT_APPLICABLE
            reason = "Position lock references a candidate outside selection."
        elif lock.strength is ConstraintStrength.PREFERENCE and not honor_preference_locks:
            status = ConstraintOutcomeStatus.NOT_APPLICABLE
            reason = "Preference locks are disabled by profile policy."
        elif positions[lock.candidate_id] == lock.position:
            status = ConstraintOutcomeStatus.SATISFIED
            reason = "Factory placement preserved the requested lock."
        else:
            status = ConstraintOutcomeStatus.BLOCKED if lock.strength is ConstraintStrength.REQUIRED else ConstraintOutcomeStatus.VIOLATED
            reason = "Factory placement could not honor the preferred position."
        outcomes.append(
            ConstraintOutcome(
                schema_version=WAVETABLE_ORDERING_SCHEMA_VERSION,
                constraint_id=f"position-lock-{index:03d}",
                kind=PlacementConstraintKind.POSITION_LOCK,
                strength=lock.strength,
                candidate_ids=(lock.candidate_id,),
                target_position=lock.position,
                status=status,
                evidence=(lock.reason, "V8-H Factory placement constraint evaluation"),
                reason=reason,
            )
        )
    for index, constraint in enumerate(request.chronology_constraints):
        applicable = constraint.before_candidate_id in selected and constraint.after_candidate_id in selected
        if not applicable:
            status = ConstraintOutcomeStatus.BLOCKED if constraint.strength is ConstraintStrength.REQUIRED else ConstraintOutcomeStatus.NOT_APPLICABLE
            reason = "Chronology references a candidate outside selection."
        elif positions[constraint.before_candidate_id] < positions[constraint.after_candidate_id]:
            status = ConstraintOutcomeStatus.SATISFIED
            reason = "Factory placement preserves chronological order."
        else:
            status = ConstraintOutcomeStatus.BLOCKED if constraint.strength is ConstraintStrength.REQUIRED else ConstraintOutcomeStatus.VIOLATED
            reason = "Factory placement violates the chronology preference."
        outcomes.append(
            ConstraintOutcome(
                schema_version=WAVETABLE_ORDERING_SCHEMA_VERSION,
                constraint_id=f"chronology-{index:03d}",
                kind=PlacementConstraintKind.CHRONOLOGY,
                strength=constraint.strength,
                candidate_ids=(constraint.before_candidate_id, constraint.after_candidate_id),
                target_position=None,
                status=status,
                evidence=(constraint.reason, "V8-H Factory placement constraint evaluation"),
                reason=reason,
            )
        )
    return tuple(outcomes)


def _constraint_score(outcomes: Sequence[ConstraintOutcome], kind: PlacementConstraintKind) -> float:
    applicable = [item for item in outcomes if item.kind is kind and item.status is not ConstraintOutcomeStatus.NOT_APPLICABLE]
    if not applicable:
        return 1.0
    score = 0.0
    for item in applicable:
        if item.status is ConstraintOutcomeStatus.SATISFIED:
            score += 1.0
        elif item.strength is ConstraintStrength.PREFERENCE:
            score += 0.25
    return _q(score / len(applicable))


def _spacing_score(positions: Sequence[int]) -> tuple[float, float, int]:
    ordered = tuple(sorted(positions))
    if len(ordered) <= 1:
        return 1.0, 0.0, 0
    gaps = tuple(right - left for left, right in zip(ordered, ordered[1:]))
    mean_gap = sum(gaps) / len(gaps)
    ideal = 60 / (len(ordered) - 1)
    deviation = sum(abs(gap - ideal) for gap in gaps) / len(gaps)
    return _q(max(0.0, 1.0 - deviation / max(1.0, ideal))), _q(mean_gap), max(gaps)


def _make_variant(
    request: WavetableBuildRequest,
    source: WavetablePlacementVariant,
    features: Mapping[str, CandidateTrajectoryFeatures],
    policy: PlacementProfilePolicy,
    slot_budget: AdaptiveSlotBudgetPlan,
    active: bool,
) -> FactoryPlacementVariant:
    ordered_ids = source.ordering.ordered_candidate_ids
    original_assignments = {item.candidate_id: item for item in source.placement.assignments}
    original_positions = {item.candidate_id: item.position for item in source.placement.assignments}
    required_positions = {
        item.candidate_id: item.position
        for item in request.position_locks
        if item.strength is ConstraintStrength.REQUIRED and item.candidate_id in original_positions
    }
    preference_positions = {
        item.candidate_id: item.position
        for item in request.position_locks
        if item.strength is ConstraintStrength.PREFERENCE and item.candidate_id in original_positions
    }
    required_zone = {candidate_id: _zone_for_position(position) for candidate_id, position in required_positions.items()}
    target_map = {item.zone: item for item in policy.targets}
    fit = {
        candidate_id: {
            zone: _zone_fit(features[candidate_id], target_map[zone], policy)
            for zone in FactoryZone
        }
        for candidate_id in ordered_ids
    }

    if active:
        desired = _desired_counts(len(ordered_ids), policy, slot_budget)
        counts = _select_zone_counts(ordered_ids, fit, required_zone, desired)
        stable_ids = tuple(ordered_ids[: counts[0]])
        evolution_ids = tuple(ordered_ids[counts[0] : counts[0] + counts[1]])
        extreme_ids = tuple(ordered_ids[counts[0] + counts[1] :])
        positions: dict[str, int] = {}
        warnings: list[str] = []
        for zone, ids in zip(FactoryZone, (stable_ids, evolution_ids, extreme_ids)):
            assigned, local_warnings = _assign_zone_positions(
                ids,
                zone,
                original_positions,
                required_positions,
                preference_positions,
                policy.honor_preference_locks,
            )
            positions.update(assigned)
            warnings.extend(local_warnings)
    else:
        positions = dict(original_positions)
        counts = tuple(sum(_zone_for_position(positions[candidate_id]) is zone for candidate_id in ordered_ids) for zone in FactoryZone)
        desired = counts
        warnings = []

    by_order = []
    zone_assignments: list[FactoryZoneAssignment] = []
    for order_index, candidate_id in enumerate(ordered_ids):
        original = original_assignments[candidate_id]
        position = positions[candidate_id]
        zone = _zone_for_position(position)
        zone_fit, error = fit[candidate_id][zone]
        required = candidate_id in required_positions
        preferred = candidate_id in preference_positions
        by_order.append(
            replace(
                original,
                position=position,
                order_index=order_index,
                required_locked=required and position == required_positions[candidate_id],
                preference_locked=preferred and position == preference_positions[candidate_id],
                evidence=tuple(dict.fromkeys(original.evidence + (f"V8-H placement profile {policy.analysis_sha256}", f"Factory zone {zone.value}"))),
                reason=(
                    "Factory Style keyframe placement inside the canonical three-zone convention."
                    if active
                    else "Generic V8-D placement preserved because Factory Style is disabled."
                ),
            )
        )
        zone_assignments.append(
            FactoryZoneAssignment(
                schema_version=FACTORY_PLACEMENT_SCHEMA_VERSION,
                candidate_id=candidate_id,
                order_index=order_index,
                zone=zone,
                position=position,
                original_position=original.position,
                zone_fit_score=zone_fit,
                trajectory_error=error,
                required_lock=required,
                preference_lock=preferred,
                evidence=(f"candidate features {features[candidate_id].to_dict()}", f"profile target {target_map[zone].to_dict()}"),
                reason=(
                    "Required lock takes precedence over profile preference."
                    if required
                    else "Candidate assigned by deterministic profile-zone optimization."
                    if active
                    else "Existing generic placement classified without movement."
                ),
            )
        )

    outcomes = _constraint_outcomes(request, ordered_ids, positions, policy.honor_preference_locks)
    required_failure = any(
        item.strength is ConstraintStrength.REQUIRED and item.status is not ConstraintOutcomeStatus.SATISFIED
        for item in outcomes
    )
    if required_failure:
        raise WavetableContractError("Factory placement would violate a required lock or chronology")
    spacing, mean_gap, maximum_gap = _spacing_score(tuple(positions.values()))
    lock_score = _constraint_score(outcomes, PlacementConstraintKind.POSITION_LOCK)
    chronology_score = _constraint_score(outcomes, PlacementConstraintKind.CHRONOLOGY)
    base_ordering = source.ordering.score.objective_score if source.ordering.score is not None else source.objective_score
    placement_objective = _q(
        source.placement.policy.ordering_weight * base_ordering
        + source.placement.policy.spacing_weight * spacing
        + source.placement.policy.lock_weight * lock_score
        + source.placement.policy.chronology_weight * chronology_score
    )
    placement_score = PlacementScore(
        schema_version=source.placement.score.schema_version if source.placement.score is not None else 1,
        objective_score=placement_objective,
        ordering_score=_q(base_ordering),
        spacing_evenness_score=spacing,
        position_lock_score=lock_score,
        chronology_score=chronology_score,
        mean_gap=mean_gap,
        maximum_gap=maximum_gap,
    )
    occupied = tuple(sorted(positions.values()))
    profiled_placement = replace(
        source.placement,
        assignments=tuple(by_order),
        occupied_positions=occupied,
        open_positions=tuple(position for position in range(USER_POSITION_COUNT) if position not in set(occupied)),
        constraint_outcomes=outcomes,
        score=placement_score,
        warnings=tuple(dict.fromkeys(source.placement.warnings + tuple(warnings))),
        blockers=(),
        reason=(
            "V8-H Factory Style placement with non-overlapping zones 01-20, 21-45 and 46-61."
            if active
            else "V8-H generic pass-through placement; Factory Style disabled."
        ),
    )
    moved = tuple(candidate_id for candidate_id in ordered_ids if positions[candidate_id] != original_positions[candidate_id])
    profiled_variant = replace(
        source,
        placement=profiled_placement,
        moved_candidate_ids=moved,
        mean_position_delta_from_primary=_q(sum(abs(positions[item] - original_positions[item]) for item in ordered_ids) / len(ordered_ids)),
        reason=(
            "V8-H profile-ranked Factory placement variant."
            if active
            else "V8-H generic pass-through variant."
        ),
    )
    trajectory_score = _q(sum(item.zone_fit_score for item in zone_assignments) / len(zone_assignments))
    adjacency_score = _q(source.ordering.score.scan_smoothness_score if source.ordering.score is not None else 1.0)
    source_fidelity = _q(source.ordering.score.source_fidelity_score if source.ordering.score is not None else 1.0)
    zone_count_score = _q(max(0.0, 1.0 - sum(abs(current - target) for current, target in zip(counts, desired)) / max(1, len(ordered_ids))))
    objective = _q(
        policy.generic_ordering_weight * source.objective_score
        + policy.trajectory_weight * trajectory_score
        + policy.adjacency_weight * adjacency_score
        + policy.source_fidelity_weight * source_fidelity
        + policy.zone_count_weight * zone_count_score
    )
    return FactoryPlacementVariant(
        schema_version=FACTORY_PLACEMENT_SCHEMA_VERSION,
        variant_id=profiled_variant.variant_id,
        rank=source.rank,
        source_v8d_variant_sha256=source.analysis_sha256,
        profiled_variant=profiled_variant,
        assignments=tuple(zone_assignments),
        zone_counts=counts,  # type: ignore[arg-type]
        trajectory_score=trajectory_score,
        adjacency_score=adjacency_score,
        source_fidelity_score=source_fidelity,
        zone_count_score=zone_count_score,
        objective_score=objective,
        moved_candidate_ids=moved,
        warnings=tuple(dict.fromkeys(tuple(warnings) + profiled_placement.warnings)),
        reason=(
            "Factory placement variant scored by profile trajectory, adjacency, source fidelity and zone budget."
            if active
            else "Generic placement retained byte-for-byte and classified by Factory zones for evidence only."
        ),
    )


def build_factory_placement(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
    v8d_analysis: CodeV8DAnalysis,
    slot_budget: AdaptiveSlotBudgetPlan,
    policy: PlacementProfilePolicy | None = None,
) -> FactoryPlacementAnalysis:
    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(v8b_analysis, CodeV8BAnalysis):
        raise WavetableContractError("v8b_analysis must be CodeV8BAnalysis")
    if not isinstance(v8c_analysis, CodeV8CAnalysis):
        raise WavetableContractError("v8c_analysis must be CodeV8CAnalysis")
    if not isinstance(v8d_analysis, CodeV8DAnalysis):
        raise WavetableContractError("v8d_analysis must be CodeV8DAnalysis")
    if not isinstance(slot_budget, AdaptiveSlotBudgetPlan):
        raise WavetableContractError("slot_budget must be AdaptiveSlotBudgetPlan")
    selected_policy = placement_profile_policy(
        request.selected_profile,
        factory_enabled=request.policy.factory_style,
    ) if policy is None else policy
    if selected_policy.profile.value != request.selected_profile:
        raise WavetableContractError("placement policy profile does not match request")
    if (
        v8b_analysis.request_sha256 != request.analysis_sha256
        or v8c_analysis.request_sha256 != request.analysis_sha256
        or v8d_analysis.request_sha256 != request.analysis_sha256
    ):
        raise WavetableContractError("V8-B/C/D request links are inconsistent")
    if v8d_analysis.status is not CodeV8DStatus.COMPLETE:
        return FactoryPlacementAnalysis(
            schema_version=FACTORY_PLACEMENT_SCHEMA_VERSION,
            status=FactoryPlacementStatus.REJECTED,
            request_sha256=request.analysis_sha256,
            v8b_analysis_sha256=v8b_analysis.analysis_sha256,
            v8c_analysis_sha256=v8c_analysis.analysis_sha256,
            v8d_analysis_sha256=v8d_analysis.analysis_sha256,
            slot_budget_sha256=slot_budget.analysis_sha256,
            policy=selected_policy,
            applied=False,
            variants=(),
            primary_variant_id=None,
            profiled_v8d_analysis=None,
            warnings=tuple(v8d_analysis.warnings),
            blockers=tuple(v8d_analysis.blockers) or ("V8-D analysis is rejected",),
            reason="V8-H rejected placement input without partial output.",
        )
    active = selected_policy.factory_enabled and request.policy.factory_style
    features = _candidate_features(request, v8b_analysis)
    built: list[FactoryPlacementVariant] = []
    failures: list[str] = []
    for source in v8d_analysis.variants:
        try:
            built.append(_make_variant(request, source, features, selected_policy, slot_budget, active))
        except WavetableContractError as exc:
            failures.append(f"{source.variant_id}: {exc}")
    if not built:
        return FactoryPlacementAnalysis(
            schema_version=FACTORY_PLACEMENT_SCHEMA_VERSION,
            status=FactoryPlacementStatus.REJECTED,
            request_sha256=request.analysis_sha256,
            v8b_analysis_sha256=v8b_analysis.analysis_sha256,
            v8c_analysis_sha256=v8c_analysis.analysis_sha256,
            v8d_analysis_sha256=v8d_analysis.analysis_sha256,
            slot_budget_sha256=slot_budget.analysis_sha256,
            policy=selected_policy,
            applied=active,
            variants=(),
            primary_variant_id=None,
            profiled_v8d_analysis=None,
            warnings=tuple(v8d_analysis.warnings),
            blockers=tuple(failures) or ("no Factory placement variant remained feasible",),
            reason="V8-H rejected all Factory placement variants without partial output.",
        )
    built.sort(key=lambda item: (-item.objective_score, item.variant_id, item.analysis_sha256))
    ranked: list[FactoryPlacementVariant] = []
    profiled_variants: list[WavetablePlacementVariant] = []
    primary_positions: dict[str, int] | None = None
    for rank, item in enumerate(built, 1):
        placement = item.profiled_variant.placement
        current_positions = {assignment.candidate_id: assignment.position for assignment in placement.assignments}
        if primary_positions is None:
            primary_positions = current_positions
        moved_from_primary = tuple(
            candidate_id
            for candidate_id in sorted(current_positions)
            if current_positions[candidate_id] != primary_positions[candidate_id]
        )
        mean_delta = _q(
            sum(abs(current_positions[candidate_id] - primary_positions[candidate_id]) for candidate_id in current_positions)
            / len(current_positions)
        )
        profiled_variant = replace(
            item.profiled_variant,
            rank=rank,
            moved_candidate_ids=moved_from_primary,
            mean_position_delta_from_primary=mean_delta,
        )
        ranked.append(replace(item, rank=rank, profiled_variant=profiled_variant))
        profiled_variants.append(profiled_variant)
    primary_id = ranked[0].variant_id
    profiled_v8d = CodeV8DAnalysis(
        schema_version=WAVETABLE_VARIANTS_SCHEMA_VERSION,
        status=CodeV8DStatus.COMPLETE,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        requested_variant_count=v8d_analysis.requested_variant_count,
        variants=tuple(profiled_variants),
        primary_variant_id=primary_id,
        warnings=tuple(dict.fromkeys(v8d_analysis.warnings + tuple(failures))),
        blockers=(),
        reason=(
            "V8-H Factory placement variants with profile-driven three-zone evidence."
            if active
            else "V8-H preserved the generic V8-D variants because Factory Style is disabled."
        ),
    )
    return FactoryPlacementAnalysis(
        schema_version=FACTORY_PLACEMENT_SCHEMA_VERSION,
        status=FactoryPlacementStatus.COMPLETE,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        v8d_analysis_sha256=v8d_analysis.analysis_sha256,
        slot_budget_sha256=slot_budget.analysis_sha256,
        policy=selected_policy,
        applied=active,
        variants=tuple(ranked),
        primary_variant_id=primary_id,
        profiled_v8d_analysis=profiled_v8d,
        warnings=tuple(dict.fromkeys(v8d_analysis.warnings + tuple(failures))),
        blockers=(),
        reason=(
            "V8-H applied true Factory Style as profile-driven keyframe selection/order/placement in three non-overlapping zones."
            if active
            else "Factory Style is disabled; generic placement remains byte-identical for the transition engine."
        ),
    )


__all__ = [
    "FACTORY_PLACEMENT_SCHEMA_VERSION",
    "FactoryPlacementAnalysis",
    "FactoryPlacementStatus",
    "FactoryPlacementVariant",
    "FactoryZone",
    "FactoryZoneAssignment",
    "FactoryZoneTarget",
    "PlacementProfilePolicy",
    "build_factory_placement",
    "placement_profile_policy",
]
