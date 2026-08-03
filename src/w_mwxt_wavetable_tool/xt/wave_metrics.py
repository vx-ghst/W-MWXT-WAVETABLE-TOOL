from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Sequence

import numpy as np
import numpy.typing as npt

from ..errors import AnalysisError
from ..profiles import PROFILE_METRIC_NAMES, ProfileWeights


_EPSILON = 1.0e-12
FloatArray = npt.NDArray[np.float64]


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


def _validate(samples: Sequence[float], *, name: str) -> FloatArray:
    array = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if array.shape != (128,):
        raise AnalysisError(f"{name} must contain exactly 128 samples")
    if not np.all(np.isfinite(array)):
        raise AnalysisError(f"{name} contains NaN or infinite values")
    if float(np.max(np.abs(array))) > 1.0 + _EPSILON:
        raise AnalysisError(f"{name} exceeds normalized range [-1, 1]")
    return array


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _rms(samples: FloatArray) -> float:
    return float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))


def _correlation(left: FloatArray, right: FloatArray) -> float:
    a = left - float(np.mean(left, dtype=np.float64))
    b = right - float(np.mean(right, dtype=np.float64))
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= _EPSILON:
        return 1.0 if np.allclose(left, right, atol=1.0e-12, rtol=0.0) else 0.0
    return float(np.clip(np.dot(a, b) / denominator, -1.0, 1.0))


def _phase_metrics(left: FloatArray, right: FloatArray) -> tuple[int, float, float]:
    correlations = np.asarray([_correlation(left, np.roll(right, shift)) for shift in range(left.size)])
    best_value = float(np.max(correlations))
    indexes = np.flatnonzero(np.isclose(correlations, best_value, atol=1.0e-15, rtol=0.0))
    best = min((int(index) for index in indexes), key=lambda value: (min(value, left.size - value), value))
    signed = best if best <= left.size // 2 else best - left.size
    score = _clip01(0.5 * abs(signed) / (left.size / 2.0) + 0.5 * (1.0 - best_value) / 2.0)
    return signed, best_value, score


def _magnitude(samples: FloatArray) -> FloatArray:
    return np.asarray(np.abs(np.fft.rfft(samples))[1:], dtype=np.float64)


def _normalized_spectrum(samples: FloatArray) -> FloatArray:
    magnitude = _magnitude(samples)
    norm = float(np.linalg.norm(magnitude))
    if norm <= _EPSILON:
        return np.zeros_like(magnitude)
    return magnitude / norm


def _band_ratios(samples: FloatArray) -> tuple[float, float, float]:
    power = np.square(_magnitude(samples))
    total = float(np.sum(power, dtype=np.float64))
    if total <= _EPSILON:
        return 0.0, 0.0, 0.0
    low = float(np.sum(power[:4], dtype=np.float64) / total)
    mid = float(np.sum(power[4:16], dtype=np.float64) / total)
    high = max(0.0, 1.0 - low - mid)
    return low, mid, high


def _perceptual_wave_features(samples: FloatArray) -> tuple[float, ...]:
    magnitude = _magnitude(samples)
    power = np.square(magnitude)
    total = float(np.sum(power, dtype=np.float64))
    if total <= _EPSILON:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    normalized_power = power / total
    indexes = np.arange(1, normalized_power.size + 1, dtype=np.float64)
    low, mid, high = _band_ratios(samples)
    fundamental = float(normalized_power[0]) if normalized_power.size else 0.0
    brightness = float(np.sum(indexes * normalized_power) / max(1.0, normalized_power.size))
    hardness = _clip01(0.65 * high + 0.35 * float(np.max(normalized_power)))
    peak = float(np.max(np.abs(samples)))
    rms = _rms(samples)
    crest = peak / max(rms, _EPSILON)
    saturation = _clip01(1.0 - min(1.0, crest / math.sqrt(2.0)))
    nonzero = normalized_power[normalized_power > 0.0]
    entropy = (
        0.0
        if normalized_power.size <= 1 or nonzero.size == 0
        else float(-np.sum(nonzero * np.log(nonzero)) / math.log(normalized_power.size))
    )
    geometric = float(np.exp(np.mean(np.log(np.maximum(power, np.finfo(np.float64).tiny)))))
    arithmetic = float(np.mean(np.maximum(power, np.finfo(np.float64).tiny)))
    flatness = _clip01(geometric / arithmetic)
    concentration = _clip01(float(np.max(normalized_power)))
    return (
        low,
        fundamental,
        _clip01(brightness),
        hardness,
        saturation,
        _clip01(entropy),
        concentration,
        flatness,
    )


@dataclass(frozen=True, slots=True)
class XtWaveMetrics:
    schema_version: int
    source_samples_sha256: str
    reconstructed_samples_sha256: str
    source_rms: float
    reconstructed_rms: float
    source_peak: float
    reconstructed_peak: float
    time_rmse: float
    time_nrmse: float
    maximum_absolute_error: float
    correlation: float
    phase_shift_samples: int
    phase_correlation: float
    phase_difference: float
    spectral_rmse: float
    spectral_similarity: float
    harmonic_loss: float
    h1_error: float
    h2_error: float
    h3_error: float
    low_band_error: float
    mid_band_error: float
    high_band_error: float
    perceptual_difference: float
    seam_value_error: float
    seam_slope_error: float
    amplitude_error: float
    aliasing_risk: float
    ringing_score: float
    subharmonic_risk: float
    sub_score: float
    bass_score: float
    monophonic_bass_warning: bool
    objective_components: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported XT-wave-metrics schema version")
        for name in ("source_samples_sha256", "reconstructed_samples_sha256"):
            value = getattr(self, name)
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise AnalysisError(f"{name} must be a SHA-256 digest")
        numeric_fields = (
            "source_rms",
            "reconstructed_rms",
            "source_peak",
            "reconstructed_peak",
            "time_rmse",
            "time_nrmse",
            "maximum_absolute_error",
            "correlation",
            "phase_correlation",
            "phase_difference",
            "spectral_rmse",
            "spectral_similarity",
            "harmonic_loss",
            "h1_error",
            "h2_error",
            "h3_error",
            "low_band_error",
            "mid_band_error",
            "high_band_error",
            "perceptual_difference",
            "seam_value_error",
            "seam_slope_error",
            "amplitude_error",
            "aliasing_risk",
            "ringing_score",
            "subharmonic_risk",
            "sub_score",
            "bass_score",
        )
        for name in numeric_fields:
            if not math.isfinite(float(getattr(self, name))):
                raise AnalysisError(f"wave metric {name} must be finite")
        if not -1.0 <= self.correlation <= 1.0 or not -1.0 <= self.phase_correlation <= 1.0:
            raise AnalysisError("correlations must be between -1 and 1")
        bounded = (
            "phase_difference",
            "spectral_rmse",
            "spectral_similarity",
            "harmonic_loss",
            "h1_error",
            "h2_error",
            "h3_error",
            "low_band_error",
            "mid_band_error",
            "high_band_error",
            "perceptual_difference",
            "seam_value_error",
            "seam_slope_error",
            "amplitude_error",
            "aliasing_risk",
            "ringing_score",
            "subharmonic_risk",
            "sub_score",
            "bass_score",
        )
        for name in bounded:
            if not 0.0 <= float(getattr(self, name)) <= 1.0:
                raise AnalysisError(f"{name} must be a bounded ratio")
        if tuple(name for name, _ in self.objective_components) != PROFILE_METRIC_NAMES:
            raise AnalysisError("objective_components must use canonical profile metric order")
        if any(not 0.0 <= value <= 1.0 for _, value in self.objective_components):
            raise AnalysisError("objective component values must be bounded")
        expected_warning = self.sub_score < 0.65 or self.phase_difference > 0.25
        if self.monophonic_bass_warning != expected_warning:
            raise AnalysisError("monophonic_bass_warning is inconsistent")

    @property
    def component_map(self) -> dict[str, float]:
        return dict(self.objective_components)

    def weighted_objective(self, weights: ProfileWeights) -> float:
        return float(sum(self.component_map[name] * weights.weight_map[name] for name in PROFILE_METRIC_NAMES))

    def _content_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "source_samples_sha256": self.source_samples_sha256,
            "reconstructed_samples_sha256": self.reconstructed_samples_sha256,
            "source_rms": self.source_rms,
            "reconstructed_rms": self.reconstructed_rms,
            "source_peak": self.source_peak,
            "reconstructed_peak": self.reconstructed_peak,
            "time_rmse": self.time_rmse,
            "time_nrmse": self.time_nrmse,
            "maximum_absolute_error": self.maximum_absolute_error,
            "correlation": self.correlation,
            "phase_shift_samples": self.phase_shift_samples,
            "phase_correlation": self.phase_correlation,
            "phase_difference": self.phase_difference,
            "spectral_rmse": self.spectral_rmse,
            "spectral_similarity": self.spectral_similarity,
            "harmonic_loss": self.harmonic_loss,
            "h1_error": self.h1_error,
            "h2_error": self.h2_error,
            "h3_error": self.h3_error,
            "low_band_error": self.low_band_error,
            "mid_band_error": self.mid_band_error,
            "high_band_error": self.high_band_error,
            "perceptual_difference": self.perceptual_difference,
            "seam_value_error": self.seam_value_error,
            "seam_slope_error": self.seam_slope_error,
            "amplitude_error": self.amplitude_error,
            "aliasing_risk": self.aliasing_risk,
            "ringing_score": self.ringing_score,
            "subharmonic_risk": self.subharmonic_risk,
            "sub_score": self.sub_score,
            "bass_score": self.bass_score,
            "monophonic_bass_warning": self.monophonic_bass_warning,
            "objective_components": dict(self.objective_components),
        }
        return result

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def measure_xt_wave_metrics(
    source_samples: Sequence[float],
    reconstructed_samples: Sequence[float],
    *,
    aliasing_risk: float = 0.0,
    ringing_score: float = 0.0,
) -> XtWaveMetrics:
    source = _validate(source_samples, name="source_samples")
    reconstructed = _validate(reconstructed_samples, name="reconstructed_samples")
    alias = _clip01(float(aliasing_risk))
    ringing = _clip01(float(ringing_score))
    difference = reconstructed - source
    source_rms = _rms(source)
    reconstructed_rms = _rms(reconstructed)
    source_peak = float(np.max(np.abs(source)))
    reconstructed_peak = float(np.max(np.abs(reconstructed)))
    rmse = _rms(difference)
    nrmse = _clip01(rmse / max(source_rms, _EPSILON))
    maximum = float(np.max(np.abs(difference)))
    correlation = _correlation(source, reconstructed)
    shift, phase_correlation, phase_difference = _phase_metrics(source, reconstructed)
    source_spectrum = _normalized_spectrum(source)
    reconstructed_spectrum = _normalized_spectrum(reconstructed)
    spectral_rmse = _clip01(float(np.sqrt(np.mean(np.square(reconstructed_spectrum - source_spectrum)))))
    spectral_similarity = _clip01(float(np.dot(source_spectrum, reconstructed_spectrum)))
    source_magnitude = _magnitude(source)
    reconstructed_magnitude = _magnitude(reconstructed)
    source_total = float(np.sum(source_magnitude, dtype=np.float64))
    harmonic_loss = _clip01(
        float(np.sum(np.maximum(0.0, source_magnitude - reconstructed_magnitude), dtype=np.float64))
        / max(source_total, _EPSILON)
    )

    def harmonic_error(index: int) -> float:
        if index - 1 >= source_spectrum.size:
            return 0.0
        return _clip01(abs(float(source_spectrum[index - 1] - reconstructed_spectrum[index - 1])))

    source_bands = _band_ratios(source)
    reconstructed_bands = _band_ratios(reconstructed)
    band_errors = tuple(_clip01(abs(left - right)) for left, right in zip(source_bands, reconstructed_bands))
    perceptual_left = _perceptual_wave_features(source)
    perceptual_right = _perceptual_wave_features(reconstructed)
    perceptual_difference = _clip01(
        math.sqrt(sum((left - right) ** 2 for left, right in zip(perceptual_left, perceptual_right)) / len(perceptual_left))
    )
    amplitude_scale = max(2.0 * source_peak, _EPSILON)
    seam_value_error = _clip01(abs((reconstructed[0] - reconstructed[-1]) - (source[0] - source[-1])) / amplitude_scale)
    source_slope = (source[1] - source[0]) - (source[0] - source[-1])
    reconstructed_slope = (reconstructed[1] - reconstructed[0]) - (reconstructed[0] - reconstructed[-1])
    seam_slope_error = _clip01(abs(reconstructed_slope - source_slope) / amplitude_scale)
    amplitude_error = _clip01(abs(reconstructed_rms - source_rms) / max(source_rms, _EPSILON))
    source_fundamental = float(abs(np.fft.rfft(source)[1]))
    reconstructed_dc = float(abs(np.fft.rfft(reconstructed)[0]))
    subharmonic_risk = _clip01(reconstructed_dc / max(source_fundamental, _EPSILON))
    h1 = harmonic_error(1)
    h2 = harmonic_error(2)
    h3 = harmonic_error(3)
    sub_score = _clip01(1.0 - (0.35 * h1 + 0.25 * band_errors[0] + 0.20 * phase_difference + 0.10 * amplitude_error + 0.10 * subharmonic_risk))
    bass_score = _clip01(1.0 - (0.30 * h1 + 0.18 * h2 + 0.12 * h3 + 0.15 * band_errors[0] + 0.10 * band_errors[1] + 0.10 * phase_difference + 0.05 * amplitude_error))
    components = (
        ("time_fidelity", nrmse),
        ("spectral_fidelity", spectral_rmse),
        ("phase_fidelity", phase_difference),
        ("seam_quality", 0.5 * (seam_value_error + seam_slope_error)),
        ("fundamental", h1),
        ("h2", h2),
        ("h3", h3),
        ("low_band", band_errors[0]),
        ("mid_band", band_errors[1]),
        ("high_band", band_errors[2]),
        ("perceptual", perceptual_difference),
        ("aliasing", alias),
        ("ringing", ringing),
        ("amplitude", amplitude_error),
    )
    return XtWaveMetrics(
        schema_version=1,
        source_samples_sha256=_sample_hash(source),
        reconstructed_samples_sha256=_sample_hash(reconstructed),
        source_rms=source_rms,
        reconstructed_rms=reconstructed_rms,
        source_peak=source_peak,
        reconstructed_peak=reconstructed_peak,
        time_rmse=rmse,
        time_nrmse=nrmse,
        maximum_absolute_error=maximum,
        correlation=correlation,
        phase_shift_samples=shift,
        phase_correlation=phase_correlation,
        phase_difference=phase_difference,
        spectral_rmse=spectral_rmse,
        spectral_similarity=spectral_similarity,
        harmonic_loss=harmonic_loss,
        h1_error=h1,
        h2_error=h2,
        h3_error=h3,
        low_band_error=band_errors[0],
        mid_band_error=band_errors[1],
        high_band_error=band_errors[2],
        perceptual_difference=perceptual_difference,
        seam_value_error=seam_value_error,
        seam_slope_error=seam_slope_error,
        amplitude_error=amplitude_error,
        aliasing_risk=alias,
        ringing_score=ringing,
        subharmonic_risk=subharmonic_risk,
        sub_score=sub_score,
        bass_score=bass_score,
        monophonic_bass_warning=(sub_score < 0.65 or phase_difference > 0.25),
        objective_components=components,
    )


@dataclass(frozen=True, slots=True)
class XtAliasingNoteRisk:
    playback_frequency_hz: float
    render_sample_rate: int
    highest_safe_harmonic: int
    aliased_power_ratio: float
    risk: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.playback_frequency_hz) or self.playback_frequency_hz <= 0.0:
            raise AnalysisError("playback_frequency_hz must be positive")
        if self.render_sample_rate <= 0:
            raise AnalysisError("render_sample_rate must be positive")
        if self.highest_safe_harmonic < 0:
            raise AnalysisError("highest_safe_harmonic must not be negative")
        for name in ("aliased_power_ratio", "risk"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise AnalysisError(f"{name} must be a finite ratio")

    def to_dict(self) -> dict[str, Any]:
        return {
            "playback_frequency_hz": self.playback_frequency_hz,
            "render_sample_rate": self.render_sample_rate,
            "highest_safe_harmonic": self.highest_safe_harmonic,
            "aliased_power_ratio": self.aliased_power_ratio,
            "risk": self.risk,
        }


@dataclass(frozen=True, slots=True)
class XtAliasingAnalysis:
    schema_version: int
    samples_sha256: str
    note_risks: tuple[XtAliasingNoteRisk, ...]
    maximum_risk: float
    mean_risk: float
    warning: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported XT-aliasing-analysis schema version")
        if len(self.samples_sha256) != 64:
            raise AnalysisError("samples_sha256 must be a SHA-256 digest")
        if not self.note_risks:
            raise AnalysisError("note_risks must not be empty")
        frequencies = tuple(item.playback_frequency_hz for item in self.note_risks)
        if frequencies != tuple(sorted(frequencies)) or len(set(frequencies)) != len(frequencies):
            raise AnalysisError("note risks must use unique ascending frequencies")
        expected_max = max(item.risk for item in self.note_risks)
        expected_mean = sum(item.risk for item in self.note_risks) / len(self.note_risks)
        if not math.isclose(self.maximum_risk, expected_max, abs_tol=1.0e-12):
            raise AnalysisError("maximum_risk is inconsistent")
        if not math.isclose(self.mean_risk, expected_mean, abs_tol=1.0e-12):
            raise AnalysisError("mean_risk is inconsistent")
        if self.warning != (self.maximum_risk >= 0.10):
            raise AnalysisError("warning is inconsistent with maximum_risk")
        if not self.reason or self.reason.strip() != self.reason:
            raise AnalysisError("reason must be normalized")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "samples_sha256": self.samples_sha256,
            "note_risks": [item.to_dict() for item in self.note_risks],
            "maximum_risk": self.maximum_risk,
            "mean_risk": self.mean_risk,
            "warning": self.warning,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def analyze_xt_aliasing_risk(
    samples: Sequence[float],
    *,
    playback_frequencies_hz: Sequence[float] = (55.0, 110.0, 220.0, 440.0, 880.0),
    render_sample_rate: int = 48000,
) -> XtAliasingAnalysis:
    values = _validate(samples, name="samples")
    frequencies = tuple(float(value) for value in playback_frequencies_hz)
    if not frequencies or any(not math.isfinite(value) or value <= 0.0 for value in frequencies):
        raise AnalysisError("playback frequencies must be positive and finite")
    if frequencies != tuple(sorted(frequencies)) or len(set(frequencies)) != len(frequencies):
        raise AnalysisError("playback frequencies must be unique and ascending")
    if render_sample_rate <= 0:
        raise AnalysisError("render_sample_rate must be positive")
    power = np.square(np.abs(np.fft.rfft(values))[1:])
    total = float(np.sum(power, dtype=np.float64))
    nyquist = render_sample_rate / 2.0
    risks: list[XtAliasingNoteRisk] = []
    for frequency in frequencies:
        safe = max(0, int(math.floor(nyquist / frequency)))
        if total <= _EPSILON or safe >= power.size:
            aliased = 0.0
        else:
            aliased = float(np.sum(power[safe:], dtype=np.float64) / total)
        risk = _clip01(aliased)
        risks.append(
            XtAliasingNoteRisk(
                playback_frequency_hz=frequency,
                render_sample_rate=render_sample_rate,
                highest_safe_harmonic=safe,
                aliased_power_ratio=risk,
                risk=risk,
            )
        )
    maximum = max(item.risk for item in risks)
    mean = sum(item.risk for item in risks) / len(risks)
    return XtAliasingAnalysis(
        schema_version=1,
        samples_sha256=_sample_hash(values),
        note_risks=tuple(risks),
        maximum_risk=maximum,
        mean_risk=mean,
        warning=maximum >= 0.10,
        reason=(
            "Risk is the normalized reconstructed-wave power above the highest harmonic "
            "that remains below the selected render Nyquist at each playback frequency."
        ),
    )
