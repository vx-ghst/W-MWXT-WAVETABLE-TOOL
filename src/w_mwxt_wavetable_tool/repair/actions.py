from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
import numpy.typing as npt

from ..errors import AnalysisError
from ..xt.resampling import (
    NormalizationPolicy,
    ResamplingAlgorithm,
    resample_periodic_wave,
)
from .models import (
    RepairActionKind,
    RepairContext,
    RepairFinding,
    _sample_hash,
)


_EPSILON = 1.0e-12
FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class RepairApplication:
    samples: tuple[float, ...]
    corrected_pitch_hz: float | None
    parameters: tuple[tuple[str, float | int | str | bool | None], ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        array = np.asarray(self.samples, dtype=np.float64)
        if array.ndim != 1 or array.size < 2:
            raise AnalysisError("repair application requires at least two samples")
        if not np.all(np.isfinite(array)):
            raise AnalysisError("repair application samples must be finite")
        if float(np.max(np.abs(array))) > 1.0 + _EPSILON:
            raise AnalysisError("repair application samples exceed normalized range")
        if self.corrected_pitch_hz is not None:
            if not math.isfinite(self.corrected_pitch_hz) or self.corrected_pitch_hz <= 0.0:
                raise AnalysisError("corrected_pitch_hz must be positive and finite")
        names = tuple(name for name, _ in self.parameters)
        if len(set(names)) != len(names):
            raise AnalysisError("repair application parameters must be unique")
        if any(not name or name.strip() != name for name in names):
            raise AnalysisError("repair application parameter names must be normalized")
        if any(not item or item.strip() != item for item in self.warnings):
            raise AnalysisError("repair application warnings must be normalized")
        if not self.reason or self.reason.strip() != self.reason:
            raise AnalysisError("repair application reason must be normalized")

    @property
    def samples_sha256(self) -> str:
        return _sample_hash(self.samples)


def _validate(samples: Sequence[float]) -> FloatArray:
    result = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if result.ndim != 1 or result.size < 2:
        raise AnalysisError("repair action input must contain at least two samples")
    if not np.all(np.isfinite(result)):
        raise AnalysisError("repair action input contains NaN or infinite values")
    if float(np.max(np.abs(result))) > 1.0 + _EPSILON:
        raise AnalysisError("repair action input exceeds normalized range [-1, 1]")
    return result


def _safe_output(samples: FloatArray) -> tuple[FloatArray, float, tuple[str, ...]]:
    peak = float(np.max(np.abs(samples)))
    if peak <= 1.0 + _EPSILON:
        return np.asarray(samples, dtype=np.float64), 1.0, ()
    scale = float(1.0 / peak)
    return (
        np.asarray(samples * scale, dtype=np.float64),
        scale,
        (f"safety_scale={scale:.12g}",),
    )


def _rms(samples: FloatArray) -> float:
    return float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))


def _correlation(left: FloatArray, right: FloatArray) -> float:
    if left.shape != right.shape:
        raise AnalysisError("repair correlation inputs must have equal length")
    a = left - float(np.mean(left, dtype=np.float64))
    b = right - float(np.mean(right, dtype=np.float64))
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= _EPSILON:
        return 1.0 if np.allclose(left, right, atol=1.0e-12, rtol=0.0) else 0.0
    return float(np.clip(np.dot(a, b) / denominator, -1.0, 1.0))


def _align_to_reference(reference: FloatArray, candidate: FloatArray) -> tuple[FloatArray, int, float]:
    correlations = tuple(
        _correlation(reference, np.roll(candidate, shift))
        for shift in range(candidate.size)
    )
    best_value = max(correlations)
    candidates = tuple(
        index
        for index, value in enumerate(correlations)
        if math.isclose(value, best_value, abs_tol=1.0e-15, rel_tol=0.0)
    )
    best = min(
        candidates,
        key=lambda value: (min(value, candidate.size - value), value),
    )
    signed = best if best <= candidate.size // 2 else best - candidate.size
    return np.roll(candidate, best), int(signed), float(best_value)


def _reference(context: RepairContext, length: int) -> FloatArray | None:
    values = context.previous_samples
    if values is None:
        values = context.reference_samples
    if values is None or len(values) != length:
        return None
    return _validate(values)


def _remove_dc(samples: FloatArray) -> tuple[FloatArray, dict[str, float], tuple[str, ...]]:
    mean = float(np.mean(samples, dtype=np.float64))
    output, scale, warnings = _safe_output(samples - mean)
    return output, {"removed_mean": mean, "safety_scale": scale}, warnings


def _reconstruct_clipped(samples: FloatArray) -> tuple[FloatArray, dict[str, float | int], tuple[str, ...]]:
    clipped = np.abs(samples) >= 0.999
    count = int(np.sum(clipped))
    if count == 0:
        return samples.copy(), {"reconstructed_sample_count": 0, "safety_scale": 1.0}, ()
    valid = np.flatnonzero(~clipped)
    output = samples.copy()
    if valid.size < 2:
        output *= 0.95
        warnings = ("insufficient_unclipped_neighbors_used_global_scale",)
    else:
        clipped_indexes = np.flatnonzero(clipped)
        n = samples.size
        xp = np.concatenate((valid - n, valid, valid + n)).astype(np.float64)
        fp = np.concatenate((samples[valid], samples[valid], samples[valid]))
        output[clipped_indexes] = np.interp(clipped_indexes, xp, fp)
        warnings = ()
    output, scale, safety = _safe_output(output)
    return (
        output,
        {"reconstructed_sample_count": count, "safety_scale": scale},
        warnings + safety,
    )


def _rotate_zero(samples: FloatArray) -> tuple[FloatArray, dict[str, int | float], tuple[str, ...]]:
    peak = max(float(np.max(np.abs(samples))), _EPSILON)
    previous = np.roll(samples, 1)
    following = np.roll(samples, -1)
    slope = np.abs(following - previous) / (2.0 * peak)
    cost = np.abs(samples) / peak + 0.25 * slope
    minimum = float(np.min(cost))
    indexes = np.flatnonzero(np.isclose(cost, minimum, atol=1.0e-15, rtol=0.0))
    index = int(indexes[0])
    return (
        np.roll(samples, -index),
        {"rotation_samples": index, "zero_cost": minimum},
        (),
    )


def _smooth_loop(samples: FloatArray) -> tuple[FloatArray, dict[str, float | int], tuple[str, ...]]:
    output = samples.copy()
    width = min(8, max(1, samples.size // 8))
    midpoint = 0.5 * float(samples[0] + samples[-1])
    for offset in range(width):
        weight = ((width - offset) / width) ** 2
        output[offset] += (midpoint - samples[0]) * weight
        output[-1 - offset] += (midpoint - samples[-1]) * weight
    output, scale, warnings = _safe_output(output)
    return output, {"crossfade_width": width, "safety_scale": scale}, warnings


def _smooth_derivative(samples: FloatArray) -> tuple[FloatArray, dict[str, float], tuple[str, ...]]:
    output = samples.copy()
    incoming = float(samples[0] - samples[-1])
    outgoing = float(samples[1] - samples[0])
    target = 0.5 * (incoming + outgoing)
    output[1] = output[0] + target
    output[-1] = output[0] - target
    if output.size >= 4:
        output[2] = 0.5 * (output[2] + output[1] + target)
        output[-2] = 0.5 * (output[-2] + output[-1] - target)
    output, scale, warnings = _safe_output(output)
    return (
        output,
        {
            "incoming_slope": incoming,
            "outgoing_slope": outgoing,
            "target_slope": target,
            "safety_scale": scale,
        },
        warnings,
    )


def _align_phase(samples: FloatArray, context: RepairContext) -> tuple[FloatArray, dict[str, int | float], tuple[str, ...]]:
    reference = _reference(context, samples.size)
    if reference is None:
        raise AnalysisError("phase alignment requires a same-length reference wave")
    output, shift, correlation = _align_to_reference(reference, samples)
    return output, {"phase_shift_samples": shift, "aligned_correlation": correlation}, ()


def _invert_polarity(samples: FloatArray, context: RepairContext) -> tuple[FloatArray, dict[str, float], tuple[str, ...]]:
    reference = _reference(context, samples.size)
    correlation = 0.0 if reference is None else _correlation(reference, samples)
    return -samples, {"reference_correlation_before": correlation}, ()


def _reduce_start_end(samples: FloatArray) -> tuple[FloatArray, dict[str, float | int], tuple[str, ...]]:
    output = samples.copy()
    width = min(8, max(1, samples.size // 8))
    start_rms = _rms(samples[:width])
    end_rms = _rms(samples[-width:])
    target = 0.5 * (start_rms + end_rms)
    start_gain = target / max(start_rms, _EPSILON)
    end_gain = target / max(end_rms, _EPSILON)
    for offset in range(width):
        weight = (width - offset) / width
        output[offset] *= 1.0 + (start_gain - 1.0) * weight
        output[-1 - offset] *= 1.0 + (end_gain - 1.0) * weight
    output, scale, warnings = _safe_output(output)
    return (
        output,
        {
            "window": width,
            "start_rms": start_rms,
            "end_rms": end_rms,
            "target_rms": target,
            "start_gain": start_gain,
            "end_gain": end_gain,
            "safety_scale": scale,
        },
        warnings,
    )


def _match_amplitude(samples: FloatArray, context: RepairContext) -> tuple[FloatArray, dict[str, float], tuple[str, ...]]:
    reference = _reference(context, samples.size)
    target = context.target_rms
    if target is None and reference is not None:
        target = _rms(reference)
    if target is None:
        raise AnalysisError("amplitude matching requires target_rms or a reference wave")
    source_rms = _rms(samples)
    gain = float(target / max(source_rms, _EPSILON))
    output, scale, warnings = _safe_output(samples * gain)
    return (
        output,
        {
            "source_rms": source_rms,
            "target_rms": float(target),
            "requested_gain": gain,
            "safety_scale": scale,
        },
        warnings,
    )


def _resample_length(samples: FloatArray, context: RepairContext) -> tuple[FloatArray, dict[str, int | str | float], tuple[str, ...]]:
    result = resample_periodic_wave(
        samples,
        context.expected_sample_count,
        algorithm=ResamplingAlgorithm.WINDOWED_SINC,
        normalization=NormalizationPolicy.NONE,
    )
    output = np.asarray(result.samples, dtype=np.float64)
    return (
        output,
        {
            "source_count": int(samples.size),
            "target_count": context.expected_sample_count,
            "algorithm": result.algorithm.value,
            "safety_scale": result.metrics.applied_scale,
        },
        result.warnings,
    )


def _reduce_noise(samples: FloatArray) -> tuple[FloatArray, dict[str, float | int], tuple[str, ...]]:
    spectrum = np.fft.rfft(samples)
    magnitude = np.abs(spectrum)
    maximum = float(np.max(magnitude[1:])) if magnitude.size > 1 else 0.0
    threshold = 0.035 * maximum
    keep = np.ones(magnitude.size, dtype=bool)
    if magnitude.size > 4:
        keep[4:] = magnitude[4:] >= threshold
    removed = int(np.sum(~keep))
    filtered = spectrum.copy()
    filtered[~keep] = 0.0
    output = np.fft.irfft(filtered, n=samples.size)
    output, scale, warnings = _safe_output(np.asarray(output, dtype=np.float64))
    return (
        output,
        {
            "spectral_gate_threshold": threshold,
            "removed_bin_count": removed,
            "safety_scale": scale,
        },
        warnings,
    )


def _restore_fundamental(samples: FloatArray) -> tuple[FloatArray, dict[str, float], tuple[str, ...]]:
    spectrum = np.fft.rfft(samples)
    magnitude = np.abs(spectrum)
    if magnitude.size <= 1:
        return samples.copy(), {"fundamental_gain": 1.0, "safety_scale": 1.0}, ()
    comparison = magnitude[2 : min(6, magnitude.size)]
    target = max(float(magnitude[1]), 0.60 * float(np.max(comparison)) if comparison.size else 0.0)
    original = float(magnitude[1])
    phase = float(np.angle(spectrum[1])) if original > _EPSILON else 0.0
    spectrum[1] = target * np.exp(1j * phase)
    output = np.fft.irfft(spectrum, n=samples.size)
    output, scale, warnings = _safe_output(np.asarray(output, dtype=np.float64))
    gain = target / max(original, _EPSILON)
    return output, {"fundamental_gain": gain, "safety_scale": scale}, warnings


def _smooth_spectral(samples: FloatArray, context: RepairContext) -> tuple[FloatArray, dict[str, float | int], tuple[str, ...]]:
    reference = _reference(context, samples.size)
    if reference is None:
        raise AnalysisError("spectral transition repair requires a reference wave")
    aligned, shift, correlation = _align_to_reference(reference, samples)
    blend = 0.25
    output = (1.0 - blend) * aligned + blend * reference
    output, scale, warnings = _safe_output(output)
    return (
        output,
        {
            "reference_blend": blend,
            "phase_shift_samples": shift,
            "aligned_correlation": correlation,
            "safety_scale": scale,
        },
        warnings,
    )


def _interpolate_redundant(samples: FloatArray, context: RepairContext) -> tuple[FloatArray, dict[str, float | int], tuple[str, ...]]:
    previous_values = context.previous_samples or context.reference_samples
    next_values = context.next_samples
    if previous_values is None or next_values is None:
        raise AnalysisError("redundant-wave interpolation requires previous and next waves")
    previous = _validate(previous_values)
    following = _validate(next_values)
    if previous.shape != samples.shape or following.shape != samples.shape:
        raise AnalysisError("redundant-wave neighbors must match the wave length")
    aligned_previous, previous_shift, _ = _align_to_reference(samples, previous)
    aligned_following, next_shift, _ = _align_to_reference(samples, following)
    output = 0.5 * (aligned_previous + aligned_following)
    output, scale, warnings = _safe_output(output)
    return (
        output,
        {
            "previous_phase_shift": previous_shift,
            "next_phase_shift": next_shift,
            "safety_scale": scale,
        },
        warnings,
    )


def _reduce_aliasing(samples: FloatArray, context: RepairContext) -> tuple[FloatArray, dict[str, int | float], tuple[str, ...]]:
    spectrum = np.fft.rfft(samples)
    maximum_harmonic = spectrum.size - 1
    safe_limit = context.safe_harmonic_limit
    if safe_limit is None:
        safe_limit = max(4, maximum_harmonic // 3)
    safe_limit = min(max(1, int(safe_limit)), maximum_harmonic)
    taper_width = min(4, max(1, maximum_harmonic - safe_limit))
    filtered = spectrum.copy()
    for index in range(safe_limit + 1, spectrum.size):
        distance = index - safe_limit
        if distance <= taper_width:
            weight = 0.5 * (1.0 + math.cos(math.pi * distance / (taper_width + 1)))
        else:
            weight = 0.0
        filtered[index] *= weight
    output = np.fft.irfft(filtered, n=samples.size)
    output, scale, warnings = _safe_output(np.asarray(output, dtype=np.float64))
    return (
        output,
        {
            "safe_harmonic_limit": safe_limit,
            "taper_width": taper_width,
            "safety_scale": scale,
        },
        warnings,
    )


def apply_repair_action(
    samples: Sequence[float],
    finding: RepairFinding,
    *,
    context: RepairContext | None = None,
) -> RepairApplication:
    array = _validate(samples)
    selected_context = RepairContext() if context is None else context
    action = finding.recommended_action
    corrected_pitch: float | None = None

    if action is RepairActionKind.REMOVE_DC:
        output, parameters, warnings = _remove_dc(array)
    elif action is RepairActionKind.RECONSTRUCT_CLIPPED_PEAKS:
        output, parameters, warnings = _reconstruct_clipped(array)
    elif action is RepairActionKind.ROTATE_TO_ZERO_CROSSING:
        output, parameters, warnings = _rotate_zero(array)
    elif action is RepairActionKind.SMOOTH_LOOP_SEAM:
        output, parameters, warnings = _smooth_loop(array)
    elif action is RepairActionKind.SMOOTH_SEAM_DERIVATIVE:
        output, parameters, warnings = _smooth_derivative(array)
    elif action is RepairActionKind.ALIGN_PHASE_TO_REFERENCE:
        output, parameters, warnings = _align_phase(array, selected_context)
    elif action is RepairActionKind.INVERT_POLARITY:
        output, parameters, warnings = _invert_polarity(array, selected_context)
    elif action is RepairActionKind.REDUCE_START_END_MISMATCH:
        output, parameters, warnings = _reduce_start_end(array)
    elif action is RepairActionKind.MATCH_REFERENCE_AMPLITUDE:
        output, parameters, warnings = _match_amplitude(array, selected_context)
    elif action is RepairActionKind.RESAMPLE_CYCLE_LENGTH:
        output, parameters, warnings = _resample_length(array, selected_context)
    elif action is RepairActionKind.UPDATE_PITCH_ESTIMATE:
        if selected_context.expected_pitch_hz is None:
            raise AnalysisError("pitch update requires expected_pitch_hz")
        output = array.copy()
        corrected_pitch = selected_context.expected_pitch_hz
        parameters = {
            "detected_pitch_hz": selected_context.detected_pitch_hz,
            "corrected_pitch_hz": corrected_pitch,
        }
        warnings = ()
    elif action is RepairActionKind.REDUCE_PARASITIC_NOISE:
        output, parameters, warnings = _reduce_noise(array)
    elif action is RepairActionKind.RESTORE_FUNDAMENTAL:
        output, parameters, warnings = _restore_fundamental(array)
    elif action is RepairActionKind.SMOOTH_SPECTRAL_TRANSITION:
        output, parameters, warnings = _smooth_spectral(array, selected_context)
    elif action is RepairActionKind.MATCH_INTER_WAVE_LEVEL:
        output, parameters, warnings = _match_amplitude(array, selected_context)
    elif action is RepairActionKind.INTERPOLATE_REDUNDANT_WAVE:
        output, parameters, warnings = _interpolate_redundant(array, selected_context)
    elif action is RepairActionKind.REDUCE_ALIASING:
        output, parameters, warnings = _reduce_aliasing(array, selected_context)
    else:  # pragma: no cover - exhaustive Enum gate
        raise AnalysisError(f"Unsupported repair action: {action.value}")

    output, final_scale, final_warnings = _safe_output(np.asarray(output, dtype=np.float64))
    if "safety_scale" not in parameters:
        parameters["safety_scale"] = final_scale
    elif final_scale != 1.0:
        parameters["final_safety_scale"] = final_scale
    rendered_parameters = tuple((name, value) for name, value in parameters.items())
    return RepairApplication(
        samples=tuple(float(value) for value in output),
        corrected_pitch_hz=corrected_pitch,
        parameters=rendered_parameters,
        warnings=tuple(warnings) + tuple(final_warnings),
        reason=f"Executed deterministic repair action {action.value}.",
    )


__all__ = ["RepairApplication", "apply_repair_action"]
