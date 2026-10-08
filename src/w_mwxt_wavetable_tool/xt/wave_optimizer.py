from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any, Sequence

import numpy as np

from ..errors import AnalysisError
from ..profiles import (
    BassSequenceConsistency,
    OptimizationProfile,
    ProfileDefinition,
    analyze_bass_sequence_consistency,
    profile_definition,
)
from .quantization import QuantizationAlgorithm
from .resampling import NormalizationPolicy
from .symmetry_candidates import (
    HalfWaveMethod,
    SymmetryCandidate,
    SymmetryTreatment,
    WaveTransform,
    build_symmetry_candidate,
)
from .wave_metrics import (
    XtAliasingAnalysis,
    XtWaveMetrics,
    analyze_xt_aliasing_risk,
    measure_xt_wave_metrics,
)


_EPSILON = 1.0e-12


class OptimizationStatus(str, Enum):
    AUTOMATIC = "automatic"
    OVERRIDDEN = "overridden"


def _canonical_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


def _sample_hash(samples: Sequence[float]) -> str:
    values = np.asarray(tuple(float(value) for value in samples), dtype="<f8")
    return sha256(values.tobytes(order="C")).hexdigest()


def _validate_source(samples: Sequence[float]) -> tuple[float, ...]:
    values = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if values.shape != (128,):
        raise AnalysisError("XT wave optimization requires exactly 128 source samples")
    if not np.all(np.isfinite(values)):
        raise AnalysisError("source wave contains NaN or infinite values")
    if float(np.max(np.abs(values))) > 1.0 + _EPSILON:
        raise AnalysisError("source wave exceeds normalized range [-1, 1]")
    if float(np.max(np.abs(values))) <= _EPSILON:
        raise AnalysisError("silent source waves cannot be optimized")
    return tuple(float(value) for value in values)


def _high_band_ratio(samples: Sequence[float]) -> float:
    values = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    power = np.square(np.abs(np.fft.rfft(values))[1:])
    total = float(np.sum(power, dtype=np.float64))
    if total <= _EPSILON:
        return 0.0
    return float(np.sum(power[16:], dtype=np.float64) / total)


def _controlled_defect_error(source: Sequence[float], reconstructed: Sequence[float]) -> float:
    left = np.asarray(source, dtype=np.float64)
    right = np.asarray(reconstructed, dtype=np.float64)

    def asymmetry(values: np.ndarray) -> float:
        positive = values[values >= 0.0]
        negative = values[values < 0.0]
        positive_mean = float(np.mean(positive)) if positive.size else 0.0
        negative_mean = abs(float(np.mean(negative))) if negative.size else 0.0
        denominator = max(positive_mean + negative_mean, _EPSILON)
        return min(1.0, abs(positive_mean - negative_mean) / denominator)

    def roughness(values: np.ndarray) -> float:
        magnitude = np.abs(np.fft.rfft(values))[1:]
        total = float(np.sum(magnitude))
        if total <= _EPSILON:
            return 0.0
        normalized = magnitude / total
        return min(1.0, float(np.sum(np.abs(np.diff(normalized)))))

    def saturation(values: np.ndarray) -> float:
        peak = float(np.max(np.abs(values)))
        rms = float(np.sqrt(np.mean(np.square(values))))
        crest = peak / max(rms, _EPSILON)
        return min(1.0, max(0.0, 1.0 - min(1.0, crest / math.sqrt(2.0))))

    def aliasing_propensity(values: np.ndarray) -> float:
        power = np.square(np.abs(np.fft.rfft(values))[1:])
        total = float(np.sum(power))
        if total <= _EPSILON:
            return 0.0
        return min(1.0, float(np.sum(power[16:]) / total))

    def fundamental_phase(values: np.ndarray) -> float:
        coefficient = np.fft.rfft(values)[1]
        return float(np.angle(coefficient))

    def seam_defect(values: np.ndarray) -> float:
        peak = max(float(np.max(np.abs(values))), _EPSILON)
        value_jump = abs(float(values[0] - values[-1])) / (2.0 * peak)
        left_slope = float(values[1] - values[0])
        right_slope = float(values[0] - values[-1])
        slope_jump = abs(left_slope - right_slope) / (2.0 * peak)
        return min(1.0, 0.5 * value_jump + 0.5 * slope_jump)

    phase_delta = abs(fundamental_phase(left) - fundamental_phase(right))
    phase_delta = min(phase_delta, 2.0 * math.pi - phase_delta) / math.pi
    components = (
        abs(aliasing_propensity(left) - aliasing_propensity(right)),
        abs(asymmetry(left) - asymmetry(right)),
        abs(saturation(left) - saturation(right)),
        min(1.0, phase_delta),
        abs(roughness(left) - roughness(right)),
        abs(seam_defect(left) - seam_defect(right)),
    )
    return min(1.0, float(sum(components) / len(components)))


@dataclass(frozen=True, slots=True)
class OptimizerSearchConfig:
    phases: tuple[int, ...] = tuple(range(128))
    transforms: tuple[WaveTransform, ...] = tuple(WaveTransform)
    half_wave_methods: tuple[HalfWaveMethod, ...] = tuple(HalfWaveMethod)
    quantization_algorithms: tuple[QuantizationAlgorithm, ...] = (
        QuantizationAlgorithm.NEAREST,
    )
    normalization: NormalizationPolicy | None = None
    top_candidate_count: int = 16

    def __post_init__(self) -> None:
        object.__setattr__(self, "phases", tuple(int(value) for value in self.phases))
        object.__setattr__(
            self,
            "transforms",
            tuple(WaveTransform(value) for value in self.transforms),
        )
        object.__setattr__(
            self,
            "half_wave_methods",
            tuple(HalfWaveMethod(value) for value in self.half_wave_methods),
        )
        object.__setattr__(
            self,
            "quantization_algorithms",
            tuple(QuantizationAlgorithm(value) for value in self.quantization_algorithms),
        )
        if self.normalization is not None:
            object.__setattr__(
                self,
                "normalization",
                NormalizationPolicy(self.normalization),
            )
        if not self.phases or len(set(self.phases)) != len(self.phases):
            raise AnalysisError("phases must be non-empty and unique")
        if any(value < 0 or value >= 128 for value in self.phases):
            raise AnalysisError("phases must stay in 0..127")
        if not self.transforms or len(set(self.transforms)) != len(self.transforms):
            raise AnalysisError("transforms must be non-empty and unique")
        if not self.half_wave_methods or len(set(self.half_wave_methods)) != len(self.half_wave_methods):
            raise AnalysisError("half_wave_methods must be non-empty and unique")
        if not self.quantization_algorithms or len(set(self.quantization_algorithms)) != len(self.quantization_algorithms):
            raise AnalysisError("quantization_algorithms must be non-empty and unique")
        if self.top_candidate_count <= 0:
            raise AnalysisError("top_candidate_count must be positive")

    @property
    def candidate_count(self) -> int:
        return (
            len(self.phases)
            * len(self.transforms)
            * len(self.half_wave_methods)
            * len(self.quantization_algorithms)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "phases": list(self.phases),
            "transforms": [item.value for item in self.transforms],
            "half_wave_methods": [item.value for item in self.half_wave_methods],
            "quantization_algorithms": [item.value for item in self.quantization_algorithms],
            "normalization": None if self.normalization is None else self.normalization.value,
            "top_candidate_count": self.top_candidate_count,
            "candidate_count": self.candidate_count,
        }


@dataclass(frozen=True, slots=True)
class XtCandidateEvaluation:
    candidate_sha256: str
    treatment: SymmetryTreatment
    metrics: XtWaveMetrics
    weighted_objective: float
    controlled_defect_error: float
    final_objective: float

    def __post_init__(self) -> None:
        if len(self.candidate_sha256) != 64:
            raise AnalysisError("candidate_sha256 must be a SHA-256 digest")
        for name in ("weighted_objective", "controlled_defect_error", "final_objective"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise AnalysisError(f"{name} must be a finite ratio")
        if self.final_objective + 1.0e-12 < self.weighted_objective:
            raise AnalysisError("final_objective must not be lower than weighted_objective")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_sha256": self.candidate_sha256,
            "treatment": self.treatment.to_dict(),
            "metrics": self.metrics.to_dict(),
            "weighted_objective": self.weighted_objective,
            "controlled_defect_error": self.controlled_defect_error,
            "final_objective": self.final_objective,
        }


@dataclass(frozen=True, slots=True)
class XtWaveRepresentations:
    original_source: tuple[float, ...]
    working_128: tuple[float, ...]
    native_64_float: tuple[float, ...]
    quantized_native_64: tuple[int, ...]
    reconstructed_128: tuple[float, ...]
    before_optimization: tuple[float, ...]
    after_optimization: tuple[float, ...]

    def __post_init__(self) -> None:
        for name in (
            "original_source",
            "working_128",
            "reconstructed_128",
            "before_optimization",
            "after_optimization",
        ):
            if len(getattr(self, name)) != 128:
                raise AnalysisError(f"{name} must contain 128 samples")
        if len(self.native_64_float) != 64 or len(self.quantized_native_64) != 64:
            raise AnalysisError("native representations must contain 64 samples")
        if any(value < -127 or value > 127 for value in self.quantized_native_64):
            raise AnalysisError("quantized native values must stay in -127..127")

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_source": list(self.original_source),
            "working_128": list(self.working_128),
            "native_64_float": list(self.native_64_float),
            "quantized_native_64": list(self.quantized_native_64),
            "reconstructed_128": list(self.reconstructed_128),
            "before_optimization": list(self.before_optimization),
            "after_optimization": list(self.after_optimization),
        }


@dataclass(frozen=True, slots=True)
class BassProtectionReport:
    source_high_band_ratio: float
    reconstructed_high_band_ratio: float
    upper_harmonic_reduction: float
    sub_score: float
    bass_score: float
    monophonic_bass_warning: bool
    pitch_comparison_required: bool
    explanation: str

    def __post_init__(self) -> None:
        for name in (
            "source_high_band_ratio",
            "reconstructed_high_band_ratio",
            "upper_harmonic_reduction",
            "sub_score",
            "bass_score",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise AnalysisError(f"{name} must be a finite ratio")
        if not self.explanation or self.explanation.strip() != self.explanation:
            raise AnalysisError("explanation must be normalized")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_high_band_ratio": self.source_high_band_ratio,
            "reconstructed_high_band_ratio": self.reconstructed_high_band_ratio,
            "upper_harmonic_reduction": self.upper_harmonic_reduction,
            "sub_score": self.sub_score,
            "bass_score": self.bass_score,
            "monophonic_bass_warning": self.monophonic_bass_warning,
            "pitch_comparison_required": self.pitch_comparison_required,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class XtWaveOptimizationResult:
    schema_version: int
    source_samples_sha256: str
    profile: ProfileDefinition
    status: OptimizationStatus
    automatic_treatment: SymmetryTreatment
    requested_treatment: SymmetryTreatment | None
    selected_candidate: SymmetryCandidate
    selected_metrics: XtWaveMetrics
    aliasing_analysis: XtAliasingAnalysis
    selected_objective: float
    search_config: OptimizerSearchConfig
    top_candidates: tuple[XtCandidateEvaluation, ...]
    representations: XtWaveRepresentations
    bass_protection: BassProtectionReport
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported XT-wave-optimization schema version")
        if len(self.source_samples_sha256) != 64:
            raise AnalysisError("source_samples_sha256 must be a SHA-256 digest")
        if self.selected_candidate.source_samples_sha256 != self.source_samples_sha256:
            raise AnalysisError("selected candidate source hash is inconsistent")
        if self.selected_metrics.source_samples_sha256 != self.source_samples_sha256:
            raise AnalysisError("selected metrics source hash is inconsistent")
        if self.aliasing_analysis.samples_sha256 != self.selected_metrics.reconstructed_samples_sha256:
            raise AnalysisError("aliasing analysis does not link to selected reconstruction")
        if not self.top_candidates:
            raise AnalysisError("top_candidates must not be empty")
        if len(self.top_candidates) > self.search_config.top_candidate_count:
            raise AnalysisError("top_candidates exceeds configured count")
        if tuple(item.final_objective for item in self.top_candidates) != tuple(sorted(item.final_objective for item in self.top_candidates)):
            raise AnalysisError("top_candidates must be sorted by final objective")
        automatic = self.top_candidates[0].treatment
        if automatic != self.automatic_treatment:
            raise AnalysisError("automatic_treatment must match the best candidate")
        if self.status is OptimizationStatus.AUTOMATIC:
            if self.requested_treatment is not None or self.selected_candidate.treatment != self.automatic_treatment:
                raise AnalysisError("automatic result has inconsistent treatment state")
        else:
            if self.requested_treatment is None or self.selected_candidate.treatment != self.requested_treatment:
                raise AnalysisError("overridden result has inconsistent treatment state")
        if not math.isfinite(self.selected_objective) or not 0.0 <= self.selected_objective <= 1.0:
            raise AnalysisError("selected_objective must be a finite ratio")
        if any(not item or item.strip() != item for item in self.warnings):
            raise AnalysisError("warnings must contain normalized strings")
        if not self.reason or self.reason.strip() != self.reason:
            raise AnalysisError("reason must be normalized")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_samples_sha256": self.source_samples_sha256,
            "profile": self.profile.to_dict(),
            "status": self.status.value,
            "automatic_treatment": self.automatic_treatment.to_dict(),
            "requested_treatment": None if self.requested_treatment is None else self.requested_treatment.to_dict(),
            "selected_candidate": self.selected_candidate.to_dict(),
            "selected_metrics": self.selected_metrics.to_dict(),
            "aliasing_analysis": self.aliasing_analysis.to_dict(),
            "selected_objective": self.selected_objective,
            "search_config": self.search_config.to_dict(),
            "top_candidates": [item.to_dict() for item in self.top_candidates],
            "representations": self.representations.to_dict(),
            "bass_protection": self.bass_protection.to_dict(),
            "warnings": list(self.warnings),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _evaluate_candidate(
    source: tuple[float, ...],
    candidate: SymmetryCandidate,
    profile: ProfileDefinition,
) -> XtCandidateEvaluation:
    resampling_aliasing = 0.0 if candidate.resampling is None else candidate.resampling.metrics.aliasing_risk
    ringing = 0.0 if candidate.resampling is None else candidate.resampling.metrics.ringing_score
    note_aliasing = analyze_xt_aliasing_risk(candidate.reconstructed_aligned).maximum_risk
    aliasing = max(resampling_aliasing, note_aliasing)
    metrics = measure_xt_wave_metrics(
        source,
        candidate.reconstructed_aligned,
        aliasing_risk=aliasing,
        ringing_score=ringing,
    )
    weighted = metrics.weighted_objective(profile.weights)
    defect_error = (
        _controlled_defect_error(source, candidate.reconstructed_aligned)
        if profile.profile is OptimizationProfile.EXPERIMENTAL
        else 0.0
    )
    final = min(1.0, weighted + 0.15 * defect_error)
    return XtCandidateEvaluation(
        candidate_sha256=candidate.analysis_sha256,
        treatment=candidate.treatment,
        metrics=metrics,
        weighted_objective=weighted,
        controlled_defect_error=defect_error,
        final_objective=final,
    )


def optimize_xt_wave(
    samples: Sequence[float],
    *,
    profile: OptimizationProfile | ProfileDefinition = OptimizationProfile.LEAD,
    requested_treatment: SymmetryTreatment | None = None,
    search_config: OptimizerSearchConfig | None = None,
) -> XtWaveOptimizationResult:
    """Compare XT-native treatments and return an explainable profile-weighted optimum."""

    source = _validate_source(samples)
    definition = profile if isinstance(profile, ProfileDefinition) else profile_definition(OptimizationProfile(profile))
    config = OptimizerSearchConfig() if search_config is None else search_config
    normalization = config.normalization
    if normalization is None:
        normalization = (
            NormalizationPolicy.BASS_PROTECT
            if definition.profile is OptimizationProfile.BASS_SUB
            else NormalizationPolicy.NONE
        )

    candidate_by_treatment: dict[SymmetryTreatment, SymmetryCandidate] = {}
    evaluations: list[XtCandidateEvaluation] = []
    for transform in config.transforms:
        for phase in config.phases:
            for method in config.half_wave_methods:
                for quantization in config.quantization_algorithms:
                    treatment = SymmetryTreatment(
                        transform=transform,
                        phase_rotation_samples=phase,
                        half_wave_method=method,
                        quantization_algorithm=quantization,
                        normalization=normalization,
                    )
                    candidate = build_symmetry_candidate(source, treatment)
                    candidate_by_treatment[treatment] = candidate
                    evaluations.append(_evaluate_candidate(source, candidate, definition))

    evaluations.sort(
        key=lambda item: (
            item.final_objective,
            item.metrics.time_nrmse,
            item.metrics.spectral_rmse,
            item.treatment.treatment_id,
        )
    )
    automatic = evaluations[0]
    top = tuple(evaluations[: min(config.top_candidate_count, len(evaluations))])
    selected_evaluation = automatic
    selected_candidate = candidate_by_treatment[automatic.treatment]
    warnings: list[str] = []
    status = OptimizationStatus.AUTOMATIC
    if requested_treatment is not None:
        requested = requested_treatment
        candidate = candidate_by_treatment.get(requested)
        if candidate is None:
            candidate = build_symmetry_candidate(source, requested)
        selected_candidate = candidate
        selected_evaluation = _evaluate_candidate(source, candidate, definition)
        status = OptimizationStatus.OVERRIDDEN
        if requested != automatic.treatment:
            warnings.append(
                "Manual treatment override differs from the automatic profile-weighted optimum."
            )
    if selected_evaluation.metrics.monophonic_bass_warning:
        warnings.append(
            "Selected reconstruction is unstable for monophonic Bass/Sub use under the current metrics."
        )
    if definition.profile is OptimizationProfile.EXPERIMENTAL:
        warnings.append(
            "Experimental preserves named controlled defects while retaining all hard numeric safety gates."
        )

    source_high = _high_band_ratio(source)
    reconstructed_high = _high_band_ratio(selected_candidate.reconstructed_aligned)
    high_reduction = max(0.0, source_high - reconstructed_high)
    bass_report = BassProtectionReport(
        source_high_band_ratio=source_high,
        reconstructed_high_band_ratio=reconstructed_high,
        upper_harmonic_reduction=min(1.0, high_reduction),
        sub_score=selected_evaluation.metrics.sub_score,
        bass_score=selected_evaluation.metrics.bass_score,
        monophonic_bass_warning=selected_evaluation.metrics.monophonic_bass_warning,
        pitch_comparison_required=definition.profile is OptimizationProfile.BASS_SUB,
        explanation=(
            "Sub and Bass are reported separately. Bass/Sub builds also require the accepted "
            "V6 working-pitch candidates to be compared by evaluate_bass_working_pitches."
        ),
    )
    aliasing_analysis = analyze_xt_aliasing_risk(selected_candidate.reconstructed_aligned)
    representations = XtWaveRepresentations(
        original_source=source,
        working_128=source,
        native_64_float=selected_candidate.stored_float_samples,
        quantized_native_64=selected_candidate.quantization.quantized_samples,
        reconstructed_128=selected_candidate.reconstructed_aligned,
        before_optimization=source,
        after_optimization=selected_candidate.reconstructed_aligned,
    )
    reason = (
        f"Automatic {definition.profile.value} optimization selected {automatic.treatment.treatment_id} "
        f"from {config.candidate_count} deterministic candidates."
        if status is OptimizationStatus.AUTOMATIC
        else (
            f"Manual treatment {selected_candidate.treatment.treatment_id} was selected while "
            f"automatic optimum {automatic.treatment.treatment_id} remains recorded."
        )
    )
    return XtWaveOptimizationResult(
        schema_version=1,
        source_samples_sha256=_sample_hash(source),
        profile=definition,
        status=status,
        automatic_treatment=automatic.treatment,
        requested_treatment=requested_treatment,
        selected_candidate=selected_candidate,
        selected_metrics=selected_evaluation.metrics,
        aliasing_analysis=aliasing_analysis,
        selected_objective=selected_evaluation.final_objective,
        search_config=config,
        top_candidates=top,
        representations=representations,
        bass_protection=bass_report,
        warnings=tuple(warnings),
        reason=reason,
    )


@dataclass(frozen=True, slots=True)
class XtWaveOptimizationEntry:
    index: int
    result: XtWaveOptimizationResult

    def __post_init__(self) -> None:
        if self.index < 0:
            raise AnalysisError("wave optimization index must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class XtWaveSetOptimization:
    schema_version: int
    profile: ProfileDefinition
    entries: tuple[XtWaveOptimizationEntry, ...]
    bass_sequence_consistency: BassSequenceConsistency | None
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported XT-wave-set-optimization schema version")
        if not self.entries:
            raise AnalysisError("wave-set optimization requires at least one wave")
        if tuple(item.index for item in self.entries) != tuple(range(len(self.entries))):
            raise AnalysisError("wave-set optimization indexes must be contiguous from zero")
        if any(item.result.profile.profile is not self.profile.profile for item in self.entries):
            raise AnalysisError("all wave results must use the aggregate profile")
        if self.profile.profile is OptimizationProfile.BASS_SUB:
            if self.bass_sequence_consistency is None:
                raise AnalysisError("Bass/Sub wave sets require sequence consistency evidence")
        elif self.bass_sequence_consistency is not None:
            raise AnalysisError("only Bass/Sub wave sets expose Bass sequence consistency")
        if not self.reason or self.reason.strip() != self.reason:
            raise AnalysisError("reason must be normalized")

    @property
    def wave_count(self) -> int:
        return len(self.entries)

    @property
    def objective_summary(self) -> dict[str, float]:
        values = np.asarray(
            [item.result.selected_objective for item in self.entries],
            dtype=np.float64,
        )
        return {
            "minimum": float(np.min(values)),
            "mean": float(np.mean(values)),
            "maximum": float(np.max(values)),
        }

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile.to_dict(),
            "wave_count": self.wave_count,
            "objective_summary": self.objective_summary,
            "entries": [item.to_dict() for item in self.entries],
            "bass_sequence_consistency": (
                None
                if self.bass_sequence_consistency is None
                else self.bass_sequence_consistency.to_dict()
            ),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def optimize_xt_wave_set(
    waves: Sequence[Sequence[float]],
    *,
    profile: OptimizationProfile | ProfileDefinition = OptimizationProfile.LEAD,
    requested_treatments: Sequence[SymmetryTreatment | None] | None = None,
    search_config: OptimizerSearchConfig | None = None,
) -> XtWaveSetOptimization:
    """Optimize each wave independently and preserve canonical source order."""

    source_waves = tuple(waves)
    if not source_waves:
        raise AnalysisError("wave-set optimization requires at least one wave")
    definition = (
        profile
        if isinstance(profile, ProfileDefinition)
        else profile_definition(OptimizationProfile(profile))
    )
    if requested_treatments is None:
        overrides: tuple[SymmetryTreatment | None, ...] = tuple(
            None for _ in source_waves
        )
    else:
        overrides = tuple(requested_treatments)
        if len(overrides) != len(source_waves):
            raise AnalysisError("requested_treatments must match the wave count")
    entries = tuple(
        XtWaveOptimizationEntry(
            index=index,
            result=optimize_xt_wave(
                samples,
                profile=definition,
                requested_treatment=overrides[index],
                search_config=search_config,
            ),
        )
        for index, samples in enumerate(source_waves)
    )
    consistency = (
        analyze_bass_sequence_consistency(
            tuple(item.result.selected_metrics for item in entries)
        )
        if definition.profile is OptimizationProfile.BASS_SUB
        else None
    )
    return XtWaveSetOptimization(
        schema_version=1,
        profile=definition,
        entries=entries,
        bass_sequence_consistency=consistency,
        reason=(
            "Every input wave was optimized independently under one effective profile; "
            "canonical source order was preserved for the later V8 builder."
        ),
    )


@dataclass(frozen=True, slots=True)
class XtCycleCompatibility:
    schema_version: int
    source_samples_sha256: str
    optimization_sha256: str
    profile: OptimizationProfile
    xt_compatibility_score: float
    psychoacoustic_quality_score: float
    sub_score: float
    bass_score: float
    recommended: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported XT-cycle-compatibility schema version")
        for name in ("source_samples_sha256", "optimization_sha256"):
            value = getattr(self, name)
            if len(value) != 64:
                raise AnalysisError(f"{name} must be a SHA-256 digest")
        for name in (
            "xt_compatibility_score",
            "psychoacoustic_quality_score",
            "sub_score",
            "bass_score",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise AnalysisError(f"{name} must be a finite ratio")
        expected = self.xt_compatibility_score >= 0.55 and self.psychoacoustic_quality_score >= 0.55
        if self.recommended != expected:
            raise AnalysisError("recommended is inconsistent with compatibility thresholds")
        if not self.reason or self.reason.strip() != self.reason:
            raise AnalysisError("reason must be normalized")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_samples_sha256": self.source_samples_sha256,
            "optimization_sha256": self.optimization_sha256,
            "profile": self.profile.value,
            "xt_compatibility_score": self.xt_compatibility_score,
            "psychoacoustic_quality_score": self.psychoacoustic_quality_score,
            "sub_score": self.sub_score,
            "bass_score": self.bass_score,
            "recommended": self.recommended,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def evaluate_cycle_xt_compatibility(
    samples: Sequence[float],
    *,
    profile: OptimizationProfile | ProfileDefinition = OptimizationProfile.LEAD,
    search_config: OptimizerSearchConfig | None = None,
) -> XtCycleCompatibility:
    """Measure XT compatibility and psychoacoustic quality for one 128-point cycle."""

    result = optimize_xt_wave(
        samples,
        profile=profile,
        search_config=search_config,
    )
    xt_score = max(0.0, 1.0 - result.selected_objective)
    psychoacoustic = max(0.0, 1.0 - result.selected_metrics.perceptual_difference)
    recommended = xt_score >= 0.55 and psychoacoustic >= 0.55
    return XtCycleCompatibility(
        schema_version=1,
        source_samples_sha256=result.source_samples_sha256,
        optimization_sha256=result.analysis_sha256,
        profile=result.profile.profile,
        xt_compatibility_score=xt_score,
        psychoacoustic_quality_score=psychoacoustic,
        sub_score=result.selected_metrics.sub_score,
        bass_score=result.selected_metrics.bass_score,
        recommended=recommended,
        reason=(
            "Compatibility is the complement of the selected profile-weighted XT objective; "
            "psychoacoustic quality is the complement of source-versus-reconstruction perceptual distance."
        ),
    )
