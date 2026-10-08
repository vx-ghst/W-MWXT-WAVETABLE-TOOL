from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .models import WavetableCandidate, WavetableContractError, reconstruct_xt_cycle

WAVETABLE_METRICS_SCHEMA_VERSION = 1
_METRIC_PRECISION = 12
_DFT_BIN_COUNT = 32


def _q(value: float) -> float:
    return round(float(value), _METRIC_PRECISION)


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _samples(value: WavetableCandidate | Sequence[int]) -> tuple[int, ...]:
    raw = value.stored_samples if isinstance(value, WavetableCandidate) else tuple(value)
    if len(raw) != 64:
        raise WavetableContractError("wave metrics require exactly 64 stored samples")
    result: list[int] = []
    for sample in raw:
        if isinstance(sample, bool) or not isinstance(sample, int):
            raise WavetableContractError("wave metrics require integer stored samples")
        if not -127 <= sample <= 127:
            raise WavetableContractError("wave metrics require the safe stored range -127..127")
        result.append(sample)
    return tuple(result)


def _normalized_cycle(stored_samples: Sequence[int]) -> tuple[float, ...]:
    return tuple(sample / 127.0 for sample in reconstruct_xt_cycle(stored_samples))


def _rms(samples: Sequence[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise WavetableContractError("correlation requires equally sized non-empty waves")
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    numerator = sum(a * b for a, b in zip(left_centered, right_centered))
    left_energy = sum(value * value for value in left_centered)
    right_energy = sum(value * value for value in right_centered)
    denominator = math.sqrt(left_energy * right_energy)
    if denominator <= 1e-18:
        return 1.0 if all(abs(a - b) <= 1e-15 for a, b in zip(left, right)) else 0.0
    return max(-1.0, min(1.0, numerator / denominator))


def _dft_magnitudes(samples: Sequence[float]) -> tuple[float, ...]:
    size = len(samples)
    magnitudes: list[float] = []
    for bin_index in range(1, _DFT_BIN_COUNT + 1):
        real = 0.0
        imag = 0.0
        factor = -2.0 * math.pi * bin_index / size
        for sample_index, sample in enumerate(samples):
            angle = factor * sample_index
            real += sample * math.cos(angle)
            imag += sample * math.sin(angle)
        magnitudes.append(math.sqrt(real * real + imag * imag))
    total = sum(magnitudes)
    if total <= 1e-18:
        return tuple(0.0 for _ in magnitudes)
    return tuple(value / total for value in magnitudes)


def _spectral_flatness(magnitudes: Sequence[float]) -> float:
    non_zero = [max(value, 1e-15) for value in magnitudes]
    if not non_zero or sum(non_zero) <= 1e-15:
        return 0.0
    geometric = math.exp(sum(math.log(value) for value in non_zero) / len(non_zero))
    arithmetic = sum(non_zero) / len(non_zero)
    return 0.0 if arithmetic <= 1e-18 else min(1.0, geometric / arithmetic)


@dataclass(frozen=True, slots=True)
class WaveShapeMetrics:
    schema_version: int
    rms: float
    peak: float
    crest_factor: float
    dc_offset: float
    zero_crossing_rate: float
    mean_absolute_slope: float
    maximum_absolute_slope: float
    mean_absolute_curvature: float
    spectral_centroid: float
    spectral_spread: float
    low_band_ratio: float
    mid_band_ratio: float
    high_band_ratio: float
    harmonic_concentration: float
    spectral_flatness: float
    polarity_balance: float
    complexity: float

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_METRICS_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported wave-shape metrics schema version")
        for name in (
            "rms",
            "peak",
            "zero_crossing_rate",
            "mean_absolute_slope",
            "maximum_absolute_slope",
            "mean_absolute_curvature",
            "spectral_centroid",
            "spectral_spread",
            "low_band_ratio",
            "mid_band_ratio",
            "high_band_ratio",
            "harmonic_concentration",
            "spectral_flatness",
            "polarity_balance",
            "complexity",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise WavetableContractError(f"{name} must be finite and between 0 and 1")
        if not math.isfinite(float(self.crest_factor)) or self.crest_factor < 0.0:
            raise WavetableContractError("crest_factor must be finite and non-negative")
        if not math.isfinite(float(self.dc_offset)) or not -1.0 <= self.dc_offset <= 1.0:
            raise WavetableContractError("dc_offset must be finite and between -1 and 1")
        if abs((self.low_band_ratio + self.mid_band_ratio + self.high_band_ratio) - 1.0) > 1e-9 and (
            self.low_band_ratio + self.mid_band_ratio + self.high_band_ratio
        ) != 0.0:
            raise WavetableContractError("spectral band ratios must sum to one or all be zero")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "rms": self.rms,
            "peak": self.peak,
            "crest_factor": self.crest_factor,
            "dc_offset": self.dc_offset,
            "zero_crossing_rate": self.zero_crossing_rate,
            "mean_absolute_slope": self.mean_absolute_slope,
            "maximum_absolute_slope": self.maximum_absolute_slope,
            "mean_absolute_curvature": self.mean_absolute_curvature,
            "spectral_centroid": self.spectral_centroid,
            "spectral_spread": self.spectral_spread,
            "low_band_ratio": self.low_band_ratio,
            "mid_band_ratio": self.mid_band_ratio,
            "high_band_ratio": self.high_band_ratio,
            "harmonic_concentration": self.harmonic_concentration,
            "spectral_flatness": self.spectral_flatness,
            "polarity_balance": self.polarity_balance,
            "complexity": self.complexity,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class WavePairDistance:
    schema_version: int
    waveform_distance: float
    inverted_waveform_distance: float
    maximum_sample_distance: float
    correlation: float
    absolute_correlation: float
    spectral_distance: float
    feature_distance: float
    perceptual_distance: float
    exact_match: bool
    polarity_equivalent: bool

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_METRICS_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported pair-distance schema version")
        for name in (
            "waveform_distance",
            "inverted_waveform_distance",
            "maximum_sample_distance",
            "absolute_correlation",
            "spectral_distance",
            "feature_distance",
            "perceptual_distance",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise WavetableContractError(f"{name} must be finite and between 0 and 1")
        if not math.isfinite(float(self.correlation)) or not -1.0 <= self.correlation <= 1.0:
            raise WavetableContractError("correlation must be finite and between -1 and 1")
        if not isinstance(self.exact_match, bool) or not isinstance(self.polarity_equivalent, bool):
            raise WavetableContractError("pair-distance flags must be boolean")
        if self.exact_match and self.polarity_equivalent:
            raise WavetableContractError("exact and polarity-equivalent flags are mutually exclusive")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "waveform_distance": self.waveform_distance,
            "inverted_waveform_distance": self.inverted_waveform_distance,
            "maximum_sample_distance": self.maximum_sample_distance,
            "correlation": self.correlation,
            "absolute_correlation": self.absolute_correlation,
            "spectral_distance": self.spectral_distance,
            "feature_distance": self.feature_distance,
            "perceptual_distance": self.perceptual_distance,
            "exact_match": self.exact_match,
            "polarity_equivalent": self.polarity_equivalent,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


def analyze_wave_shape(value: WavetableCandidate | Sequence[int]) -> WaveShapeMetrics:
    stored = _samples(value)
    cycle = _normalized_cycle(stored)
    rms = _rms(cycle)
    peak = max((abs(sample) for sample in cycle), default=0.0)
    crest = 0.0 if rms <= 1e-18 else peak / rms
    dc_offset = sum(cycle) / len(cycle)

    non_zero_signs = [1 if value > 0.0 else -1 for value in cycle if value != 0.0]
    zero_crossings = sum(
        left != right for left, right in zip(non_zero_signs, non_zero_signs[1:])
    )
    zero_crossing_rate = 0.0 if len(non_zero_signs) < 2 else zero_crossings / (len(non_zero_signs) - 1)

    slopes = [abs(right - left) / 2.0 for left, right in zip(cycle, cycle[1:] + cycle[:1])]
    signed_slopes = [right - left for left, right in zip(cycle, cycle[1:] + cycle[:1])]
    curvatures = [
        abs(signed_slopes[(index + 1) % len(signed_slopes)] - signed_slopes[index]) / 4.0
        for index in range(len(signed_slopes))
    ]

    magnitudes = _dft_magnitudes(cycle)
    if sum(magnitudes) <= 1e-18:
        centroid = spread = low = mid = high = concentration = flatness = 0.0
    else:
        normalized_bins = [(index + 1) / _DFT_BIN_COUNT for index in range(len(magnitudes))]
        centroid = sum(position * magnitude for position, magnitude in zip(normalized_bins, magnitudes))
        spread = math.sqrt(
            sum(((position - centroid) ** 2) * magnitude for position, magnitude in zip(normalized_bins, magnitudes))
        )
        low = sum(magnitudes[:4])
        mid = sum(magnitudes[4:16])
        high = sum(magnitudes[16:])
        total = low + mid + high
        low, mid, high = (low / total, mid / total, high / total) if total > 0.0 else (0.0, 0.0, 0.0)
        concentration = sum(sorted(magnitudes, reverse=True)[:4])
        flatness = _spectral_flatness(magnitudes)

    positive = sum(sample > 0.0 for sample in cycle)
    negative = sum(sample < 0.0 for sample in cycle)
    polarity_balance = 1.0 if positive + negative == 0 else 1.0 - abs(positive - negative) / (positive + negative)
    mean_slope = sum(slopes) / len(slopes)
    maximum_slope = max(slopes, default=0.0)
    mean_curvature = sum(curvatures) / len(curvatures)
    complexity = (
        0.20 * mean_slope
        + 0.15 * maximum_slope
        + 0.20 * mean_curvature
        + 0.20 * flatness
        + 0.15 * centroid
        + 0.10 * spread
    )

    return WaveShapeMetrics(
        schema_version=WAVETABLE_METRICS_SCHEMA_VERSION,
        rms=_q(min(1.0, rms)),
        peak=_q(min(1.0, peak)),
        crest_factor=_q(crest),
        dc_offset=_q(max(-1.0, min(1.0, dc_offset))),
        zero_crossing_rate=_q(min(1.0, zero_crossing_rate)),
        mean_absolute_slope=_q(min(1.0, mean_slope)),
        maximum_absolute_slope=_q(min(1.0, maximum_slope)),
        mean_absolute_curvature=_q(min(1.0, mean_curvature)),
        spectral_centroid=_q(min(1.0, centroid)),
        spectral_spread=_q(min(1.0, spread)),
        low_band_ratio=_q(low),
        mid_band_ratio=_q(mid),
        high_band_ratio=_q(high),
        harmonic_concentration=_q(min(1.0, concentration)),
        spectral_flatness=_q(min(1.0, flatness)),
        polarity_balance=_q(min(1.0, polarity_balance)),
        complexity=_q(min(1.0, complexity)),
    )


def compare_wave_shapes(
    left: WavetableCandidate | Sequence[int],
    right: WavetableCandidate | Sequence[int],
) -> WavePairDistance:
    left_stored = _samples(left)
    right_stored = _samples(right)
    left_cycle = _normalized_cycle(left_stored)
    right_cycle = _normalized_cycle(right_stored)
    inverted_right = tuple(-sample for sample in right_cycle)

    direct_rmse = _rms(tuple(a - b for a, b in zip(left_cycle, right_cycle))) / 2.0
    inverted_rmse = _rms(tuple(a - b for a, b in zip(left_cycle, inverted_right))) / 2.0
    maximum_sample_distance = max(abs(a - b) for a, b in zip(left_cycle, right_cycle)) / 2.0
    correlation = _correlation(left_cycle, right_cycle)

    left_spectrum = _dft_magnitudes(left_cycle)
    right_spectrum = _dft_magnitudes(right_cycle)
    spectral_distance = _rms(tuple(a - b for a, b in zip(left_spectrum, right_spectrum))) * math.sqrt(
        len(left_spectrum)
    )

    left_metrics = analyze_wave_shape(left_stored)
    right_metrics = analyze_wave_shape(right_stored)
    features_left = (
        left_metrics.rms,
        left_metrics.zero_crossing_rate,
        left_metrics.mean_absolute_slope,
        left_metrics.mean_absolute_curvature,
        left_metrics.spectral_centroid,
        left_metrics.spectral_spread,
        left_metrics.low_band_ratio,
        left_metrics.high_band_ratio,
        left_metrics.harmonic_concentration,
        left_metrics.spectral_flatness,
        left_metrics.complexity,
    )
    features_right = (
        right_metrics.rms,
        right_metrics.zero_crossing_rate,
        right_metrics.mean_absolute_slope,
        right_metrics.mean_absolute_curvature,
        right_metrics.spectral_centroid,
        right_metrics.spectral_spread,
        right_metrics.low_band_ratio,
        right_metrics.high_band_ratio,
        right_metrics.harmonic_concentration,
        right_metrics.spectral_flatness,
        right_metrics.complexity,
    )
    feature_distance = _rms(tuple(a - b for a, b in zip(features_left, features_right)))

    exact_match = left_stored == right_stored
    polarity_equivalent = not exact_match and all(a == -b for a, b in zip(left_stored, right_stored))
    phase_agnostic_waveform = min(direct_rmse, inverted_rmse)
    perceptual = (
        0.45 * phase_agnostic_waveform
        + 0.35 * min(1.0, spectral_distance)
        + 0.20 * min(1.0, feature_distance)
    )

    return WavePairDistance(
        schema_version=WAVETABLE_METRICS_SCHEMA_VERSION,
        waveform_distance=_q(min(1.0, direct_rmse)),
        inverted_waveform_distance=_q(min(1.0, inverted_rmse)),
        maximum_sample_distance=_q(min(1.0, maximum_sample_distance)),
        correlation=_q(correlation),
        absolute_correlation=_q(abs(correlation)),
        spectral_distance=_q(min(1.0, spectral_distance)),
        feature_distance=_q(min(1.0, feature_distance)),
        perceptual_distance=_q(min(1.0, perceptual)),
        exact_match=exact_match,
        polarity_equivalent=polarity_equivalent,
    )
