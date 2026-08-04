from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping

from ..analysis.regions import RegionInterestAnalysis
from .builder import (
    CodeV8EStatus,
    TransitionDensityPolicy,
    WavetableTransitionMap,
    build_wavetable_transitions,
)
from .continuity import (
    DEFAULT_CONTINUITY_THRESHOLDS,
    ContinuityRepairReport,
    ContinuityStatus,
    ContinuityThresholds,
    WavetableContinuityReport,
    repair_wavetable_continuity,
)
from .deduplication import CodeV8BAnalysis
from .interpolation import (
    DEFAULT_INTERPOLATION_POLICY,
    InterpolationPolicy,
    progression_value,
)
from .models import (
    WavetableBuild,
    WavetableBuildRequest,
    WavetableBuildSet,
    WavetableContractError,
)
from .selection import CodeV8CAnalysis
from .transition_planner import (
    DEFAULT_ADAPTIVE_SLOT_BUDGET_POLICY,
    DEFAULT_INTERPOLATION_ORACLE_THRESHOLDS,
    AdaptiveSlotBudgetPlan,
    AdaptiveSlotBudgetPolicy,
    InterpolationOracleThresholds,
    TransitionIntervalDecision,
    plan_adaptive_slot_budget,
    select_interval_interpolation_method,
)
from .variants import CodeV8DAnalysis, CodeV8DStatus

CODE_V8G_SCHEMA_VERSION = 1
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


class CodeV8GStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CodeV8GVariant:
    schema_version: int
    variant_id: str
    rank: int
    build: WavetableBuild
    transition_map: WavetableTransitionMap
    interval_decisions: tuple[TransitionIntervalDecision, ...]
    continuity: WavetableContinuityReport
    repair: ContinuityRepairReport
    objective_score: float
    oracle_score: float
    continuity_score: float
    placement_score: float
    density_score: float
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8G_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-G variant schema version")
        if not isinstance(self.variant_id, str) or not self.variant_id:
            raise WavetableContractError("variant_id must not be empty")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise WavetableContractError("rank must be a positive integer")
        if self.build.variant_id != self.variant_id:
            raise WavetableContractError("build variant_id disagrees with V8-G variant")
        if self.continuity.build_sha256 != self.build.analysis_sha256:
            raise WavetableContractError("continuity report does not link to repaired build")
        if self.continuity.status is ContinuityStatus.FAIL:
            raise WavetableContractError("V8-G variant cannot retain failed continuity")
        if self.repair.repaired_build_sha256 != self.build.analysis_sha256:
            raise WavetableContractError("repair report does not link to repaired build")
        decisions = tuple(self.interval_decisions)
        object.__setattr__(self, "interval_decisions", decisions)
        if len(decisions) != len(self.transition_map.intervals):
            raise WavetableContractError("every transition interval requires one decision")
        for plan, decision in zip(self.transition_map.intervals, decisions):
            if (plan.left_candidate_id, plan.right_candidate_id) != (
                decision.left_candidate_id,
                decision.right_candidate_id,
            ):
                raise WavetableContractError("interval decision endpoints disagree")
            methods = {
                record.method
                for record in self.transition_map.records
                if record.position in plan.open_positions
            }
            methods.discard(None)
            if methods and methods != {decision.selected_method}:
                raise WavetableContractError("one immutable method is required per interval")
        for name in (
            "objective_score",
            "oracle_score",
            "continuity_score",
            "placement_score",
            "density_score",
        ):
            _ratio(getattr(self, name), name=name)
        object.__setattr__(self, "warnings", tuple(dict.fromkeys(self.warnings)))
        if not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "rank": self.rank,
            "build": self.build.to_dict(),
            "transition_map": self.transition_map.to_dict(),
            "interval_decisions": [item.to_dict() for item in self.interval_decisions],
            "continuity": self.continuity.to_dict(),
            "repair": self.repair.to_dict(),
            "objective_score": self.objective_score,
            "oracle_score": self.oracle_score,
            "continuity_score": self.continuity_score,
            "placement_score": self.placement_score,
            "density_score": self.density_score,
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
class CodeV8GAnalysis:
    schema_version: int
    status: CodeV8GStatus
    request_sha256: str
    v8b_analysis_sha256: str
    v8c_analysis_sha256: str
    v8d_analysis_sha256: str
    region_interest_analysis_sha256: str
    interpolation_policy: InterpolationPolicy
    density_policy: TransitionDensityPolicy
    continuity_thresholds: ContinuityThresholds
    slot_budget: AdaptiveSlotBudgetPlan | None
    variants: tuple[CodeV8GVariant, ...]
    primary_variant_id: str | None
    build_set: WavetableBuildSet | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8G_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-G schema version")
        if not isinstance(self.status, CodeV8GStatus):
            raise WavetableContractError("status must be CodeV8GStatus")
        for name in (
            "request_sha256",
            "v8b_analysis_sha256",
            "v8c_analysis_sha256",
            "v8d_analysis_sha256",
            "region_interest_analysis_sha256",
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
        object.__setattr__(self, "warnings", tuple(dict.fromkeys(self.warnings)))
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))
        if self.status is CodeV8GStatus.COMPLETE:
            if self.blockers or self.slot_budget is None or not variants:
                raise WavetableContractError("complete V8-G analysis requires output without blockers")
            if self.primary_variant_id != variants[0].variant_id or self.build_set is None:
                raise WavetableContractError("complete V8-G analysis requires a primary build set")
            if tuple(item.rank for item in variants) != tuple(range(1, len(variants) + 1)):
                raise WavetableContractError("V8-G ranks must be canonical")
            if tuple(build.variant_id for build in self.build_set.builds) != tuple(
                item.variant_id for item in variants
            ):
                raise WavetableContractError("V8-G build set disagrees with variants")
        else:
            if not self.blockers:
                raise WavetableContractError("rejected V8-G analysis requires blockers")
            if self.slot_budget is not None or variants or self.primary_variant_id is not None or self.build_set is not None:
                raise WavetableContractError("rejected V8-G analysis cannot expose partial output")
        if not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def produced_variant_count(self) -> int:
        return len(self.variants)

    @property
    def primary_variant(self) -> CodeV8GVariant | None:
        return self.variants[0] if self.variants else None

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "v8b_analysis_sha256": self.v8b_analysis_sha256,
            "v8c_analysis_sha256": self.v8c_analysis_sha256,
            "v8d_analysis_sha256": self.v8d_analysis_sha256,
            "region_interest_analysis_sha256": self.region_interest_analysis_sha256,
            "interpolation_policy": self.interpolation_policy.to_dict(),
            "density_policy": self.density_policy.to_dict(),
            "continuity_thresholds": self.continuity_thresholds.to_dict(),
            "slot_budget": None if self.slot_budget is None else self.slot_budget.to_dict(),
            "produced_variant_count": self.produced_variant_count,
            "primary_variant_id": self.primary_variant_id,
            "variants": [item.to_dict() for item in self.variants],
            "build_set": None if self.build_set is None else self.build_set.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "canonical_reconciliation": True,
                "global_slot_budget": True,
                "one_method_per_interval": True,
                "measured_continuity_repair": True,
                "applies_factory_style": False,
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


def _permissive_continuity_thresholds() -> ContinuityThresholds:
    return ContinuityThresholds(
        warning_perceptual_distance=0.999,
        failure_perceptual_distance=1.0,
        warning_spectral_distance=0.999,
        failure_spectral_distance=1.0,
        warning_level_delta=0.999,
        failure_level_delta=1.0,
        warning_fundamental_delta=0.999,
        failure_fundamental_delta=1.0,
        warning_maximum_sample_distance=0.999,
        failure_maximum_sample_distance=1.0,
        failure_correlation_floor=-1.0,
    )


def _rejected(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
    v8d_analysis: CodeV8DAnalysis,
    region_interest_analysis: RegionInterestAnalysis,
    interpolation_policy: InterpolationPolicy,
    density_policy: TransitionDensityPolicy,
    continuity_thresholds: ContinuityThresholds,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    reason: str,
) -> CodeV8GAnalysis:
    return CodeV8GAnalysis(
        schema_version=CODE_V8G_SCHEMA_VERSION,
        status=CodeV8GStatus.REJECTED,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        v8d_analysis_sha256=v8d_analysis.analysis_sha256,
        region_interest_analysis_sha256=region_interest_analysis.analysis_sha256,
        interpolation_policy=interpolation_policy,
        density_policy=density_policy,
        continuity_thresholds=continuity_thresholds,
        slot_budget=None,
        variants=(),
        primary_variant_id=None,
        build_set=None,
        warnings=warnings,
        blockers=blockers,
        reason=reason,
    )


def build_code_v8g(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
    v8d_analysis: CodeV8DAnalysis,
    region_interest_analysis: RegionInterestAnalysis,
    interpolation_policy: InterpolationPolicy = DEFAULT_INTERPOLATION_POLICY,
    density_policy: TransitionDensityPolicy = TransitionDensityPolicy(),
    continuity_thresholds: ContinuityThresholds = DEFAULT_CONTINUITY_THRESHOLDS,
    slot_budget_policy: AdaptiveSlotBudgetPolicy = DEFAULT_ADAPTIVE_SLOT_BUDGET_POLICY,
    oracle_thresholds: InterpolationOracleThresholds = DEFAULT_INTERPOLATION_ORACLE_THRESHOLDS,
) -> CodeV8GAnalysis:
    """Build the V8-G reconciliation and transition aggregate.

    This stage deliberately excludes Factory Style, physical-wave consolidation,
    WCTD materialization, memory allocation, SysEx generation and MIDI transport.
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
    if (
        region_interest_analysis.sample_sha256 != request.sample_sha256
        or region_interest_analysis.sample_rate != request.sample_rate
        or region_interest_analysis.sample_count != request.sample_count
    ):
        raise WavetableContractError("region-interest analysis does not link to request source")
    if (
        v8b_analysis.request_sha256 != request.analysis_sha256
        or v8c_analysis.request_sha256 != request.analysis_sha256
        or v8d_analysis.request_sha256 != request.analysis_sha256
    ):
        raise WavetableContractError("V8-B/C/D request links are inconsistent")
    if (
        v8c_analysis.v8b_analysis_sha256 != v8b_analysis.analysis_sha256
        or v8d_analysis.v8b_analysis_sha256 != v8b_analysis.analysis_sha256
        or v8d_analysis.v8c_analysis_sha256 != v8c_analysis.analysis_sha256
    ):
        raise WavetableContractError("V8-B/C/D analysis links are inconsistent")
    if v8d_analysis.status is not CodeV8DStatus.COMPLETE:
        return _rejected(
            request,
            v8b_analysis,
            v8c_analysis,
            v8d_analysis,
            region_interest_analysis,
            interpolation_policy,
            density_policy,
            continuity_thresholds,
            tuple(v8d_analysis.blockers) or ("V8-D analysis is rejected",),
            tuple(v8d_analysis.warnings),
            "CODE V8-G rejected the input without exposing partial output.",
        )

    slot_budget = plan_adaptive_slot_budget(region_interest_analysis, slot_budget_policy)
    v8e = build_wavetable_transitions(
        request,
        v8b_analysis,
        v8c_analysis,
        v8d_analysis,
        interpolation_policy,
        density_policy,
        _permissive_continuity_thresholds(),
    )
    if v8e.status is not CodeV8EStatus.COMPLETE:
        return _rejected(
            request,
            v8b_analysis,
            v8c_analysis,
            v8d_analysis,
            region_interest_analysis,
            interpolation_policy,
            density_policy,
            continuity_thresholds,
            tuple(v8e.blockers) or ("V8-E transition build is rejected",),
            tuple(v8e.warnings),
            "CODE V8-G rejected the transition baseline without partial output.",
        )

    candidates = {item.candidate_id: item for item in request.candidates}
    built: list[tuple[float, object, WavetableBuild, WavetableTransitionMap, tuple[TransitionIntervalDecision, ...], WavetableContinuityReport, ContinuityRepairReport, float, float]] = []
    failures: list[str] = []

    for source_variant in v8e.variants:
        repaired_build, continuity, repair = repair_wavetable_continuity(
            source_variant.build,
            continuity_thresholds,
            interpolation_policy,
        )
        decisions: list[TransitionIntervalDecision] = []
        for plan in source_variant.transition_map.intervals:
            targets = tuple(
                sorted(
                    {
                        progression_value(
                            value,
                            request.policy.progression_curve,
                            plan.complexity_score,
                        )
                        for value in plan.progress_values
                    }
                )
            )
            decisions.append(
                select_interval_interpolation_method(
                    candidates[plan.left_candidate_id],
                    candidates[plan.right_candidate_id],
                    request.policy.allowed_interpolation_methods,
                    interpolation_policy,
                    targets,
                    oracle_thresholds,
                )
            )

        accepted_positions = set(repair.accepted_positions)
        records = tuple(
            replace(
                record,
                stored_samples_sha256=repaired_build.slots[record.position].stored_samples_sha256,
                evidence=tuple(
                    dict.fromkeys(
                        record.evidence
                        + (
                            (f"continuity repair {repair.analysis_sha256}",)
                            if record.position in accepted_positions
                            else ()
                        )
                    )
                ),
                reason=(
                    "Transition stage updated by accepted V8-G continuity repair."
                    if record.position in accepted_positions
                    else record.reason
                ),
            )
            for record in source_variant.transition_map.records
        )
        transition_map = replace(
            source_variant.transition_map,
            records=records,
            reason="V8-G interval decisions and measured continuity repair linked to every open position.",
        )

        inconsistent: list[str] = []
        for plan, decision in zip(transition_map.intervals, decisions):
            methods = {
                record.method
                for record in transition_map.records
                if record.position in plan.open_positions
            }
            methods.discard(None)
            if methods and methods != {decision.selected_method}:
                inconsistent.append(f"{plan.left_candidate_id}->{plan.right_candidate_id}")
        if inconsistent or continuity.status is ContinuityStatus.FAIL:
            failures.append(
                f"{source_variant.variant_id}: "
                + (
                    "method varied inside interval " + ", ".join(inconsistent)
                    if inconsistent
                    else "; ".join(continuity.blockers)
                )
            )
            continue

        selected_oracles = [
            next(
                oracle
                for oracle in decision.oracles
                if oracle.method is decision.selected_method
            )
            for decision in decisions
        ]
        oracle_score = _q(
            1.0
            if not selected_oracles
            else sum(item.aggregate_score for item in selected_oracles) / len(selected_oracles)
        )
        continuity_score = _q(
            0.65 * continuity.mean_continuity_score
            + 0.35 * continuity.minimum_continuity_score
        )
        objective = _q(
            0.40 * continuity_score
            + 0.25 * oracle_score
            + 0.20 * source_variant.placement_score
            + 0.15 * source_variant.density_score
        )
        built.append(
            (
                objective,
                source_variant,
                repaired_build,
                transition_map,
                tuple(decisions),
                continuity,
                repair,
                oracle_score,
                continuity_score,
            )
        )

    if not built:
        return _rejected(
            request,
            v8b_analysis,
            v8c_analysis,
            v8d_analysis,
            region_interest_analysis,
            interpolation_policy,
            density_policy,
            continuity_thresholds,
            tuple(failures) or ("no V8-G variant passed mandatory continuity",),
            tuple(v8e.warnings),
            "CODE V8-G rejected every variant without exposing partial output.",
        )

    built.sort(
        key=lambda item: (
            -item[0],
            item[1].rank,
            item[1].variant_id,
            item[2].analysis_sha256,
        )
    )
    variants: list[CodeV8GVariant] = []
    for rank, (
        objective,
        source_variant,
        repaired_build,
        transition_map,
        decisions,
        continuity,
        repair,
        oracle_score,
        continuity_score,
    ) in enumerate(built, 1):
        variants.append(
            CodeV8GVariant(
                schema_version=CODE_V8G_SCHEMA_VERSION,
                variant_id=repaired_build.variant_id,
                rank=rank,
                build=repaired_build,
                transition_map=transition_map,
                interval_decisions=decisions,
                continuity=continuity,
                repair=repair,
                objective_score=objective,
                oracle_score=oracle_score,
                continuity_score=continuity_score,
                placement_score=source_variant.placement_score,
                density_score=source_variant.density_score,
                warnings=tuple(
                    dict.fromkeys(source_variant.warnings + continuity.warnings)
                ),
                reason=(
                    "Primary V8-G variant selected by interval oracles, continuity, placement and density."
                    if rank == 1
                    else "Alternative V8-G variant retained with complete evidence."
                ),
            )
        )

    primary_variant_id = variants[0].variant_id
    build_set = WavetableBuildSet(
        schema_version=1,
        request_sha256=request.analysis_sha256,
        builds=tuple(item.build for item in variants),
        primary_variant_id=primary_variant_id,
        reason=(
            "Complete V8-G build set. Factory Style, physical-wave consolidation, "
            "inventory and WCTD remain outside this stage."
        ),
    )
    return CodeV8GAnalysis(
        schema_version=CODE_V8G_SCHEMA_VERSION,
        status=CodeV8GStatus.COMPLETE,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        v8d_analysis_sha256=v8d_analysis.analysis_sha256,
        region_interest_analysis_sha256=region_interest_analysis.analysis_sha256,
        interpolation_policy=interpolation_policy,
        density_policy=density_policy,
        continuity_thresholds=continuity_thresholds,
        slot_budget=slot_budget,
        variants=tuple(variants),
        primary_variant_id=primary_variant_id,
        build_set=build_set,
        warnings=tuple(dict.fromkeys(tuple(v8e.warnings) + tuple(failures))),
        blockers=(),
        reason=(
            "CODE V8-G reconciled canonical requirement references, produced a "
            "global 61-slot budget, selected one method per interval and applied "
            "measured continuity repair."
        ),
    )


__all__ = [
    "CODE_V8G_SCHEMA_VERSION",
    "CodeV8GStatus",
    "CodeV8GVariant",
    "CodeV8GAnalysis",
    "build_code_v8g",
]
