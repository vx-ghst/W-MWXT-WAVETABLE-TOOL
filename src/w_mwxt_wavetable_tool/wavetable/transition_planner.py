from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from functools import lru_cache
import json
import math
from typing import Mapping, Sequence

import numpy as np

from ..analysis.regions import InterestRegion, RegionInterestAnalysis, RegionKind
from .interpolation import (
    DEFAULT_INTERPOLATION_POLICY,
    InterpolationPolicy,
    interpolate_xt_wave,
)
from .metrics import compare_wave_shapes
from .models import (
    GenerationMethod,
    USER_POSITION_COUNT,
    WavetableCandidate,
    WavetableContractError,
    reconstruct_xt_cycle,
)

WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION = 1
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


def _progress_values(values: Sequence[float], *, allow_empty: bool = False) -> tuple[float, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError("progress values must be a sequence")
    result = tuple(_q(_ratio(value, name="progress value")) for value in values)
    if not allow_empty and not result:
        raise WavetableContractError("progress values must not be empty")
    if result != tuple(sorted(set(result))):
        raise WavetableContractError("progress values must be sorted and unique")
    if any(value <= 0.0 or value >= 1.0 for value in result):
        raise WavetableContractError("progress values must be strictly inside (0, 1)")
    return result


def _harmonic_magnitudes(samples: Sequence[int], count: int = 3) -> tuple[float, ...]:
    cycle = np.asarray(reconstruct_xt_cycle(samples), dtype=np.float64) / 127.0
    spectrum = np.abs(np.fft.rfft(cycle))
    result = []
    for index in range(1, count + 1):
        amplitude = 0.0 if index >= spectrum.size else 2.0 * spectrum[index] / cycle.size
        result.append(_q(max(0.0, min(1.0, amplitude))))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class AdaptiveSlotBudgetPolicy:
    schema_version: int = WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION
    minimum_slots_per_active_region: int = 1
    allocation_weight: float = 0.20
    interest_weight: float = 0.25
    useful_change_weight: float = 0.30
    complexity_weight: float = 0.15
    saturation_weight: float = 0.05
    attack_bonus: float = 0.05
    stable_penalty: float = 0.35
    redundancy_penalty: float = 0.80

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported adaptive slot-budget schema version")
        if (
            isinstance(self.minimum_slots_per_active_region, bool)
            or not isinstance(self.minimum_slots_per_active_region, int)
            or self.minimum_slots_per_active_region < 0
        ):
            raise WavetableContractError(
                "minimum_slots_per_active_region must be a non-negative integer"
            )
        for name in (
            "allocation_weight",
            "interest_weight",
            "useful_change_weight",
            "complexity_weight",
            "saturation_weight",
            "attack_bonus",
            "stable_penalty",
            "redundancy_penalty",
        ):
            _ratio(getattr(self, name), name=name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "minimum_slots_per_active_region": self.minimum_slots_per_active_region,
            "allocation_weight": self.allocation_weight,
            "interest_weight": self.interest_weight,
            "useful_change_weight": self.useful_change_weight,
            "complexity_weight": self.complexity_weight,
            "saturation_weight": self.saturation_weight,
            "attack_bonus": self.attack_bonus,
            "stable_penalty": self.stable_penalty,
            "redundancy_penalty": self.redundancy_penalty,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_ADAPTIVE_SLOT_BUDGET_POLICY = AdaptiveSlotBudgetPolicy()


@dataclass(frozen=True, slots=True)
class RegionSlotBudget:
    schema_version: int
    region_index: int
    kind: RegionKind
    slot_count: int
    normalized_weight: float
    strong_change_region: bool
    stable_region: bool
    redundant_region: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported region slot-budget schema version")
        if isinstance(self.region_index, bool) or not isinstance(self.region_index, int) or self.region_index < 0:
            raise WavetableContractError("region_index must be a non-negative integer")
        if isinstance(self.slot_count, bool) or not isinstance(self.slot_count, int) or self.slot_count < 0:
            raise WavetableContractError("slot_count must be a non-negative integer")
        if not isinstance(self.kind, RegionKind):
            raise WavetableContractError("kind must be RegionKind")
        _ratio(self.normalized_weight, name="normalized_weight")
        if self.redundant_region and self.strong_change_region:
            raise WavetableContractError(
                "a redundant region cannot simultaneously be a strong-change region"
            )
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "region_index": self.region_index,
            "kind": self.kind.value,
            "slot_count": self.slot_count,
            "normalized_weight": self.normalized_weight,
            "strong_change_region": self.strong_change_region,
            "stable_region": self.stable_region,
            "redundant_region": self.redundant_region,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AdaptiveSlotBudgetPlan:
    schema_version: int
    region_interest_analysis_sha256: str
    policy: AdaptiveSlotBudgetPolicy
    total_slots: int
    budgets: tuple[RegionSlotBudget, ...]
    strong_change_slot_count: int
    stable_slot_count: int
    redundant_slot_count: int
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported adaptive slot-budget plan schema version")
        _sha256(self.region_interest_analysis_sha256, name="region_interest_analysis_sha256")
        if not isinstance(self.policy, AdaptiveSlotBudgetPolicy):
            raise WavetableContractError("policy must be AdaptiveSlotBudgetPolicy")
        object.__setattr__(self, "budgets", tuple(self.budgets))
        if self.total_slots != USER_POSITION_COUNT:
            raise WavetableContractError("adaptive slot budget must contain exactly 61 slots")
        if sum(item.slot_count for item in self.budgets) != self.total_slots:
            raise WavetableContractError("region slot counts must sum to 61")
        if tuple(item.region_index for item in self.budgets) != tuple(range(len(self.budgets))):
            raise WavetableContractError("region budgets must be ordered and contiguous")
        expected_strong = sum(item.slot_count for item in self.budgets if item.strong_change_region)
        expected_stable = sum(item.slot_count for item in self.budgets if item.stable_region)
        expected_redundant = sum(item.slot_count for item in self.budgets if item.redundant_region)
        if self.strong_change_slot_count != expected_strong:
            raise WavetableContractError("strong_change_slot_count disagrees with budgets")
        if self.stable_slot_count != expected_stable:
            raise WavetableContractError("stable_slot_count disagrees with budgets")
        if self.redundant_slot_count != expected_redundant:
            raise WavetableContractError("redundant_slot_count disagrees with budgets")
        if not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "region_interest_analysis_sha256": self.region_interest_analysis_sha256,
            "policy": self.policy.to_dict(),
            "total_slots": self.total_slots,
            "budgets": [item.to_dict() for item in self.budgets],
            "strong_change_slot_count": self.strong_change_slot_count,
            "stable_slot_count": self.stable_slot_count,
            "redundant_slot_count": self.redundant_slot_count,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _region_weight(
    region: InterestRegion,
    policy: AdaptiveSlotBudgetPolicy,
) -> tuple[float, bool, bool, bool]:
    redundant = region.kind is RegionKind.REDUNDANCY
    stable = (
        region.kind in {RegionKind.ESTABLISHMENT, RegionKind.SUSTAIN}
        and not region.useful_change
    )
    strong = (not redundant) and (
        region.useful_change
        or region.kind
        in {
            RegionKind.ATTACK,
            RegionKind.EVOLUTION,
            RegionKind.SATURATION,
            RegionKind.DISAPPEARANCE,
        }
    )
    score = (
        policy.allocation_weight * region.allocation_weight
        + policy.interest_weight * region.interest_score
        + policy.useful_change_weight * region.useful_change_score
        + policy.complexity_weight * region.complexity_score
        + policy.saturation_weight * region.saturation_score
        + (policy.attack_bonus if region.kind is RegionKind.ATTACK else 0.0)
    )
    if stable:
        score *= 1.0 - policy.stable_penalty
    if redundant:
        score *= 1.0 - policy.redundancy_penalty
    if region.kind is RegionKind.SILENCE:
        score = 0.0
    return max(0.0, score), strong, stable, redundant


def plan_adaptive_slot_budget(
    analysis: RegionInterestAnalysis,
    policy: AdaptiveSlotBudgetPolicy = DEFAULT_ADAPTIVE_SLOT_BUDGET_POLICY,
) -> AdaptiveSlotBudgetPlan:
    if not isinstance(analysis, RegionInterestAnalysis):
        raise WavetableContractError("analysis must be RegionInterestAnalysis")
    if not isinstance(policy, AdaptiveSlotBudgetPolicy):
        raise WavetableContractError("policy must be AdaptiveSlotBudgetPolicy")
    scored = [_region_weight(region, policy) for region in analysis.regions]
    active = [
        index
        for index, region in enumerate(analysis.regions)
        if region.kind is not RegionKind.SILENCE
    ]
    if not active:
        raise WavetableContractError("at least one active region is required")
    minimum = policy.minimum_slots_per_active_region
    if minimum * len(active) > USER_POSITION_COUNT:
        raise WavetableContractError("minimum region allocation exceeds 61 positions")
    counts = [0] * len(analysis.regions)
    for index in active:
        counts[index] = minimum
    remaining = USER_POSITION_COUNT - sum(counts)
    scores = [scored[index][0] for index in active]
    total_score = sum(scores)
    weights = (
        [1.0 / len(active)] * len(active)
        if total_score <= 1e-15
        else [score / total_score for score in scores]
    )
    quotas = [remaining * weight for weight in weights]
    for index, quota in zip(active, quotas):
        counts[index] += int(math.floor(quota))
    leftovers = USER_POSITION_COUNT - sum(counts)
    order = sorted(
        range(len(active)),
        key=lambda item: (-(quotas[item] - math.floor(quotas[item])), active[item]),
    )
    for item in order[:leftovers]:
        counts[active[item]] += 1
    normalized = [0.0] * len(analysis.regions)
    for index, weight in zip(active, weights):
        normalized[index] = _q(weight)
    budgets = tuple(
        RegionSlotBudget(
            schema_version=WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION,
            region_index=region.index,
            kind=region.kind,
            slot_count=counts[region.index],
            normalized_weight=normalized[region.index],
            strong_change_region=scored[region.index][1],
            stable_region=scored[region.index][2],
            redundant_region=scored[region.index][3],
            reason=(
                "V8-G global allocation derived from source-region change, "
                "complexity, saturation and redundancy evidence."
            ),
        )
        for region in analysis.regions
    )
    return AdaptiveSlotBudgetPlan(
        schema_version=WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION,
        region_interest_analysis_sha256=analysis.analysis_sha256,
        policy=policy,
        total_slots=USER_POSITION_COUNT,
        budgets=budgets,
        strong_change_slot_count=sum(
            item.slot_count for item in budgets if item.strong_change_region
        ),
        stable_slot_count=sum(item.slot_count for item in budgets if item.stable_region),
        redundant_slot_count=sum(
            item.slot_count for item in budgets if item.redundant_region
        ),
        reason=(
            "Exactly 61 logical positions globally budgeted. V8-H consumes "
            "this evidence for profile-aware placement."
        ),
    )


@dataclass(frozen=True, slots=True)
class InterpolationOracleThresholds:
    schema_version: int = WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION
    minimum_spacing_regularity: float = 0.50
    minimum_spectral_path: float = 0.45
    minimum_harmonic_path: float = 0.70
    minimum_protection: float = 0.50
    minimum_solver_improvement: float = 0.000001
    solver_grid_size: int = 17

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported interpolation oracle schema version")
        for name in (
            "minimum_spacing_regularity",
            "minimum_spectral_path",
            "minimum_harmonic_path",
            "minimum_protection",
            "minimum_solver_improvement",
        ):
            _ratio(getattr(self, name), name=name)
        if (
            isinstance(self.solver_grid_size, bool)
            or not isinstance(self.solver_grid_size, int)
            or self.solver_grid_size < 5
            or self.solver_grid_size % 2 == 0
        ):
            raise WavetableContractError("solver_grid_size must be an odd integer >= 5")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "minimum_spacing_regularity": self.minimum_spacing_regularity,
            "minimum_spectral_path": self.minimum_spectral_path,
            "minimum_harmonic_path": self.minimum_harmonic_path,
            "minimum_protection": self.minimum_protection,
            "minimum_solver_improvement": self.minimum_solver_improvement,
            "solver_grid_size": self.solver_grid_size,
        }


DEFAULT_INTERPOLATION_ORACLE_THRESHOLDS = InterpolationOracleThresholds()


@dataclass(frozen=True, slots=True)
class PerceptualProgressPlan:
    schema_version: int
    method: GenerationMethod
    target_fractions: tuple[float, ...]
    direct_progress_values: tuple[float, ...]
    solved_progress_values: tuple[float, ...]
    direct_cumulative_fractions: tuple[float, ...]
    solved_cumulative_fractions: tuple[float, ...]
    direct_max_error: float
    solved_max_error: float
    improvement: float
    optimized: bool
    grid_size: int
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported perceptual progress-plan schema version")
        if not isinstance(self.method, GenerationMethod) or not self.method.is_interpolation:
            raise WavetableContractError("method must be an interpolation GenerationMethod")
        targets = _progress_values(self.target_fractions)
        direct = _progress_values(self.direct_progress_values)
        solved = _progress_values(self.solved_progress_values)
        object.__setattr__(self, "target_fractions", targets)
        object.__setattr__(self, "direct_progress_values", direct)
        object.__setattr__(self, "solved_progress_values", solved)
        if not (len(targets) == len(direct) == len(solved)):
            raise WavetableContractError("progress-plan arrays must have equal lengths")
        direct_fractions = tuple(_q(_ratio(value, name="direct cumulative fraction")) for value in self.direct_cumulative_fractions)
        solved_fractions = tuple(_q(_ratio(value, name="solved cumulative fraction")) for value in self.solved_cumulative_fractions)
        object.__setattr__(self, "direct_cumulative_fractions", direct_fractions)
        object.__setattr__(self, "solved_cumulative_fractions", solved_fractions)
        if not (len(direct_fractions) == len(targets) == len(solved_fractions)):
            raise WavetableContractError("cumulative-fraction arrays must match target count")
        for name in ("direct_max_error", "solved_max_error", "improvement"):
            _ratio(getattr(self, name), name=name)
        if self.improvement != _q(max(0.0, self.direct_max_error - self.solved_max_error)):
            raise WavetableContractError("improvement must equal direct minus solved error")
        if isinstance(self.grid_size, bool) or not isinstance(self.grid_size, int) or self.grid_size < 5:
            raise WavetableContractError("grid_size must be an integer >= 5")
        if not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "method": self.method.value,
            "target_fractions": list(self.target_fractions),
            "direct_progress_values": list(self.direct_progress_values),
            "solved_progress_values": list(self.solved_progress_values),
            "direct_cumulative_fractions": list(self.direct_cumulative_fractions),
            "solved_cumulative_fractions": list(self.solved_cumulative_fractions),
            "direct_max_error": self.direct_max_error,
            "solved_max_error": self.solved_max_error,
            "improvement": self.improvement,
            "optimized": self.optimized,
            "grid_size": self.grid_size,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _sample_path(
    left: WavetableCandidate,
    right: WavetableCandidate,
    method: GenerationMethod,
    policy: InterpolationPolicy,
    progress_values: Sequence[float],
) -> tuple[tuple[float, ...], tuple[tuple[int, ...], ...]]:
    progresses = tuple(float(value) for value in progress_values)
    waves = [left.stored_samples]
    for progress in progresses[1:-1]:
        waves.append(interpolate_xt_wave(left, right, progress, method, policy).stored_samples)
    waves.append(right.stored_samples)
    distances = [
        compare_wave_shapes(first, second).perceptual_distance
        for first, second in zip(waves, waves[1:])
    ]
    cumulative = [0.0]
    for distance in distances:
        cumulative.append(cumulative[-1] + distance)
    total = cumulative[-1]
    normalized = (
        tuple(index / (len(cumulative) - 1) for index in range(len(cumulative)))
        if total <= 1e-15
        else tuple(value / total for value in cumulative)
    )
    return tuple(_q(value) for value in normalized), tuple(waves)


def _interpolate_curve(x: Sequence[float], y: Sequence[float], value: float) -> float:
    if value <= x[0]:
        return float(y[0])
    if value >= x[-1]:
        return float(y[-1])
    for left_index in range(len(x) - 1):
        x0 = float(x[left_index])
        x1 = float(x[left_index + 1])
        if x0 <= value <= x1:
            if x1 - x0 <= 1e-15:
                return float(y[left_index])
            fraction = (value - x0) / (x1 - x0)
            return float(y[left_index] + fraction * (y[left_index + 1] - y[left_index]))
    return float(y[-1])


@lru_cache(maxsize=1024)
def solve_perceptual_progress_plan(
    left: WavetableCandidate,
    right: WavetableCandidate,
    method: GenerationMethod,
    target_fractions: Sequence[float],
    policy: InterpolationPolicy = DEFAULT_INTERPOLATION_POLICY,
    thresholds: InterpolationOracleThresholds = DEFAULT_INTERPOLATION_ORACLE_THRESHOLDS,
) -> PerceptualProgressPlan:
    if not isinstance(left, WavetableCandidate) or not isinstance(right, WavetableCandidate):
        raise WavetableContractError("left and right must be WavetableCandidate values")
    if left.candidate_id == right.candidate_id:
        raise WavetableContractError("interval endpoints must be distinct")
    if method not in policy.method_priority or not method.is_interpolation:
        raise WavetableContractError("method is not enabled by interpolation policy")
    targets = _progress_values(target_fractions)
    if method is not GenerationMethod.PERCEPTUAL_INTERPOLATION:
        direct_grid = (0.0,) + targets + (1.0,)
        direct_curve, _ = _sample_path(left, right, method, policy, direct_grid)
        direct_cumulative = tuple(direct_curve[index + 1] for index in range(len(targets)))
        direct_error = _q(max(abs(actual - target) for actual, target in zip(direct_cumulative, targets)))
        return PerceptualProgressPlan(
            schema_version=WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION,
            method=method,
            target_fractions=targets,
            direct_progress_values=targets,
            solved_progress_values=targets,
            direct_cumulative_fractions=direct_cumulative,
            solved_cumulative_fractions=direct_cumulative,
            direct_max_error=direct_error,
            solved_max_error=direct_error,
            improvement=0.0,
            optimized=False,
            grid_size=len(direct_grid),
            reason="Direct target progress retained; arc-length inversion is reserved for perceptual interpolation.",
        )
    grid = tuple(index / (thresholds.solver_grid_size - 1) for index in range(thresholds.solver_grid_size))
    cumulative, _ = _sample_path(left, right, method, policy, grid)
    direct_cumulative = tuple(_q(_interpolate_curve(grid, cumulative, target)) for target in targets)
    solved = tuple(_q(_interpolate_curve(cumulative, grid, target)) for target in targets)
    solved_cumulative = tuple(_q(_interpolate_curve(grid, cumulative, progress)) for progress in solved)
    direct_error = _q(max(abs(actual - target) for actual, target in zip(direct_cumulative, targets)))
    solved_error = _q(max(abs(actual - target) for actual, target in zip(solved_cumulative, targets)))
    optimized = solved_error + thresholds.minimum_solver_improvement <= direct_error
    final_progress = solved if optimized else targets
    final_cumulative = solved_cumulative if optimized else direct_cumulative
    final_error = solved_error if optimized else direct_error
    improvement = _q(max(0.0, direct_error - final_error))
    return PerceptualProgressPlan(
        schema_version=WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION,
        method=method,
        target_fractions=targets,
        direct_progress_values=targets,
        solved_progress_values=final_progress,
        direct_cumulative_fractions=direct_cumulative,
        solved_cumulative_fractions=final_cumulative,
        direct_max_error=direct_error,
        solved_max_error=final_error,
        improvement=improvement,
        optimized=optimized,
        grid_size=thresholds.solver_grid_size,
        reason=(
            "Arc-length progress inversion improved the XT-native perceptual path."
            if optimized
            else "Direct progress retained because the solver did not improve the measured path."
        ),
    )


@dataclass(frozen=True, slots=True)
class InterpolationMethodOracle:
    schema_version: int
    method: GenerationMethod
    progress_plan: PerceptualProgressPlan
    mean_objective_score: float
    spacing_regularity_score: float
    spectral_path_score: float
    harmonic_path_score: float
    protection_score: float
    aggregate_score: float
    passed: bool
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported interpolation oracle schema version")
        if not isinstance(self.method, GenerationMethod) or not self.method.is_interpolation:
            raise WavetableContractError("oracle method must be an interpolation method")
        if not isinstance(self.progress_plan, PerceptualProgressPlan) or self.progress_plan.method is not self.method:
            raise WavetableContractError("oracle progress plan must match its method")
        for name in (
            "mean_objective_score",
            "spacing_regularity_score",
            "spectral_path_score",
            "harmonic_path_score",
            "protection_score",
            "aggregate_score",
        ):
            _ratio(getattr(self, name), name=name)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not self.evidence or not self.reason:
            raise WavetableContractError("oracle evidence and reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "method": self.method.value,
            "progress_plan": self.progress_plan.to_dict(),
            "mean_objective_score": self.mean_objective_score,
            "spacing_regularity_score": self.spacing_regularity_score,
            "spectral_path_score": self.spectral_path_score,
            "harmonic_path_score": self.harmonic_path_score,
            "protection_score": self.protection_score,
            "aggregate_score": self.aggregate_score,
            "passed": self.passed,
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


@lru_cache(maxsize=2048)
def evaluate_interval_interpolation_method(
    left: WavetableCandidate,
    right: WavetableCandidate,
    method: GenerationMethod,
    policy: InterpolationPolicy = DEFAULT_INTERPOLATION_POLICY,
    target_fractions: Sequence[float] = (0.25, 0.5, 0.75),
    thresholds: InterpolationOracleThresholds = DEFAULT_INTERPOLATION_ORACLE_THRESHOLDS,
) -> InterpolationMethodOracle:
    plan = solve_perceptual_progress_plan(
        left,
        right,
        method,
        target_fractions,
        policy,
        thresholds,
    )
    waves = tuple(
        interpolate_xt_wave(left, right, progress, method, policy)
        for progress in plan.solved_progress_values
    )
    path_samples = (
        (left.stored_samples,)
        + tuple(item.stored_samples for item in waves)
        + (right.stored_samples,)
    )
    adjacent = tuple(
        compare_wave_shapes(first, second)
        for first, second in zip(path_samples, path_samples[1:])
    )
    distances = tuple(item.perceptual_distance for item in adjacent)
    mean_distance = sum(distances) / len(distances)
    spacing_error = sum(abs(value - mean_distance) for value in distances) / len(distances)
    spacing_score = _q(max(0.0, min(1.0, 1.0 - spacing_error)))

    spectral_distances = tuple(item.spectral_distance for item in adjacent)
    mean_spectral = sum(spectral_distances) / len(spectral_distances)
    spectral_error = sum(abs(value - mean_spectral) for value in spectral_distances) / len(spectral_distances)
    spectral_score = _q(max(0.0, min(1.0, 1.0 - spectral_error)))

    left_h = _harmonic_magnitudes(left.stored_samples)
    right_h = _harmonic_magnitudes(right.stored_samples)
    harmonic_errors: list[float] = []
    for target, wave in zip(plan.target_fractions, waves):
        measured = _harmonic_magnitudes(wave.stored_samples)
        harmonic_errors.extend(
            abs(
                measured[index]
                - ((1.0 - target) * left_h[index] + target * right_h[index])
            )
            for index in range(3)
        )
    harmonic_score = _q(
        max(0.0, min(1.0, 1.0 - sum(harmonic_errors) / max(1, len(harmonic_errors))))
    )
    protection_score = _q(
        max(
            0.0,
            min(
                1.0,
                1.0
                - sum(
                    (
                        wave.level_error
                        + wave.fundamental_error
                        + (1.0 - wave.polarity_score)
                    )
                    / 3.0
                    for wave in waves
                )
                / len(waves),
            ),
        )
    )
    mean_objective = _q(sum(wave.objective_score for wave in waves) / len(waves))
    aggregate = _q(
        0.35 * mean_objective
        + 0.25 * spacing_score
        + 0.15 * spectral_score
        + 0.15 * harmonic_score
        + 0.10 * protection_score
    )
    passed = (
        spacing_score >= thresholds.minimum_spacing_regularity
        and spectral_score >= thresholds.minimum_spectral_path
        and harmonic_score >= thresholds.minimum_harmonic_path
        and protection_score >= thresholds.minimum_protection
        and all(
            wave.level_error <= policy.level_tolerance + 1e-12
            and wave.fundamental_error <= policy.fundamental_tolerance + 1e-12
            for wave in waves
        )
    )
    return InterpolationMethodOracle(
        schema_version=WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION,
        method=method,
        progress_plan=plan,
        mean_objective_score=mean_objective,
        spacing_regularity_score=spacing_score,
        spectral_path_score=spectral_score,
        harmonic_path_score=harmonic_score,
        protection_score=protection_score,
        aggregate_score=aggregate,
        passed=passed,
        evidence=(
            f"target fractions {plan.target_fractions}",
            f"progress plan {plan.analysis_sha256}",
            "weights objective=.35 spacing=.25 spectral=.15 harmonic=.15 protection=.10",
        ),
        reason="Quantitative V8-G oracle for one complete interpolation interval.",
    )


@dataclass(frozen=True, slots=True)
class TransitionIntervalDecision:
    schema_version: int
    left_candidate_id: str
    right_candidate_id: str
    selected_method: GenerationMethod
    target_fractions: tuple[float, ...]
    oracles: tuple[InterpolationMethodOracle, ...]
    selected_oracle_sha256: str
    selected_progress_plan: PerceptualProgressPlan
    fallback_used: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported transition decision schema version")
        if not self.left_candidate_id or not self.right_candidate_id or self.left_candidate_id == self.right_candidate_id:
            raise WavetableContractError("transition endpoints must be distinct non-empty IDs")
        if not isinstance(self.selected_method, GenerationMethod) or not self.selected_method.is_interpolation:
            raise WavetableContractError("selected_method must be an interpolation method")
        targets = _progress_values(self.target_fractions)
        object.__setattr__(self, "target_fractions", targets)
        object.__setattr__(self, "oracles", tuple(self.oracles))
        if not self.oracles:
            raise WavetableContractError("oracles must not be empty")
        matching = tuple(item for item in self.oracles if item.method is self.selected_method)
        if len(matching) != 1:
            raise WavetableContractError("selected method must have exactly one oracle")
        if matching[0].analysis_sha256 != self.selected_oracle_sha256:
            raise WavetableContractError("selected oracle SHA-256 mismatch")
        if self.selected_progress_plan.analysis_sha256 != matching[0].progress_plan.analysis_sha256:
            raise WavetableContractError("selected progress plan does not match selected oracle")
        if self.selected_progress_plan.target_fractions != targets:
            raise WavetableContractError("selected progress plan target fractions mismatch")
        if not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "left_candidate_id": self.left_candidate_id,
            "right_candidate_id": self.right_candidate_id,
            "selected_method": self.selected_method.value,
            "target_fractions": list(self.target_fractions),
            "oracles": [item.to_dict() for item in self.oracles],
            "selected_oracle_sha256": self.selected_oracle_sha256,
            "selected_progress_plan": self.selected_progress_plan.to_dict(),
            "fallback_used": self.fallback_used,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@lru_cache(maxsize=1024)
def select_interval_interpolation_method(
    left: WavetableCandidate,
    right: WavetableCandidate,
    allowed_methods: Sequence[GenerationMethod],
    policy: InterpolationPolicy = DEFAULT_INTERPOLATION_POLICY,
    target_fractions: Sequence[float] = (0.25, 0.5, 0.75),
    thresholds: InterpolationOracleThresholds = DEFAULT_INTERPOLATION_ORACLE_THRESHOLDS,
) -> TransitionIntervalDecision:
    if not isinstance(policy, InterpolationPolicy):
        raise WavetableContractError("policy must be InterpolationPolicy")
    allowed = tuple(allowed_methods)
    if not allowed or len(set(allowed)) != len(allowed):
        raise WavetableContractError("allowed_methods must be non-empty and unique")
    methods = tuple(
        method for method in policy.method_priority if method in allowed and method.is_interpolation
    )
    if not methods:
        raise WavetableContractError("no enabled interpolation method is available")
    targets = _progress_values(target_fractions)
    evaluated_methods = methods if policy.adaptive_method_selection else methods[:1]
    oracles = tuple(
        evaluate_interval_interpolation_method(
            left,
            right,
            method,
            policy,
            targets,
            thresholds,
        )
        for method in evaluated_methods
    )
    passing = tuple(item for item in oracles if item.passed)
    pool = passing or oracles
    priority = {method: index for index, method in enumerate(policy.method_priority)}
    selected = min(
        pool,
        key=lambda item: (
            -item.aggregate_score,
            -item.protection_score,
            item.progress_plan.solved_max_error,
            priority[item.method],
            item.analysis_sha256,
        ),
    )
    fallback = not bool(passing)
    return TransitionIntervalDecision(
        schema_version=WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION,
        left_candidate_id=left.candidate_id,
        right_candidate_id=right.candidate_id,
        selected_method=selected.method,
        target_fractions=targets,
        oracles=oracles,
        selected_oracle_sha256=selected.analysis_sha256,
        selected_progress_plan=selected.progress_plan,
        fallback_used=fallback,
        reason=(
            "One immutable interpolation method selected for the complete interval."
            if not fallback
            else "No method passed every oracle; the deterministic safest method was selected and flagged."
        ),
    )


__all__ = [
    "WAVETABLE_TRANSITION_PLANNER_SCHEMA_VERSION",
    "AdaptiveSlotBudgetPolicy",
    "DEFAULT_ADAPTIVE_SLOT_BUDGET_POLICY",
    "RegionSlotBudget",
    "AdaptiveSlotBudgetPlan",
    "InterpolationOracleThresholds",
    "DEFAULT_INTERPOLATION_ORACLE_THRESHOLDS",
    "PerceptualProgressPlan",
    "InterpolationMethodOracle",
    "TransitionIntervalDecision",
    "plan_adaptive_slot_budget",
    "solve_perceptual_progress_plan",
    "evaluate_interval_interpolation_method",
    "select_interval_interpolation_method",
]
