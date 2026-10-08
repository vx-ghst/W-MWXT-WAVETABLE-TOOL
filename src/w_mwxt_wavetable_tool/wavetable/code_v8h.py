from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping

from ..analysis.regions import RegionInterestAnalysis
from .code_v8g import CodeV8GAnalysis, CodeV8GStatus, CodeV8GVariant, build_code_v8g
from .continuity import DEFAULT_CONTINUITY_THRESHOLDS, ContinuityThresholds
from .deduplication import CodeV8BAnalysis
from .builder import TransitionDensityPolicy
from .factory_placement import (
    FactoryPlacementAnalysis,
    FactoryPlacementStatus,
    FactoryPlacementVariant,
    PlacementProfilePolicy,
    build_factory_placement,
)
from .interpolation import DEFAULT_INTERPOLATION_POLICY, InterpolationPolicy
from .models import (
    WAVETABLE_BUILD_SCHEMA_VERSION,
    WavetableBuild,
    WavetableBuildRequest,
    WavetableBuildSet,
    WavetableContractError,
)
from .selection import CodeV8CAnalysis
from .transition_planner import (
    DEFAULT_ADAPTIVE_SLOT_BUDGET_POLICY,
    DEFAULT_INTERPOLATION_ORACLE_THRESHOLDS,
    AdaptiveSlotBudgetPolicy,
    InterpolationOracleThresholds,
    plan_adaptive_slot_budget,
)
from .transition_shaping import (
    DISABLED_TRANSITION_SHAPING_POLICY,
    TransitionShapingAnalysis,
    TransitionShapingPolicy,
    TransitionShapingStatus,
    TransitionShapingVariant,
    apply_transition_shaping,
)
from .variants import CodeV8DAnalysis

CODE_V8H_SCHEMA_VERSION = 1
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


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _ratio(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked) or not 0.0 <= checked <= 1.0:
        raise WavetableContractError(f"{name} must be finite and between 0 and 1")
    return checked


class CodeV8HStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CodeV8HVariant:
    schema_version: int
    variant_id: str
    rank: int
    factory_placement_variant_sha256: str
    v8g_variant_sha256: str
    transition_shaping_variant_sha256: str
    build: WavetableBuild
    factory_score: float
    transition_score: float
    continuity_score: float
    objective_score: float
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8H_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-H variant schema version")
        if not isinstance(self.variant_id, str) or not self.variant_id:
            raise WavetableContractError("variant_id must not be empty")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise WavetableContractError("rank must be a positive integer")
        for name in (
            "factory_placement_variant_sha256",
            "v8g_variant_sha256",
            "transition_shaping_variant_sha256",
        ):
            _sha256(getattr(self, name), name=name)
        if not isinstance(self.build, WavetableBuild) or self.build.variant_id != self.variant_id:
            raise WavetableContractError("V8-H build must link to the variant ID")
        for name in (
            "factory_score",
            "transition_score",
            "continuity_score",
            "objective_score",
        ):
            _ratio(getattr(self, name), name=name)
        warnings = tuple(dict.fromkeys(self.warnings))
        object.__setattr__(self, "warnings", warnings)
        if any(not isinstance(item, str) or not item or item.strip() != item for item in warnings):
            raise WavetableContractError("warnings must contain normalized strings")
        if not isinstance(self.reason, str) or not self.reason or self.reason.strip() != self.reason:
            raise WavetableContractError("reason must be normalized")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "rank": self.rank,
            "factory_placement_variant_sha256": self.factory_placement_variant_sha256,
            "v8g_variant_sha256": self.v8g_variant_sha256,
            "transition_shaping_variant_sha256": self.transition_shaping_variant_sha256,
            "build": self.build.to_dict(),
            "factory_score": self.factory_score,
            "transition_score": self.transition_score,
            "continuity_score": self.continuity_score,
            "objective_score": self.objective_score,
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
class CodeV8HAnalysis:
    schema_version: int
    status: CodeV8HStatus
    request_sha256: str
    v8b_analysis_sha256: str
    v8c_analysis_sha256: str
    v8d_analysis_sha256: str
    region_interest_analysis_sha256: str
    factory_placement: FactoryPlacementAnalysis | None
    v8g_analysis: CodeV8GAnalysis | None
    transition_shaping: TransitionShapingAnalysis | None
    variants: tuple[CodeV8HVariant, ...]
    primary_variant_id: str | None
    build_set: WavetableBuildSet | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8H_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-H schema version")
        if not isinstance(self.status, CodeV8HStatus):
            raise WavetableContractError("status must be CodeV8HStatus")
        for name in (
            "request_sha256",
            "v8b_analysis_sha256",
            "v8c_analysis_sha256",
            "v8d_analysis_sha256",
            "region_interest_analysis_sha256",
        ):
            _sha256(getattr(self, name), name=name)
        variants = tuple(self.variants)
        object.__setattr__(self, "variants", variants)
        object.__setattr__(self, "warnings", tuple(dict.fromkeys(self.warnings)))
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))
        if tuple(item.rank for item in variants) != tuple(range(1, len(variants) + 1)):
            raise WavetableContractError("V8-H ranks must be canonical")
        if tuple(item.objective_score for item in variants) != tuple(
            sorted((item.objective_score for item in variants), reverse=True)
        ):
            raise WavetableContractError("V8-H variants must be ranked by objective score")
        if self.status is CodeV8HStatus.COMPLETE:
            if self.blockers:
                raise WavetableContractError("complete V8-H analysis cannot contain blockers")
            if (
                self.factory_placement is None
                or self.v8g_analysis is None
                or self.transition_shaping is None
                or not variants
                or self.primary_variant_id is None
                or self.build_set is None
            ):
                raise WavetableContractError("complete V8-H analysis requires all outputs")
            if self.factory_placement.status is not FactoryPlacementStatus.COMPLETE:
                raise WavetableContractError("complete V8-H requires complete Factory placement")
            if self.v8g_analysis.status is not CodeV8GStatus.COMPLETE:
                raise WavetableContractError("complete V8-H requires complete V8-G transitions")
            if self.transition_shaping.status is not TransitionShapingStatus.COMPLETE:
                raise WavetableContractError("complete V8-H requires complete shaping analysis")
            if variants[0].variant_id != self.primary_variant_id:
                raise WavetableContractError("primary V8-H variant must rank first")
            if self.build_set.primary_variant_id != self.primary_variant_id:
                raise WavetableContractError("V8-H build set primary variant disagrees")
            if tuple(item.variant_id for item in variants) != tuple(
                item.variant_id for item in self.build_set.builds
            ):
                raise WavetableContractError("V8-H build set disagrees with variants")
        else:
            if not self.blockers:
                raise WavetableContractError("rejected V8-H analysis requires blockers")
            if (
                self.factory_placement is not None
                or self.v8g_analysis is not None
                or self.transition_shaping is not None
                or variants
                or self.primary_variant_id is not None
                or self.build_set is not None
            ):
                raise WavetableContractError("rejected V8-H cannot expose partial output")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def primary_variant(self) -> CodeV8HVariant | None:
        return self.variants[0] if self.variants else None

    def _content_dict(self) -> dict[str, object]:
        factory_applied = bool(
            self.factory_placement is not None and self.factory_placement.applied
        )
        shaping_applied = bool(
            self.transition_shaping is not None and self.transition_shaping.applied
        )
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "v8b_analysis_sha256": self.v8b_analysis_sha256,
            "v8c_analysis_sha256": self.v8c_analysis_sha256,
            "v8d_analysis_sha256": self.v8d_analysis_sha256,
            "region_interest_analysis_sha256": self.region_interest_analysis_sha256,
            "factory_placement": (
                None if self.factory_placement is None else self.factory_placement.to_dict()
            ),
            "v8g_analysis": None if self.v8g_analysis is None else self.v8g_analysis.to_dict(),
            "transition_shaping": (
                None if self.transition_shaping is None else self.transition_shaping.to_dict()
            ),
            "variants": [item.to_dict() for item in self.variants],
            "primary_variant_id": self.primary_variant_id,
            "build_set": None if self.build_set is None else self.build_set.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "factory_style_placement": factory_applied,
                "factory_zones": {
                    "stable_playable": [1, 20],
                    "main_evolution": [21, 45],
                    "extreme": [46, 61],
                },
                "placement_precedes_interpolation": True,
                "transition_shaping_optional": True,
                "transition_shaping_applied": shaping_applied,
                "historical_waldorf_reconstruction_claim": False,
                "consolidates_physical_waves": False,
                "materializes_wctd": False,
                "allocates_xt_memory": False,
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
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n"


def _rejected(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
    v8d_analysis: CodeV8DAnalysis,
    region_interest_analysis: RegionInterestAnalysis,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    reason: str,
) -> CodeV8HAnalysis:
    return CodeV8HAnalysis(
        schema_version=CODE_V8H_SCHEMA_VERSION,
        status=CodeV8HStatus.REJECTED,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        v8d_analysis_sha256=v8d_analysis.analysis_sha256,
        region_interest_analysis_sha256=region_interest_analysis.analysis_sha256,
        factory_placement=None,
        v8g_analysis=None,
        transition_shaping=None,
        variants=(),
        primary_variant_id=None,
        build_set=None,
        warnings=warnings,
        blockers=blockers,
        reason=reason,
    )


def _combine_variants(
    factory: FactoryPlacementAnalysis,
    v8g: CodeV8GAnalysis,
    shaping: TransitionShapingAnalysis,
) -> tuple[CodeV8HVariant, ...]:
    factory_by_id: dict[str, FactoryPlacementVariant] = {
        item.variant_id: item for item in factory.variants
    }
    v8g_by_id: dict[str, CodeV8GVariant] = {item.variant_id: item for item in v8g.variants}
    shaping_by_id: dict[str, TransitionShapingVariant] = {
        item.variant_id: item for item in shaping.variants
    }
    common = set(factory_by_id) & set(v8g_by_id) & set(shaping_by_id)
    if not common:
        raise WavetableContractError("V8-H stages do not share a complete variant")
    built: list[CodeV8HVariant] = []
    for variant_id in sorted(common):
        factory_variant = factory_by_id[variant_id]
        transition_variant = v8g_by_id[variant_id]
        shaping_variant = shaping_by_id[variant_id]
        continuity_score = _q(shaping_variant.continuity.mean_continuity_score)
        objective = _q(
            0.40 * factory_variant.objective_score
            + 0.40 * transition_variant.objective_score
            + 0.20 * shaping_variant.objective_score
        )
        built.append(
            CodeV8HVariant(
                schema_version=CODE_V8H_SCHEMA_VERSION,
                variant_id=variant_id,
                rank=1,
                factory_placement_variant_sha256=factory_variant.analysis_sha256,
                v8g_variant_sha256=transition_variant.analysis_sha256,
                transition_shaping_variant_sha256=shaping_variant.analysis_sha256,
                build=shaping_variant.build,
                factory_score=factory_variant.objective_score,
                transition_score=transition_variant.objective_score,
                continuity_score=continuity_score,
                objective_score=objective,
                warnings=tuple(
                    dict.fromkeys(
                        factory_variant.warnings
                        + transition_variant.warnings
                        + shaping_variant.warnings
                    )
                ),
                reason=(
                    "V8-H variant combines profile-driven Factory placement, V8-G transitions "
                    "and optional post-transition shaping."
                ),
            )
        )
    built.sort(key=lambda item: (-item.objective_score, item.variant_id, item.analysis_sha256))
    return tuple(
        CodeV8HVariant(
            schema_version=item.schema_version,
            variant_id=item.variant_id,
            rank=rank,
            factory_placement_variant_sha256=item.factory_placement_variant_sha256,
            v8g_variant_sha256=item.v8g_variant_sha256,
            transition_shaping_variant_sha256=item.transition_shaping_variant_sha256,
            build=item.build,
            factory_score=item.factory_score,
            transition_score=item.transition_score,
            continuity_score=item.continuity_score,
            objective_score=item.objective_score,
            warnings=item.warnings,
            reason=item.reason,
        )
        for rank, item in enumerate(built, 1)
    )


def build_code_v8h(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
    v8d_analysis: CodeV8DAnalysis,
    region_interest_analysis: RegionInterestAnalysis,
    placement_policy: PlacementProfilePolicy | None = None,
    transition_shaping_policy: TransitionShapingPolicy = DISABLED_TRANSITION_SHAPING_POLICY,
    *,
    transition_shaping_requested: bool = False,
    interpolation_policy: InterpolationPolicy = DEFAULT_INTERPOLATION_POLICY,
    density_policy: TransitionDensityPolicy = TransitionDensityPolicy(),
    continuity_thresholds: ContinuityThresholds = DEFAULT_CONTINUITY_THRESHOLDS,
    slot_budget_policy: AdaptiveSlotBudgetPolicy = DEFAULT_ADAPTIVE_SLOT_BUDGET_POLICY,
    oracle_thresholds: InterpolationOracleThresholds = DEFAULT_INTERPOLATION_ORACLE_THRESHOLDS,
) -> CodeV8HAnalysis:
    """Build V8-H Factory Style placement before V8-G interpolation.

    Factory Style is a deterministic, profile-driven three-zone placement
    convention.  It does not claim reconstruction of historical Waldorf
    algorithms.  Transition shaping is a separate optional operation and must
    be requested explicitly.
    """

    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(v8b_analysis, CodeV8BAnalysis):
        raise WavetableContractError("v8b_analysis must be CodeV8BAnalysis")
    if not isinstance(v8c_analysis, CodeV8CAnalysis):
        raise WavetableContractError("v8c_analysis must be CodeV8CAnalysis")
    if not isinstance(v8d_analysis, CodeV8DAnalysis):
        raise WavetableContractError("v8d_analysis must be CodeV8DAnalysis")
    if not isinstance(region_interest_analysis, RegionInterestAnalysis):
        raise WavetableContractError("region_interest_analysis must be RegionInterestAnalysis")
    if not isinstance(transition_shaping_requested, bool):
        raise WavetableContractError("transition_shaping_requested must be boolean")
    if not isinstance(transition_shaping_policy, TransitionShapingPolicy):
        raise WavetableContractError("transition_shaping_policy must be TransitionShapingPolicy")

    slot_budget = plan_adaptive_slot_budget(region_interest_analysis, slot_budget_policy)
    factory = build_factory_placement(
        request,
        v8b_analysis,
        v8c_analysis,
        v8d_analysis,
        slot_budget,
        placement_policy,
    )
    if factory.status is not FactoryPlacementStatus.COMPLETE:
        return _rejected(
            request,
            v8b_analysis,
            v8c_analysis,
            v8d_analysis,
            region_interest_analysis,
            tuple(factory.blockers) or ("Factory placement is rejected",),
            tuple(factory.warnings),
            "CODE V8-H rejected Factory placement without exposing partial output.",
        )

    # The generic path must be exactly the original V8-G path.  The Factory
    # evidence analysis still exists, but no re-ranking or replacement of V8-D
    # is passed to interpolation when Factory Style is disabled.
    placement_v8d = (
        factory.profiled_v8d_analysis if factory.applied else v8d_analysis
    )
    if placement_v8d is None:
        raise WavetableContractError("complete Factory placement lacks a V8-D output")
    v8g = build_code_v8g(
        request,
        v8b_analysis,
        v8c_analysis,
        placement_v8d,
        region_interest_analysis,
        interpolation_policy,
        density_policy,
        continuity_thresholds,
        slot_budget_policy,
        oracle_thresholds,
    )
    if v8g.status is not CodeV8GStatus.COMPLETE:
        return _rejected(
            request,
            v8b_analysis,
            v8c_analysis,
            v8d_analysis,
            region_interest_analysis,
            tuple(v8g.blockers) or ("V8-G transition analysis is rejected",),
            tuple(dict.fromkeys(factory.warnings + v8g.warnings)),
            "CODE V8-H rejected transition generation without exposing partial output.",
        )

    shaping = apply_transition_shaping(
        request,
        v8g,
        transition_shaping_policy,
        requested=transition_shaping_requested,
    )
    if shaping.status is not TransitionShapingStatus.COMPLETE:
        return _rejected(
            request,
            v8b_analysis,
            v8c_analysis,
            v8d_analysis,
            region_interest_analysis,
            tuple(shaping.blockers) or ("transition shaping is rejected",),
            tuple(dict.fromkeys(factory.warnings + v8g.warnings + shaping.warnings)),
            "CODE V8-H rejected optional shaping without exposing partial output.",
        )

    try:
        variants = _combine_variants(factory, v8g, shaping)
    except WavetableContractError as exc:
        return _rejected(
            request,
            v8b_analysis,
            v8c_analysis,
            v8d_analysis,
            region_interest_analysis,
            (str(exc),),
            tuple(dict.fromkeys(factory.warnings + v8g.warnings + shaping.warnings)),
            "CODE V8-H rejected inconsistent variant links without partial output.",
        )
    primary_id = variants[0].variant_id
    build_set = WavetableBuildSet(
        schema_version=WAVETABLE_BUILD_SCHEMA_VERSION,
        request_sha256=request.analysis_sha256,
        builds=tuple(item.build for item in variants),
        primary_variant_id=primary_id,
        reason=(
            "CODE V8-H build set with Factory placement before interpolation and optional shaping."
        ),
    )
    warnings = tuple(
        dict.fromkeys(factory.warnings + v8g.warnings + shaping.warnings)
    )
    return CodeV8HAnalysis(
        schema_version=CODE_V8H_SCHEMA_VERSION,
        status=CodeV8HStatus.COMPLETE,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        v8d_analysis_sha256=v8d_analysis.analysis_sha256,
        region_interest_analysis_sha256=region_interest_analysis.analysis_sha256,
        factory_placement=factory,
        v8g_analysis=v8g,
        transition_shaping=shaping,
        variants=variants,
        primary_variant_id=primary_id,
        build_set=build_set,
        warnings=warnings,
        blockers=(),
        reason=(
            "CODE V8-H completed profile-driven Factory Style placement in zones 01-20, "
            "21-45 and 46-61 before V8-G interpolation."
        ),
    )


__all__ = [
    "CODE_V8H_SCHEMA_VERSION",
    "CodeV8HAnalysis",
    "CodeV8HStatus",
    "CodeV8HVariant",
    "build_code_v8h",
]
