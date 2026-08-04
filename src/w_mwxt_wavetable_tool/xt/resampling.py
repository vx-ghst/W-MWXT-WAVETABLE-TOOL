from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any, Sequence

import numpy as np
import numpy.typing as npt

from ..errors import AnalysisError


FloatArray = npt.NDArray[np.float64]
_EPSILON = 1.0e-12


class ResamplingAlgorithm(str, Enum):
    WINDOWED_SINC = "windowed_sinc"
    FOURIER = "fourier"
    LINEAR = "linear"


class NormalizationPolicy(str, Enum):
    NONE = "none"
    PEAK_MATCH = "peak_match"
    RMS_MATCH = "rms_match"
    BASS_PROTECT = "bass_protect"


def _finite_ratio(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked) or not 0.0 <= checked <= 1.0:
        raise AnalysisError(f"{name} must be a finite ratio")
    return checked


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
    array = np.asarray(tuple(float(value) for value in samples), dtype="<f8")
    return sha256(array.tobytes(order="C")).hexdigest()


def _validate_samples(samples: Sequence[float], *, name: str = "samples") -> FloatArray:
    array = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if array.ndim != 1 or array.size < 2:
        raise AnalysisError(f"{name} must contain at least two samples")
    if not np.all(np.isfinite(array)):
        raise AnalysisError(f"{name} contains NaN or infinite values")
    if float(np.max(np.abs(array))) > 1.0 + _EPSILON:
        raise AnalysisError(f"{name} must stay in normalized range [-1, 1]")
    return array


def _rms(samples: FloatArray) -> float:
    return float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))


def _fundamental_amplitude(samples: FloatArray) -> float:
    if samples.size < 3:
        return 0.0
    spectrum = np.fft.rfft(samples)
    return float(2.0 * abs(spectrum[1]) / samples.size)


def _low_band_power_ratio(samples: FloatArray) -> float:
    spectrum = np.fft.rfft(samples)
    power = np.square(np.abs(spectrum[1:]))
    total = float(np.sum(power, dtype=np.float64))
    if total <= _EPSILON:
        return 0.0
    stop = min(4, power.size)
    return float(np.sum(power[:stop], dtype=np.float64) / total)


def _normalized_spectrum(samples: FloatArray, bins: int) -> FloatArray:
    magnitude = np.abs(np.fft.rfft(samples))[1 : bins + 1]
    if magnitude.size < bins:
        magnitude = np.pad(magnitude, (0, bins - magnitude.size))
    norm = float(np.linalg.norm(magnitude))
    if norm <= _EPSILON:
        return np.zeros(bins, dtype=np.float64)
    return np.asarray(magnitude / norm, dtype=np.float64)


def _circular_phase_metrics(reference: FloatArray, candidate: FloatArray) -> tuple[int, float]:
    if reference.shape != candidate.shape:
        raise AnalysisError("phase comparison requires equal lengths")
    left = reference - float(np.mean(reference, dtype=np.float64))
    right = candidate - float(np.mean(candidate, dtype=np.float64))
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= _EPSILON:
        return (0, 1.0 if np.allclose(reference, candidate, atol=1.0e-12, rtol=0.0) else 0.0)
    correlations = np.asarray(
        [float(np.dot(left, np.roll(right, shift)) / denominator) for shift in range(reference.size)],
        dtype=np.float64,
    )
    best_value = float(np.max(correlations))
    indexes = np.flatnonzero(np.isclose(correlations, best_value, atol=1.0e-15, rtol=0.0))
    best = min((int(index) for index in indexes), key=lambda value: (min(value, reference.size - value), value))
    signed = best if best <= reference.size // 2 else best - reference.size
    return signed, float(np.clip(best_value, -1.0, 1.0))


def _linear_resample(samples: FloatArray, target_count: int) -> FloatArray:
    positions = np.arange(target_count, dtype=np.float64) * (samples.size / target_count)
    left = np.floor(positions).astype(np.int64) % samples.size
    fraction = positions - np.floor(positions)
    right = (left + 1) % samples.size
    return np.asarray(samples[left] * (1.0 - fraction) + samples[right] * fraction, dtype=np.float64)


def _fourier_resample(samples: FloatArray, target_count: int) -> FloatArray:
    source_count = samples.size
    coefficients = np.fft.fft(samples) / source_count
    harmonics = np.rint(np.fft.fftfreq(source_count) * source_count).astype(np.int64)
    maximum = target_count // 2
    if target_count % 2 == 0:
        keep = np.abs(harmonics) < maximum
    else:
        keep = np.abs(harmonics) <= maximum
    selected_coefficients = coefficients[keep]
    selected_harmonics = harmonics[keep]
    phases = np.exp(
        2j
        * np.pi
        * np.outer(np.arange(target_count, dtype=np.float64) / target_count, selected_harmonics)
    )
    result = phases @ selected_coefficients
    if target_count % 2 == 0 and maximum > 0:
        nyquist_coefficients = coefficients[np.abs(harmonics) == maximum]
        if nyquist_coefficients.size:
            combined = complex(np.sum(nyquist_coefficients))
            result += combined * np.exp(2j * np.pi * maximum * np.arange(target_count) / target_count)
    return np.asarray(np.real_if_close(result, tol=1000).real, dtype=np.float64)


def _windowed_sinc_resample(samples: FloatArray, target_count: int) -> FloatArray:
    source_count = samples.size
    cutoff = min(1.0, target_count / source_count) * 0.95
    radius = max(4, min(16, source_count // 2))
    window = np.kaiser(2 * radius + 1, 8.6)
    output = np.empty(target_count, dtype=np.float64)
    for output_index in range(target_count):
        position = output_index * source_count / target_count
        center = math.floor(position)
        offsets = np.arange(-radius, radius + 1, dtype=np.int64)
        indexes = (center + offsets) % source_count
        delta = position - (center + offsets.astype(np.float64))
        weights = cutoff * np.sinc(cutoff * delta) * window
        weight_sum = float(np.sum(weights, dtype=np.float64))
        if abs(weight_sum) <= _EPSILON:
            raise AnalysisError("windowed-sinc kernel has zero normalization")
        output[output_index] = float(np.dot(samples[indexes], weights / weight_sum))
    return output


def _raw_resample(samples: FloatArray, target_count: int, algorithm: ResamplingAlgorithm) -> FloatArray:
    if algorithm is ResamplingAlgorithm.LINEAR:
        return _linear_resample(samples, target_count)
    if algorithm is ResamplingAlgorithm.FOURIER:
        return _fourier_resample(samples, target_count)
    if algorithm is ResamplingAlgorithm.WINDOWED_SINC:
        return _windowed_sinc_resample(samples, target_count)
    raise AnalysisError(f"Unsupported resampling algorithm: {algorithm}")


def _apply_normalization(
    source: FloatArray,
    output: FloatArray,
    policy: NormalizationPolicy,
) -> tuple[FloatArray, float, tuple[str, ...]]:
    scale = 1.0
    warnings: list[str] = []
    source_peak = float(np.max(np.abs(source)))
    output_peak = float(np.max(np.abs(output)))
    source_rms = _rms(source)
    output_rms = _rms(output)
    if policy is NormalizationPolicy.PEAK_MATCH and output_peak > _EPSILON:
        scale = source_peak / output_peak
    elif policy is NormalizationPolicy.RMS_MATCH and output_rms > _EPSILON:
        scale = source_rms / output_rms
    elif policy is NormalizationPolicy.BASS_PROTECT:
        source_fundamental = _fundamental_amplitude(source)
        output_fundamental = _fundamental_amplitude(output)
        if source_fundamental > _EPSILON and output_fundamental > _EPSILON:
            scale = source_fundamental / output_fundamental
        elif source_rms > _EPSILON and output_rms > _EPSILON:
            scale = source_rms / output_rms
            warnings.append("Fundamental was unavailable; Bass Protect fell back to RMS matching.")
    normalized = np.asarray(output * scale, dtype=np.float64)
    normalized_peak = float(np.max(np.abs(normalized)))
    if normalized_peak > 1.0 + _EPSILON:
        safety_scale = 1.0 / normalized_peak
        normalized *= safety_scale
        scale *= safety_scale
        warnings.append("Global safety scaling prevented normalized-range overflow without clipping.")
    return normalized, float(scale), tuple(warnings)


@dataclass(frozen=True, slots=True)
class ResamplingMetrics:
    source_count: int
    target_count: int
    source_rms: float
    target_rms: float
    source_peak: float
    target_peak: float
    applied_scale: float
    phase_shift_samples: int
    phase_correlation: float
    fundamental_amplitude_ratio: float
    low_band_power_ratio_before: float
    low_band_power_ratio_after: float
    low_band_loss: float
    spectral_rmse: float
    aliasing_risk: float
    ringing_score: float
    overshoot: float
    extreme_count: int
    quality_score: float

    def __post_init__(self) -> None:
        if self.source_count < 2 or self.target_count < 2:
            raise AnalysisError("resampling counts must be at least two")
        for name, value in self.to_dict().items():
            if name in {"source_count", "target_count", "phase_shift_samples", "extreme_count"}:
                continue
            if not math.isfinite(float(value)):
                raise AnalysisError(f"resampling metric {name} must be finite")
        for name in (
            "phase_correlation",
            "low_band_power_ratio_before",
            "low_band_power_ratio_after",
            "low_band_loss",
            "spectral_rmse",
            "aliasing_risk",
            "ringing_score",
            "overshoot",
            "quality_score",
        ):
            value = float(getattr(self, name))
            if name == "phase_correlation":
                if not -1.0 <= value <= 1.0:
                    raise AnalysisError("phase_correlation must be between -1 and 1")
            else:
                _finite_ratio(value, name=name)
        if self.extreme_count < 0:
            raise AnalysisError("extreme_count must not be negative")
        if self.source_rms < 0.0 or self.target_rms < 0.0 or self.source_peak < 0.0 or self.target_peak < 0.0:
            raise AnalysisError("level metrics must not be negative")
        if self.applied_scale <= 0.0 or self.fundamental_amplitude_ratio < 0.0:
            raise AnalysisError("scale and fundamental ratio must be positive or zero")

    def to_dict(self) -> dict[str, float | int]:
        return {
            "source_count": self.source_count,
            "target_count": self.target_count,
            "source_rms": self.source_rms,
            "target_rms": self.target_rms,
            "source_peak": self.source_peak,
            "target_peak": self.target_peak,
            "applied_scale": self.applied_scale,
            "phase_shift_samples": self.phase_shift_samples,
            "phase_correlation": self.phase_correlation,
            "fundamental_amplitude_ratio": self.fundamental_amplitude_ratio,
            "low_band_power_ratio_before": self.low_band_power_ratio_before,
            "low_band_power_ratio_after": self.low_band_power_ratio_after,
            "low_band_loss": self.low_band_loss,
            "spectral_rmse": self.spectral_rmse,
            "aliasing_risk": self.aliasing_risk,
            "ringing_score": self.ringing_score,
            "overshoot": self.overshoot,
            "extreme_count": self.extreme_count,
            "quality_score": self.quality_score,
        }


@dataclass(frozen=True, slots=True)
class ResampledWave:
    schema_version: int
    algorithm: ResamplingAlgorithm
    normalization: NormalizationPolicy
    anti_alias: bool
    source_samples_sha256: str
    samples: tuple[float, ...]
    metrics: ResamplingMetrics
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported resampled-wave schema version")
        if len(self.source_samples_sha256) != 64:
            raise AnalysisError("source_samples_sha256 must be a SHA-256 digest")
        if len(self.samples) != self.metrics.target_count:
            raise AnalysisError("resampled sample count is inconsistent")
        values = np.asarray(self.samples, dtype=np.float64)
        if np.any(~np.isfinite(values)) or float(np.max(np.abs(values))) > 1.0 + _EPSILON:
            raise AnalysisError("resampled samples must be finite and normalized")
        if any(not item or item.strip() != item for item in self.warnings):
            raise AnalysisError("warnings must contain normalized strings")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "algorithm": self.algorithm.value,
            "normalization": self.normalization.value,
            "anti_alias": self.anti_alias,
            "source_samples_sha256": self.source_samples_sha256,
            "samples": list(self.samples),
            "metrics": self.metrics.to_dict(),
            "warnings": list(self.warnings),
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class ResamplingComparison:
    schema_version: int
    source_samples_sha256: str
    target_count: int
    candidates: tuple[ResampledWave, ...]
    selected_algorithm: ResamplingAlgorithm
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported resampling-comparison schema version")
        if tuple(item.algorithm for item in self.candidates) != tuple(ResamplingAlgorithm):
            raise AnalysisError("candidates must contain every algorithm in canonical order")
        if any(item.source_samples_sha256 != self.source_samples_sha256 for item in self.candidates):
            raise AnalysisError("candidate source hashes are inconsistent")
        if any(item.metrics.target_count != self.target_count for item in self.candidates):
            raise AnalysisError("candidate target counts are inconsistent")
        selected = min(
            self.candidates,
            key=lambda item: (item.metrics.quality_score, list(ResamplingAlgorithm).index(item.algorithm)),
        )
        if selected.algorithm is not self.selected_algorithm:
            raise AnalysisError("selected_algorithm must match the lowest quality score")
        if not self.reason or self.reason.strip() != self.reason:
            raise AnalysisError("reason must be normalized")

    @property
    def selected(self) -> ResampledWave:
        return next(item for item in self.candidates if item.algorithm is self.selected_algorithm)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_samples_sha256": self.source_samples_sha256,
            "target_count": self.target_count,
            "candidates": [item.to_dict() for item in self.candidates],
            "selected_algorithm": self.selected_algorithm.value,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _measure(
    source: FloatArray,
    raw_output: FloatArray,
    output: FloatArray,
    *,
    target_count: int,
    applied_scale: float,
    algorithm: ResamplingAlgorithm,
) -> ResamplingMetrics:
    source_rms = _rms(source)
    target_rms = _rms(output)
    source_peak = float(np.max(np.abs(source)))
    target_peak = float(np.max(np.abs(output)))
    fundamental_before = _fundamental_amplitude(source)
    fundamental_after = _fundamental_amplitude(output)
    fundamental_ratio = (
        1.0 if fundamental_before <= _EPSILON and fundamental_after <= _EPSILON
        else fundamental_after / max(fundamental_before, _EPSILON)
    )
    low_before = _low_band_power_ratio(source)
    low_after = _low_band_power_ratio(output)
    low_loss = min(1.0, abs(low_after - low_before))

    common_bins = max(1, min(source.size, target_count) // 2)
    source_spectrum = _normalized_spectrum(source, common_bins)
    output_spectrum = _normalized_spectrum(output, common_bins)
    spectral_rmse = min(
        1.0,
        float(np.sqrt(np.mean(np.square(output_spectrum - source_spectrum), dtype=np.float64))),
    )

    reconstructed = _fourier_resample(output, source.size)
    ideal_lowpass = _fourier_resample(_fourier_resample(source, target_count), source.size)
    shift, phase_correlation = _circular_phase_metrics(ideal_lowpass, reconstructed)

    if target_count < source.size:
        lowpassed_source = _fourier_resample(_fourier_resample(source, target_count), source.size)
        alias_reference = _raw_resample(lowpassed_source, target_count, algorithm)
        alias_difference = raw_output - alias_reference
        aliasing_risk = min(1.0, _rms(alias_difference) / max(source_rms, _EPSILON))
    else:
        aliasing_risk = 0.0

    source_min = float(np.min(source))
    source_max = float(np.max(source))
    overshoot_amount = max(0.0, float(np.max(raw_output)) - source_max, source_min - float(np.min(raw_output)))
    source_span = max(source_max - source_min, _EPSILON)
    overshoot = min(1.0, overshoot_amount / source_span)
    source_variation = float(np.sum(np.abs(np.diff(np.r_[source, source[0]])), dtype=np.float64))
    output_variation = float(np.sum(np.abs(np.diff(np.r_[raw_output, raw_output[0]])), dtype=np.float64))
    variation_excess = max(0.0, output_variation / max(source_variation, _EPSILON) - 1.0)
    ringing_score = min(1.0, 0.65 * overshoot + 0.35 * min(1.0, variation_excess))
    extreme_count = int(np.count_nonzero(np.abs(raw_output) > 1.0 + _EPSILON))

    phase_error = min(1.0, abs(shift) / max(1.0, source.size / 2.0))
    fundamental_loss = min(1.0, abs(1.0 - fundamental_ratio))
    level_loss = min(1.0, abs(target_rms - source_rms) / max(source_rms, _EPSILON))
    quality = min(
        1.0,
        0.25 * spectral_rmse
        + 0.20 * aliasing_risk
        + 0.15 * phase_error
        + 0.15 * fundamental_loss
        + 0.10 * low_loss
        + 0.10 * ringing_score
        + 0.05 * level_loss,
    )
    return ResamplingMetrics(
        source_count=source.size,
        target_count=target_count,
        source_rms=source_rms,
        target_rms=target_rms,
        source_peak=source_peak,
        target_peak=target_peak,
        applied_scale=applied_scale,
        phase_shift_samples=shift,
        phase_correlation=phase_correlation,
        fundamental_amplitude_ratio=float(fundamental_ratio),
        low_band_power_ratio_before=low_before,
        low_band_power_ratio_after=low_after,
        low_band_loss=low_loss,
        spectral_rmse=spectral_rmse,
        aliasing_risk=aliasing_risk,
        ringing_score=ringing_score,
        overshoot=overshoot,
        extreme_count=extreme_count,
        quality_score=quality,
    )


def resample_periodic_wave(
    samples: Sequence[float],
    target_count: int,
    *,
    algorithm: ResamplingAlgorithm = ResamplingAlgorithm.WINDOWED_SINC,
    normalization: NormalizationPolicy = NormalizationPolicy.NONE,
) -> ResampledWave:
    source = _validate_samples(samples)
    if target_count < 2:
        raise AnalysisError("target_count must be at least two")
    selected_algorithm = ResamplingAlgorithm(algorithm)
    selected_normalization = NormalizationPolicy(normalization)
    raw = _raw_resample(source, int(target_count), selected_algorithm)
    output, scale, warnings = _apply_normalization(source, raw, selected_normalization)
    metrics = _measure(
        source,
        raw,
        output,
        target_count=int(target_count),
        applied_scale=scale,
        algorithm=selected_algorithm,
    )
    return ResampledWave(
        schema_version=1,
        algorithm=selected_algorithm,
        normalization=selected_normalization,
        anti_alias=selected_algorithm is not ResamplingAlgorithm.LINEAR,
        source_samples_sha256=_sample_hash(source),
        samples=tuple(float(value) for value in output),
        metrics=metrics,
        warnings=warnings,
    )


def compare_resampling_algorithms(
    samples: Sequence[float],
    target_count: int,
    *,
    normalization: NormalizationPolicy = NormalizationPolicy.NONE,
) -> ResamplingComparison:
    candidates = tuple(
        resample_periodic_wave(
            samples,
            target_count,
            algorithm=algorithm,
            normalization=normalization,
        )
        for algorithm in ResamplingAlgorithm
    )
    selected = min(
        candidates,
        key=lambda item: (item.metrics.quality_score, list(ResamplingAlgorithm).index(item.algorithm)),
    )
    return ResamplingComparison(
        schema_version=1,
        source_samples_sha256=candidates[0].source_samples_sha256,
        target_count=int(target_count),
        candidates=candidates,
        selected_algorithm=selected.algorithm,
        reason=(
            "All three deterministic periodic-wave resamplers were measured for spectral "
            "error, alias contamination, phase, fundamental, low-band preservation, ringing, "
            "and level behavior; the lowest bounded quality score was selected."
        ),
    )
