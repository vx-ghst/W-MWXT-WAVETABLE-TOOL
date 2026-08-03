from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import numpy.typing as npt

from ..errors import AnalysisError
from .models import (
    RepairActionKind,
    RepairContext,
    RepairDefect,
    RepairFinding,
    RepairSeverity,
    RepairThresholds,
    RepairWaveMetrics,
    _sample_hash,
)


_EPSILON = 1.0e-12
FloatArray = npt.NDArray[np.float64]


_ACTION_BY_DEFECT = {
    RepairDefect.DC_OFFSET: RepairActionKind.REMOVE_DC,
    RepairDefect.CLIPPING: RepairActionKind.RECONSTRUCT_CLIPPED_PEAKS,
    RepairDefect.ZERO_CROSSING: RepairActionKind.ROTATE_TO_ZERO_CROSSING,
    RepairDefect.LOOP_DISCONTINUITY: RepairActionKind.SMOOTH_LOOP_SEAM,
    RepairDefect.DERIVATIVE_DISCONTINUITY: RepairActionKind.SMOOTH_SEAM_DERIVATIVE,
    RepairDefect.PHASE_INVERSION: RepairActionKind.ALIGN_PHASE_TO_REFERENCE,
    RepairDefect.POLARITY_INVERSION: RepairActionKind.INVERT_POLARITY,
    RepairDefect.START_END_MISMATCH: RepairActionKind.REDUCE_START_END_MISMATCH,
    RepairDefect.AMPLITUDE_INCONSISTENCY: RepairActionKind.MATCH_REFERENCE_AMPLITUDE,
    RepairDefect.CYCLE_LENGTH: RepairActionKind.RESAMPLE_CYCLE_LENGTH,
    RepairDefect.PITCH_ESTIMATE: RepairActionKind.UPDATE_PITCH_ESTIMATE,
    RepairDefect.PARASITIC_NOISE: RepairActionKind.REDUCE_PARASITIC_NOISE,
    RepairDefect.FUNDAMENTAL_LOSS: RepairActionKind.RESTORE_FUNDAMENTAL,
    RepairDefect.SPECTRAL_JUMP: RepairActionKind.SMOOTH_SPECTRAL_TRANSITION,
    RepairDefect.INTER_WAVE_LEVEL_MISMATCH: RepairActionKind.MATCH_INTER_WAVE_LEVEL,
    RepairDefect.REDUNDANT_WAVE: RepairActionKind.INTERPOLATE_REDUNDANT_WAVE,
    RepairDefect.EXCESSIVE_ALIASING: RepairActionKind.REDUCE_ALIASING,
}


def _validate(samples: Sequence[float], *, name: str = "samples") -> FloatArray:
    result = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if result.ndim != 1 or result.size < 2:
        raise AnalysisError(f"{name} must contain at least two samples")
    if not np.all(np.isfinite(result)):
        raise AnalysisError(f"{name} contains NaN or infinite values")
    if float(np.max(np.abs(result))) > 1.0 + _EPSILON:
        raise AnalysisError(f"{name} exceeds normalized range [-1, 1]")
    return result


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _rms(samples: FloatArray) -> float:
    return float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))


def _magnitude(samples: FloatArray) -> FloatArray:
    return np.asarray(np.abs(np.fft.rfft(samples))[1:], dtype=np.float64)


def _power(samples: FloatArray) -> FloatArray:
    return np.square(_magnitude(samples))


def _normalized_spectrum(samples: FloatArray) -> FloatArray:
    magnitude = _magnitude(samples)
    norm = float(np.linalg.norm(magnitude))
    if norm <= _EPSILON:
        return np.zeros_like(magnitude)
    return magnitude / norm


def _correlation(left: FloatArray, right: FloatArray) -> float:
    if left.shape != right.shape:
        raise AnalysisError("correlation inputs must have the same shape")
    a = left - float(np.mean(left, dtype=np.float64))
    b = right - float(np.mean(right, dtype=np.float64))
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= _EPSILON:
        return 1.0 if np.allclose(left, right, atol=1.0e-12, rtol=0.0) else 0.0
    return float(np.clip(np.dot(a, b) / denominator, -1.0, 1.0))


def _best_phase(reference: FloatArray, candidate: FloatArray) -> tuple[int, float]:
    correlations = tuple(
        _correlation(reference, np.roll(candidate, shift))
        for shift in range(candidate.size)
    )
    best_value = max(correlations)
    best_indexes = tuple(
        index
        for index, value in enumerate(correlations)
        if math.isclose(value, best_value, abs_tol=1.0e-15, rel_tol=0.0)
    )
    best = min(
        best_indexes,
        key=lambda value: (min(value, candidate.size - value), value),
    )
    signed = best if best <= candidate.size // 2 else best - candidate.size
    return int(signed), float(best_value)


def _spectral_distance(left: FloatArray, right: FloatArray) -> float:
    a = _normalized_spectrum(left)
    b = _normalized_spectrum(right)
    if a.shape != b.shape:
        raise AnalysisError("spectral comparison inputs must have the same shape")
    return _clip01(float(np.sqrt(np.mean(np.square(a - b), dtype=np.float64))))


def _db_delta(left: float, right: float) -> float:
    if left <= _EPSILON and right <= _EPSILON:
        return 0.0
    return float(abs(20.0 * math.log10(max(left, _EPSILON) / max(right, _EPSILON))))


def _severity(score: float, threshold: float, detected: bool) -> RepairSeverity:
    if not detected:
        return RepairSeverity.INFO
    denominator = max(threshold, 0.025)
    ratio = score / denominator
    if ratio >= 5.0:
        return RepairSeverity.BLOCKING
    if ratio >= 2.5:
        return RepairSeverity.HIGH
    return RepairSeverity.WARNING


def _finding(
    defect: RepairDefect,
    *,
    evaluated: bool,
    score: float,
    threshold: float,
    metrics: tuple[tuple[str, float], ...],
    auto_safe: bool,
    evidence: tuple[str, ...],
    unavailable_reason: str | None = None,
) -> RepairFinding:
    bounded_score = _clip01(score)
    bounded_threshold = _clip01(threshold)
    detected = bool(evaluated and bounded_score >= bounded_threshold)
    if unavailable_reason is not None:
        reason = unavailable_reason
    elif detected:
        reason = (
            f"{defect.value} exceeded its deterministic threshold "
            f"({bounded_score:.6f} >= {bounded_threshold:.6f})."
        )
    else:
        reason = (
            f"{defect.value} remained below its deterministic threshold "
            f"({bounded_score:.6f} < {bounded_threshold:.6f})."
        )
    return RepairFinding(
        defect=defect,
        evaluated=evaluated,
        detected=detected,
        severity=_severity(bounded_score, bounded_threshold, detected),
        score=bounded_score,
        threshold=bounded_threshold,
        metrics=metrics,
        recommended_action=_ACTION_BY_DEFECT[defect],
        auto_safe=auto_safe,
        evidence=evidence,
        reason=reason,
    )


def measure_repair_wave(samples: Sequence[float]) -> RepairWaveMetrics:
    array = _validate(samples)
    peak = float(np.max(np.abs(array)))
    scale = max(peak, _EPSILON)
    power = _power(array)
    total_power = float(np.sum(power, dtype=np.float64))
    fundamental = 0.0 if total_power <= _EPSILON else float(power[0] / total_power)
    high_start = max(1, int(math.ceil(power.size * 0.50)))
    high = (
        0.0
        if total_power <= _EPSILON
        else float(np.sum(power[high_start:], dtype=np.float64) / total_power)
    )
    positive = np.maximum(power, np.finfo(np.float64).tiny)
    arithmetic = float(np.mean(positive, dtype=np.float64))
    geometric = float(np.exp(np.mean(np.log(positive), dtype=np.float64)))
    flatness = 0.0 if arithmetic <= _EPSILON else _clip01(geometric / arithmetic)
    seam_value = _clip01(abs(float(array[0] - array[-1])) / (2.0 * scale))
    first_slope = float(array[1] - array[0])
    seam_slope = float(array[0] - array[-1])
    slope_error = _clip01(abs(first_slope - seam_slope) / (2.0 * scale))
    return RepairWaveMetrics(
        sample_count=int(array.size),
        sample_sha256=_sample_hash(array),
        mean=float(np.mean(array, dtype=np.float64)),
        rms=_rms(array),
        peak=peak,
        clipping_ratio=_clip01(float(np.mean(np.abs(array) >= 0.999))),
        nearest_zero_ratio=_clip01(float(np.min(np.abs(array))) / scale),
        seam_value_ratio=seam_value,
        seam_slope_ratio=slope_error,
        fundamental_ratio=_clip01(fundamental),
        high_band_ratio=_clip01(high),
        spectral_flatness=flatness,
    )


def detect_wave_defects(
    samples: Sequence[float],
    *,
    context: RepairContext | None = None,
    thresholds: RepairThresholds | None = None,
) -> tuple[RepairFinding, ...]:
    array = _validate(samples)
    selected_context = RepairContext() if context is None else context
    selected_thresholds = RepairThresholds() if thresholds is None else thresholds
    metrics = measure_repair_wave(array)
    peak = max(metrics.peak, _EPSILON)
    rms = max(metrics.rms, _EPSILON)

    findings: dict[RepairDefect, RepairFinding] = {}

    dc_score = _clip01(abs(metrics.mean) / rms)
    findings[RepairDefect.DC_OFFSET] = _finding(
        RepairDefect.DC_OFFSET,
        evaluated=True,
        score=dc_score,
        threshold=selected_thresholds.dc_ratio,
        metrics=(("dc_ratio", dc_score), ("mean", metrics.mean)),
        auto_safe=True,
        evidence=(f"mean={metrics.mean:.12g}", f"rms={metrics.rms:.12g}"),
    )

    findings[RepairDefect.CLIPPING] = _finding(
        RepairDefect.CLIPPING,
        evaluated=True,
        score=metrics.clipping_ratio,
        threshold=selected_thresholds.clipping_ratio,
        metrics=(("clipping_ratio", metrics.clipping_ratio), ("peak", metrics.peak)),
        auto_safe=True,
        evidence=(
            f"clipping_ratio={metrics.clipping_ratio:.12g}",
            f"peak={metrics.peak:.12g}",
        ),
    )

    findings[RepairDefect.ZERO_CROSSING] = _finding(
        RepairDefect.ZERO_CROSSING,
        evaluated=True,
        score=metrics.nearest_zero_ratio,
        threshold=selected_thresholds.zero_crossing_score,
        metrics=(("nearest_zero_ratio", metrics.nearest_zero_ratio),),
        auto_safe=True,
        evidence=(f"nearest_zero_ratio={metrics.nearest_zero_ratio:.12g}",),
    )

    findings[RepairDefect.LOOP_DISCONTINUITY] = _finding(
        RepairDefect.LOOP_DISCONTINUITY,
        evaluated=True,
        score=metrics.seam_value_ratio,
        threshold=selected_thresholds.seam_value_score,
        metrics=(("seam_value_ratio", metrics.seam_value_ratio),),
        auto_safe=True,
        evidence=(f"seam_value_ratio={metrics.seam_value_ratio:.12g}",),
    )

    findings[RepairDefect.DERIVATIVE_DISCONTINUITY] = _finding(
        RepairDefect.DERIVATIVE_DISCONTINUITY,
        evaluated=True,
        score=metrics.seam_slope_ratio,
        threshold=selected_thresholds.seam_slope_score,
        metrics=(("seam_slope_ratio", metrics.seam_slope_ratio),),
        auto_safe=True,
        evidence=(f"seam_slope_ratio={metrics.seam_slope_ratio:.12g}",),
    )

    reference_values = (
        selected_context.previous_samples
        if selected_context.previous_samples is not None
        else selected_context.reference_samples
    )
    reference = None
    if reference_values is not None and len(reference_values) == array.size:
        reference = _validate(reference_values, name="reference samples")

    if reference is None:
        findings[RepairDefect.PHASE_INVERSION] = _finding(
            RepairDefect.PHASE_INVERSION,
            evaluated=False,
            score=0.0,
            threshold=selected_thresholds.phase_shift_ratio,
            metrics=(("phase_shift_ratio", 0.0),),
            auto_safe=False,
            evidence=("reference_unavailable",),
            unavailable_reason="phase inversion requires a same-length reference wave.",
        )
        findings[RepairDefect.POLARITY_INVERSION] = _finding(
            RepairDefect.POLARITY_INVERSION,
            evaluated=False,
            score=0.0,
            threshold=_clip01(abs(selected_thresholds.polarity_correlation)),
            metrics=(("negative_correlation", 0.0),),
            auto_safe=False,
            evidence=("reference_unavailable",),
            unavailable_reason="polarity inversion requires a same-length reference wave.",
        )
    else:
        phase_shift, phase_correlation = _best_phase(reference, array)
        phase_score = _clip01(abs(phase_shift) / max(1.0, array.size / 2.0))
        raw_correlation = _correlation(reference, array)
        polarity_score = _clip01(max(0.0, -raw_correlation))
        findings[RepairDefect.PHASE_INVERSION] = _finding(
            RepairDefect.PHASE_INVERSION,
            evaluated=True,
            score=phase_score,
            threshold=selected_thresholds.phase_shift_ratio,
            metrics=(
                ("phase_shift_samples", float(phase_shift)),
                ("phase_shift_ratio", phase_score),
                ("aligned_correlation", phase_correlation),
            ),
            auto_safe=True,
            evidence=(
                f"phase_shift_samples={phase_shift}",
                f"aligned_correlation={phase_correlation:.12g}",
            ),
        )
        findings[RepairDefect.POLARITY_INVERSION] = _finding(
            RepairDefect.POLARITY_INVERSION,
            evaluated=True,
            score=polarity_score,
            threshold=_clip01(abs(selected_thresholds.polarity_correlation)),
            metrics=(("raw_correlation", raw_correlation), ("negative_correlation", polarity_score)),
            auto_safe=True,
            evidence=(f"raw_correlation={raw_correlation:.12g}",),
        )

    window = min(8, max(1, array.size // 8))
    start_rms = _rms(array[:window])
    end_rms = _rms(array[-window:])
    start_end_score = _clip01(abs(start_rms - end_rms) / max(start_rms, end_rms, _EPSILON))
    findings[RepairDefect.START_END_MISMATCH] = _finding(
        RepairDefect.START_END_MISMATCH,
        evaluated=True,
        score=start_end_score,
        threshold=selected_thresholds.start_end_score,
        metrics=(
            ("start_rms", start_rms),
            ("end_rms", end_rms),
            ("start_end_score", start_end_score),
        ),
        auto_safe=True,
        evidence=(
            f"start_rms={start_rms:.12g}",
            f"end_rms={end_rms:.12g}",
        ),
    )

    target_rms = selected_context.target_rms
    if target_rms is None and reference is not None:
        target_rms = _rms(reference)
    if target_rms is None:
        findings[RepairDefect.AMPLITUDE_INCONSISTENCY] = _finding(
            RepairDefect.AMPLITUDE_INCONSISTENCY,
            evaluated=False,
            score=0.0,
            threshold=_clip01(selected_thresholds.amplitude_delta_db / 12.0),
            metrics=(("amplitude_delta_db", 0.0),),
            auto_safe=False,
            evidence=("target_rms_unavailable",),
            unavailable_reason="amplitude consistency requires target RMS or a reference wave.",
        )
    else:
        amplitude_db = _db_delta(metrics.rms, target_rms)
        amplitude_score = _clip01(amplitude_db / 12.0)
        findings[RepairDefect.AMPLITUDE_INCONSISTENCY] = _finding(
            RepairDefect.AMPLITUDE_INCONSISTENCY,
            evaluated=True,
            score=amplitude_score,
            threshold=_clip01(selected_thresholds.amplitude_delta_db / 12.0),
            metrics=(("amplitude_delta_db", amplitude_db), ("target_rms", target_rms)),
            auto_safe=True,
            evidence=(
                f"amplitude_delta_db={amplitude_db:.12g}",
                f"target_rms={target_rms:.12g}",
            ),
        )

    length_delta = abs(array.size - selected_context.expected_sample_count)
    length_score = _clip01(length_delta / selected_context.expected_sample_count)
    findings[RepairDefect.CYCLE_LENGTH] = _finding(
        RepairDefect.CYCLE_LENGTH,
        evaluated=True,
        score=length_score,
        threshold=0.0 if length_delta else 1.0,
        metrics=(
            ("sample_count", float(array.size)),
            ("expected_sample_count", float(selected_context.expected_sample_count)),
        ),
        auto_safe=True,
        evidence=(
            f"sample_count={array.size}",
            f"expected_sample_count={selected_context.expected_sample_count}",
        ),
    )

    if (
        selected_context.detected_pitch_hz is None
        or selected_context.expected_pitch_hz is None
    ):
        findings[RepairDefect.PITCH_ESTIMATE] = _finding(
            RepairDefect.PITCH_ESTIMATE,
            evaluated=False,
            score=0.0,
            threshold=_clip01(selected_thresholds.pitch_error_cents / 600.0),
            metrics=(("pitch_error_cents", 0.0),),
            auto_safe=False,
            evidence=("pitch_pair_unavailable",),
            unavailable_reason="pitch repair requires detected and expected pitch values.",
        )
    else:
        cents = abs(
            1200.0
            * math.log2(
                selected_context.detected_pitch_hz
                / selected_context.expected_pitch_hz
            )
        )
        pitch_score = _clip01(cents / 600.0)
        findings[RepairDefect.PITCH_ESTIMATE] = _finding(
            RepairDefect.PITCH_ESTIMATE,
            evaluated=True,
            score=pitch_score,
            threshold=_clip01(selected_thresholds.pitch_error_cents / 600.0),
            metrics=(("pitch_error_cents", cents),),
            auto_safe=True,
            evidence=(
                f"detected_pitch_hz={selected_context.detected_pitch_hz:.12g}",
                f"expected_pitch_hz={selected_context.expected_pitch_hz:.12g}",
            ),
        )

    noise_score = _clip01(
        0.60 * metrics.spectral_flatness + 0.40 * metrics.high_band_ratio
    )
    findings[RepairDefect.PARASITIC_NOISE] = _finding(
        RepairDefect.PARASITIC_NOISE,
        evaluated=True,
        score=noise_score,
        threshold=selected_thresholds.parasitic_noise_ratio,
        metrics=(
            ("spectral_flatness", metrics.spectral_flatness),
            ("high_band_ratio", metrics.high_band_ratio),
            ("noise_score", noise_score),
        ),
        auto_safe=True,
        evidence=(
            f"spectral_flatness={metrics.spectral_flatness:.12g}",
            f"high_band_ratio={metrics.high_band_ratio:.12g}",
        ),
    )

    fundamental_loss_score = _clip01(
        max(0.0, selected_thresholds.fundamental_ratio - metrics.fundamental_ratio)
        / max(selected_thresholds.fundamental_ratio, _EPSILON)
    )
    findings[RepairDefect.FUNDAMENTAL_LOSS] = _finding(
        RepairDefect.FUNDAMENTAL_LOSS,
        evaluated=selected_context.tonal_expected,
        score=fundamental_loss_score,
        threshold=0.01,
        metrics=(("fundamental_ratio", metrics.fundamental_ratio),),
        auto_safe=selected_context.tonal_expected,
        evidence=(
            f"fundamental_ratio={metrics.fundamental_ratio:.12g}",
            f"tonal_expected={selected_context.tonal_expected}",
        ),
        unavailable_reason=(
            None
            if selected_context.tonal_expected
            else "fundamental-loss detection is disabled for intentionally non-tonal material."
        ),
    )

    if reference is None:
        for defect, unavailable_reason in (
            (
                RepairDefect.SPECTRAL_JUMP,
                "spectral-jump detection requires a previous or reference wave.",
            ),
            (
                RepairDefect.INTER_WAVE_LEVEL_MISMATCH,
                "inter-wave level detection requires a previous or reference wave.",
            ),
            (
                RepairDefect.REDUNDANT_WAVE,
                "redundancy detection requires a previous or reference wave.",
            ),
        ):
            findings[defect] = _finding(
                defect,
                evaluated=False,
                score=0.0,
                threshold=(
                    selected_thresholds.spectral_jump
                    if defect is RepairDefect.SPECTRAL_JUMP
                    else _clip01(selected_thresholds.inter_wave_level_db / 12.0)
                    if defect is RepairDefect.INTER_WAVE_LEVEL_MISMATCH
                    else selected_thresholds.redundancy_correlation
                ),
                metrics=(("reference_metric", 0.0),),
                auto_safe=False,
                evidence=("reference_unavailable",),
                unavailable_reason=unavailable_reason,
            )
    else:
        spectral_distance = _spectral_distance(reference, array)
        level_db = _db_delta(_rms(reference), metrics.rms)
        level_score = _clip01(level_db / 12.0)
        correlation = _correlation(reference, array)
        redundancy_score = _clip01(
            0.70 * max(0.0, correlation)
            + 0.30 * (1.0 - spectral_distance)
        )
        redundancy_threshold = _clip01(
            0.70 * selected_thresholds.redundancy_correlation
            + 0.30 * (1.0 - selected_thresholds.redundancy_spectral_distance)
        )
        findings[RepairDefect.SPECTRAL_JUMP] = _finding(
            RepairDefect.SPECTRAL_JUMP,
            evaluated=True,
            score=spectral_distance,
            threshold=selected_thresholds.spectral_jump,
            metrics=(("spectral_distance", spectral_distance),),
            auto_safe=True,
            evidence=(f"spectral_distance={spectral_distance:.12g}",),
        )
        findings[RepairDefect.INTER_WAVE_LEVEL_MISMATCH] = _finding(
            RepairDefect.INTER_WAVE_LEVEL_MISMATCH,
            evaluated=True,
            score=level_score,
            threshold=_clip01(selected_thresholds.inter_wave_level_db / 12.0),
            metrics=(("inter_wave_level_db", level_db),),
            auto_safe=True,
            evidence=(f"inter_wave_level_db={level_db:.12g}",),
        )
        findings[RepairDefect.REDUNDANT_WAVE] = _finding(
            RepairDefect.REDUNDANT_WAVE,
            evaluated=True,
            score=redundancy_score,
            threshold=redundancy_threshold,
            metrics=(
                ("correlation", correlation),
                ("spectral_distance", spectral_distance),
                ("redundancy_score", redundancy_score),
            ),
            auto_safe=selected_context.next_samples is not None,
            evidence=(
                f"correlation={correlation:.12g}",
                f"spectral_distance={spectral_distance:.12g}",
            ),
        )

    if selected_context.aliasing_risk is not None:
        aliasing_score = selected_context.aliasing_risk
        aliasing_evidence = "context_aliasing_risk"
    else:
        spectrum_power = _power(array)
        total = float(np.sum(spectrum_power, dtype=np.float64))
        safe_limit = selected_context.safe_harmonic_limit
        if safe_limit is None:
            safe_limit = max(4, spectrum_power.size // 3)
        safe_limit = min(max(1, safe_limit), spectrum_power.size)
        aliasing_score = (
            0.0
            if total <= _EPSILON
            else _clip01(
                float(np.sum(spectrum_power[safe_limit:], dtype=np.float64) / total)
            )
        )
        aliasing_evidence = f"derived_safe_harmonic_limit={safe_limit}"
    findings[RepairDefect.EXCESSIVE_ALIASING] = _finding(
        RepairDefect.EXCESSIVE_ALIASING,
        evaluated=True,
        score=aliasing_score,
        threshold=selected_thresholds.aliasing_risk,
        metrics=(("aliasing_risk", aliasing_score),),
        auto_safe=True,
        evidence=(
            f"aliasing_risk={aliasing_score:.12g}",
            aliasing_evidence,
        ),
    )

    return tuple(findings[defect] for defect in RepairDefect)


__all__ = ["detect_wave_defects", "measure_repair_wave"]
