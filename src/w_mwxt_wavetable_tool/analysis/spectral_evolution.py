from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any, Iterable

import numpy as np
import numpy.typing as npt

from .harmonic_perceptual import HarmonicPerceptualAnalysis
from .spectral import SpectralAnalysis

FloatArray = npt.NDArray[np.float64]


def _finite(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked):
        raise ValueError(f"{name} must be finite")
    return checked


def _ratio(value: float, *, name: str) -> float:
    checked = _finite(value, name=name)
    if not 0.0 <= checked <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return checked


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


def _sample_hash(samples: FloatArray) -> str:
    return sha256(
        np.ascontiguousarray(samples, dtype=np.float64)
        .astype("<f8", copy=False)
        .tobytes(order="C")
    ).hexdigest()


def _periodic_hann(length: int) -> FloatArray:
    if length <= 0:
        raise ValueError("window length must be positive")
    if length == 1:
        return np.ones(1, dtype=np.float64)
    indexes = np.arange(length, dtype=np.float64)
    return 0.5 - 0.5 * np.cos((2.0 * np.pi * indexes) / float(length))


def _frames(samples: FloatArray, frame_size: int, hop_size: int) -> Iterable[tuple[int, FloatArray]]:
    if samples.size <= frame_size:
        padded = np.zeros(frame_size, dtype=np.float64)
        padded[: samples.size] = samples
        yield 0, padded
        return
    starts = list(range(0, samples.size - frame_size + 1, hop_size))
    final_start = samples.size - frame_size
    if starts[-1] != final_start:
        starts.append(final_start)
    for start in starts:
        yield start, np.ascontiguousarray(samples[start : start + frame_size])


def _normalize_power(power: FloatArray) -> FloatArray:
    total = float(np.sum(power, dtype=np.float64))
    if total <= 0.0:
        return np.zeros_like(power)
    return power / total


def _cosine_similarity(left: FloatArray, right: FloatArray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 0.0 and right_norm <= 0.0:
        return 1.0
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return float(min(1.0, max(0.0, np.dot(left, right) / (left_norm * right_norm))))


def _band_ratios(
    frequencies: FloatArray,
    normalized_power: FloatArray,
    *,
    low_max_hz: float,
    low_mid_max_hz: float,
    mid_max_hz: float,
) -> tuple[float, float, float, float]:
    masks = (
        frequencies < low_max_hz,
        (frequencies >= low_max_hz) & (frequencies < low_mid_max_hz),
        (frequencies >= low_mid_max_hz) & (frequencies < mid_max_hz),
        frequencies >= mid_max_hz,
    )
    values = [float(np.sum(normalized_power[mask], dtype=np.float64)) for mask in masks]
    total = sum(values)
    if total <= 0.0:
        return 0.0, 0.0, 0.0, 0.0
    values = [value / total for value in values]
    values[-1] = max(0.0, 1.0 - sum(values[:-1]))
    return tuple(float(min(1.0, max(0.0, value))) for value in values)  # type: ignore[return-value]


def _local_peaks(power: FloatArray, minimum_ratio: float) -> list[int]:
    if power.size < 3:
        return []
    return [
        index
        for index in range(1, power.size - 1)
        if power[index] >= minimum_ratio
        and power[index] > power[index - 1]
        and power[index] >= power[index + 1]
    ]


class PartialKind(str, Enum):
    HARMONIC = "harmonic"
    INHARMONIC = "inharmonic"


@dataclass(frozen=True, slots=True)
class SpectralEvolutionFrame:
    index: int
    start_sample: int
    center_seconds: float
    active: bool
    low_ratio: float
    low_mid_ratio: float
    mid_ratio: float
    high_ratio: float
    harmonic_energy_ratio: float
    inharmonic_energy_ratio: float
    spectral_density: float
    correlation_from_previous: float | None

    def __post_init__(self) -> None:
        if self.index < 0 or self.start_sample < 0:
            raise ValueError("frame indexes must not be negative")
        if _finite(self.center_seconds, name="center_seconds") < 0.0:
            raise ValueError("center_seconds must not be negative")
        for name in (
            "low_ratio",
            "low_mid_ratio",
            "mid_ratio",
            "high_ratio",
            "harmonic_energy_ratio",
            "inharmonic_energy_ratio",
            "spectral_density",
        ):
            _ratio(getattr(self, name), name=name)
        band_sum = self.low_ratio + self.low_mid_ratio + self.mid_ratio + self.high_ratio
        if self.active and not math.isclose(band_sum, 1.0, abs_tol=1.0e-9):
            raise ValueError("active frame band ratios must sum to one")
        if not self.active and not math.isclose(band_sum, 0.0, abs_tol=1.0e-12):
            raise ValueError("inactive frame band ratios must be zero")
        if not math.isclose(
            self.harmonic_energy_ratio + self.inharmonic_energy_ratio,
            1.0 if self.active else 0.0,
            abs_tol=1.0e-9,
        ):
            raise ValueError("harmonic and inharmonic frame ratios are inconsistent")
        if self.correlation_from_previous is not None:
            _ratio(self.correlation_from_previous, name="correlation_from_previous")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start_sample": self.start_sample,
            "center_seconds": self.center_seconds,
            "active": self.active,
            "low_ratio": self.low_ratio,
            "low_mid_ratio": self.low_mid_ratio,
            "mid_ratio": self.mid_ratio,
            "high_ratio": self.high_ratio,
            "harmonic_energy_ratio": self.harmonic_energy_ratio,
            "inharmonic_energy_ratio": self.inharmonic_energy_ratio,
            "spectral_density": self.spectral_density,
            "correlation_from_previous": self.correlation_from_previous,
        }


@dataclass(frozen=True, slots=True)
class PartialCandidate:
    index: int
    frequency_hz: float
    power_ratio: float
    kind: PartialKind
    nearest_harmonic_number: int | None
    deviation_cents: float | None
    confidence: float

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("index must not be negative")
        if _finite(self.frequency_hz, name="frequency_hz") <= 0.0:
            raise ValueError("frequency_hz must be positive")
        _ratio(self.power_ratio, name="power_ratio")
        _ratio(self.confidence, name="confidence")
        if self.kind is PartialKind.HARMONIC:
            if self.nearest_harmonic_number is None or self.nearest_harmonic_number <= 0:
                raise ValueError("harmonic partials require a positive harmonic number")
            if self.deviation_cents is None:
                raise ValueError("harmonic partials require deviation_cents")
        else:
            if self.nearest_harmonic_number is not None:
                raise ValueError("inharmonic partials must not expose a harmonic number")
        if self.deviation_cents is not None:
            _finite(self.deviation_cents, name="deviation_cents")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "frequency_hz": self.frequency_hz,
            "power_ratio": self.power_ratio,
            "kind": self.kind.value,
            "nearest_harmonic_number": self.nearest_harmonic_number,
            "deviation_cents": self.deviation_cents,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class SpectralEvolutionAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    spectral_analysis_sha256: str
    harmonic_perceptual_analysis_sha256: str
    frame_size: int
    hop_size: int
    fft_size: int
    low_band_max_hz: float
    low_mid_band_max_hz: float
    mid_band_max_hz: float
    harmonic_tolerance_cents: float
    minimum_partial_power_ratio: float
    frames: tuple[SpectralEvolutionFrame, ...]
    partials: tuple[PartialCandidate, ...]
    low_ratio: float
    low_mid_ratio: float
    mid_ratio: float
    high_ratio: float
    mean_harmonic_energy_ratio: float
    mean_inharmonic_energy_ratio: float
    harmonic_evolution_score: float
    density_evolution_score: float
    mean_adjacent_correlation: float
    useful_change_score: float
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported spectral-evolution schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "spectral_analysis_sha256",
            "harmonic_perceptual_analysis_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if self.frame_size <= 0 or self.hop_size <= 0 or self.fft_size < self.frame_size:
            raise ValueError("frame and FFT sizes are invalid")
        low = _finite(self.low_band_max_hz, name="low_band_max_hz")
        low_mid = _finite(self.low_mid_band_max_hz, name="low_mid_band_max_hz")
        mid = _finite(self.mid_band_max_hz, name="mid_band_max_hz")
        if not 0.0 < low < low_mid < mid <= self.sample_rate / 2.0:
            raise ValueError("four-band frequency boundaries are invalid")
        if _finite(self.harmonic_tolerance_cents, name="harmonic_tolerance_cents") <= 0.0:
            raise ValueError("harmonic_tolerance_cents must be positive")
        _ratio(self.minimum_partial_power_ratio, name="minimum_partial_power_ratio")
        if not self.frames:
            raise ValueError("frames must not be empty")
        if tuple(frame.index for frame in self.frames) != tuple(range(len(self.frames))):
            raise ValueError("frame indexes must be contiguous")
        if tuple(partial.index for partial in self.partials) != tuple(range(len(self.partials))):
            raise ValueError("partial indexes must be contiguous")
        if tuple(partial.frequency_hz for partial in self.partials) != tuple(
            sorted(partial.frequency_hz for partial in self.partials)
        ):
            raise ValueError("partials must be ordered by frequency")
        for name in (
            "low_ratio",
            "low_mid_ratio",
            "mid_ratio",
            "high_ratio",
            "mean_harmonic_energy_ratio",
            "mean_inharmonic_energy_ratio",
            "harmonic_evolution_score",
            "density_evolution_score",
            "mean_adjacent_correlation",
            "useful_change_score",
        ):
            _ratio(getattr(self, name), name=name)
        active = any(frame.active for frame in self.frames)
        band_total = self.low_ratio + self.low_mid_ratio + self.mid_ratio + self.high_ratio
        expected_total = 1.0 if active else 0.0
        if not math.isclose(band_total, expected_total, abs_tol=1.0e-9):
            raise ValueError("aggregate four-band ratios are inconsistent")
        if not math.isclose(
            self.mean_harmonic_energy_ratio + self.mean_inharmonic_energy_ratio,
            expected_total,
            abs_tol=1.0e-9,
        ):
            raise ValueError("aggregate harmonic ratios are inconsistent")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    @property
    def active_frame_count(self) -> int:
        return sum(frame.active for frame in self.frames)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "spectral_analysis_sha256": self.spectral_analysis_sha256,
            "harmonic_perceptual_analysis_sha256": self.harmonic_perceptual_analysis_sha256,
            "frame_size": self.frame_size,
            "hop_size": self.hop_size,
            "fft_size": self.fft_size,
            "low_band_max_hz": self.low_band_max_hz,
            "low_mid_band_max_hz": self.low_mid_band_max_hz,
            "mid_band_max_hz": self.mid_band_max_hz,
            "harmonic_tolerance_cents": self.harmonic_tolerance_cents,
            "minimum_partial_power_ratio": self.minimum_partial_power_ratio,
            "frames": [frame.to_dict() for frame in self.frames],
            "frame_count": len(self.frames),
            "active_frame_count": self.active_frame_count,
            "partials": [partial.to_dict() for partial in self.partials],
            "partial_count": len(self.partials),
            "low_ratio": self.low_ratio,
            "low_mid_ratio": self.low_mid_ratio,
            "mid_ratio": self.mid_ratio,
            "high_ratio": self.high_ratio,
            "mean_harmonic_energy_ratio": self.mean_harmonic_energy_ratio,
            "mean_inharmonic_energy_ratio": self.mean_inharmonic_energy_ratio,
            "harmonic_evolution_score": self.harmonic_evolution_score,
            "density_evolution_score": self.density_evolution_score,
            "mean_adjacent_correlation": self.mean_adjacent_correlation,
            "useful_change_score": self.useful_change_score,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class SpectralSpan:
    label: str
    start_sample: int
    end_sample: int

    def __post_init__(self) -> None:
        if not self.label or self.label.strip() != self.label:
            raise ValueError("label must be a non-empty normalized string")
        if self.start_sample < 0 or self.end_sample <= self.start_sample:
            raise ValueError("spectral span bounds are invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
        }


@dataclass(frozen=True, slots=True)
class SpectralCorrelation:
    left_index: int
    right_index: int
    correlation: float
    distance: float

    def __post_init__(self) -> None:
        if self.left_index < 0 or self.right_index <= self.left_index:
            raise ValueError("correlation indexes must form an ordered unique pair")
        _ratio(self.correlation, name="correlation")
        _ratio(self.distance, name="distance")
        if not math.isclose(self.correlation + self.distance, 1.0, abs_tol=1.0e-12):
            raise ValueError("correlation and distance must sum to one")

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_index": self.left_index,
            "right_index": self.right_index,
            "correlation": self.correlation,
            "distance": self.distance,
        }


@dataclass(frozen=True, slots=True)
class SpectralCorrelationMatrix:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    fft_size: int
    spans: tuple[SpectralSpan, ...]
    correlations: tuple[SpectralCorrelation, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported spectral-correlation schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0 or self.fft_size <= 0:
            raise ValueError("spectral correlation identity is invalid")
        if not _hash_is_valid(self.sample_sha256):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if len(self.spans) < 2:
            raise ValueError("at least two spans are required")
        if any(span.end_sample > self.sample_count for span in self.spans):
            raise ValueError("spectral span exceeds source bounds")
        expected_pairs = len(self.spans) * (len(self.spans) - 1) // 2
        if len(self.correlations) != expected_pairs:
            raise ValueError("correlation pair count is inconsistent")
        expected_indexes = tuple(
            (left, right)
            for left in range(len(self.spans))
            for right in range(left + 1, len(self.spans))
        )
        actual_indexes = tuple(
            (item.left_index, item.right_index) for item in self.correlations
        )
        if actual_indexes != expected_indexes:
            raise ValueError("correlations must use canonical pair order")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "fft_size": self.fft_size,
            "spans": [span.to_dict() for span in self.spans],
            "correlations": [item.to_dict() for item in self.correlations],
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _validate_links(
    samples: FloatArray,
    sample_rate: int,
    spectral_analysis: SpectralAnalysis,
    harmonic_analysis: HarmonicPerceptualAnalysis,
) -> None:
    if sample_rate != spectral_analysis.sample_rate:
        raise ValueError("sample rate does not match spectral analysis")
    if samples.size != spectral_analysis.sample_count:
        raise ValueError("sample count does not match spectral analysis")
    if _sample_hash(samples) != spectral_analysis.sample_sha256:
        raise ValueError("sample hash does not match spectral analysis")
    if harmonic_analysis.sample_rate != sample_rate:
        raise ValueError("harmonic analysis sample rate is inconsistent")
    if harmonic_analysis.sample_count != samples.size:
        raise ValueError("harmonic analysis sample count is inconsistent")
    if harmonic_analysis.sample_sha256 != spectral_analysis.sample_sha256:
        raise ValueError("harmonic analysis sample hash is inconsistent")
    if harmonic_analysis.spectral_analysis_sha256 != spectral_analysis.analysis_sha256:
        raise ValueError("harmonic analysis does not link to spectral analysis")


def analyze_spectral_evolution(
    samples: npt.ArrayLike,
    sample_rate: int,
    spectral_analysis: SpectralAnalysis,
    harmonic_analysis: HarmonicPerceptualAnalysis,
    *,
    low_band_max_hz: float = 250.0,
    low_mid_band_max_hz: float = 1000.0,
    mid_band_max_hz: float = 4000.0,
    harmonic_tolerance_cents: float = 40.0,
    minimum_partial_power_ratio: float = 0.002,
    maximum_partials: int = 64,
) -> SpectralEvolutionAnalysis:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 1 or data.size == 0:
        raise ValueError("spectral evolution expects non-empty mono samples")
    if not bool(np.all(np.isfinite(data))):
        raise ValueError("spectral evolution requires finite samples")
    _validate_links(data, int(sample_rate), spectral_analysis, harmonic_analysis)

    low = _finite(low_band_max_hz, name="low_band_max_hz")
    low_mid = _finite(low_mid_band_max_hz, name="low_mid_band_max_hz")
    mid = min(_finite(mid_band_max_hz, name="mid_band_max_hz"), sample_rate / 2.0)
    if not 0.0 < low < low_mid < mid:
        raise ValueError("four-band frequency boundaries are invalid")
    tolerance = _finite(harmonic_tolerance_cents, name="harmonic_tolerance_cents")
    if tolerance <= 0.0:
        raise ValueError("harmonic_tolerance_cents must be positive")
    minimum_partial = _ratio(
        minimum_partial_power_ratio, name="minimum_partial_power_ratio"
    )
    if int(maximum_partials) <= 0:
        raise ValueError("maximum_partials must be positive")

    frame_size = spectral_analysis.frame_size
    hop_size = spectral_analysis.hop_size
    fft_size = spectral_analysis.fft_size
    window = _periodic_hann(frame_size)
    frequencies = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)
    fundamental = harmonic_analysis.fundamental_frequency_hz

    built_frames: list[SpectralEvolutionFrame] = []
    active_powers: list[FloatArray] = []
    previous_active: FloatArray | None = None
    for frame_index, (start, frame) in enumerate(_frames(data, frame_size, hop_size)):
        rms = float(np.sqrt(np.mean(frame * frame, dtype=np.float64)))
        active = rms > spectral_analysis.active_rms_threshold
        if active:
            transformed = np.fft.rfft(frame * window, n=fft_size)
            normalized = _normalize_power(np.abs(transformed) ** 2)
            bands = _band_ratios(
                frequencies,
                normalized,
                low_max_hz=low,
                low_mid_max_hz=low_mid,
                mid_max_hz=mid,
            )
            if fundamental is not None:
                harmonic_mask = np.zeros(normalized.size, dtype=bool)
                maximum_harmonic = int((sample_rate / 2.0) // fundamental)
                for harmonic_number in range(1, maximum_harmonic + 1):
                    expected = harmonic_number * fundamental
                    lower = expected / (2.0 ** (tolerance / 1200.0))
                    upper = expected * (2.0 ** (tolerance / 1200.0))
                    harmonic_mask |= (frequencies >= lower) & (frequencies <= upper)
                harmonic_ratio = float(np.sum(normalized[harmonic_mask], dtype=np.float64))
            else:
                harmonic_ratio = 0.0
            harmonic_ratio = min(1.0, max(0.0, harmonic_ratio))
            inharmonic_ratio = max(0.0, 1.0 - harmonic_ratio)
            density = float(np.count_nonzero(normalized >= minimum_partial) / normalized.size)
            correlation = (
                None if previous_active is None else _cosine_similarity(previous_active, normalized)
            )
            previous_active = normalized
            active_powers.append(normalized)
        else:
            bands = (0.0, 0.0, 0.0, 0.0)
            harmonic_ratio = 0.0
            inharmonic_ratio = 0.0
            density = 0.0
            correlation = None
        built_frames.append(
            SpectralEvolutionFrame(
                index=frame_index,
                start_sample=start,
                center_seconds=float((start + frame_size / 2.0) / sample_rate),
                active=active,
                low_ratio=bands[0],
                low_mid_ratio=bands[1],
                mid_ratio=bands[2],
                high_ratio=bands[3],
                harmonic_energy_ratio=harmonic_ratio,
                inharmonic_energy_ratio=inharmonic_ratio,
                spectral_density=min(1.0, max(0.0, density)),
                correlation_from_previous=correlation,
            )
        )

    mean_power = np.asarray(
        spectral_analysis.normalized_mean_power_spectrum, dtype=np.float64
    )
    aggregate_bands = _band_ratios(
        np.asarray(spectral_analysis.frequencies_hz, dtype=np.float64),
        mean_power,
        low_max_hz=low,
        low_mid_max_hz=low_mid,
        mid_max_hz=mid,
    ) if spectral_analysis.active_frame_count else (0.0, 0.0, 0.0, 0.0)

    mean_frequencies = np.asarray(spectral_analysis.frequencies_hz, dtype=np.float64)
    peak_indexes = _local_peaks(mean_power, minimum_partial)
    peak_indexes.sort(key=lambda index: (-mean_power[index], mean_frequencies[index]))
    peak_indexes = peak_indexes[: int(maximum_partials)]
    peak_indexes.sort(key=lambda index: mean_frequencies[index])
    partials: list[PartialCandidate] = []
    for partial_index, peak_index in enumerate(peak_indexes):
        frequency = float(mean_frequencies[peak_index])
        power_ratio = float(mean_power[peak_index])
        harmonic_number: int | None = None
        deviation: float | None = None
        kind = PartialKind.INHARMONIC
        if fundamental is not None and frequency > 0.0:
            nearest = max(1, int(round(frequency / fundamental)))
            expected = nearest * fundamental
            deviation_value = 1200.0 * math.log2(frequency / expected)
            if abs(deviation_value) <= tolerance:
                kind = PartialKind.HARMONIC
                harmonic_number = nearest
                deviation = deviation_value
        confidence = min(1.0, max(0.0, power_ratio / max(minimum_partial, 1.0e-15)))
        partials.append(
            PartialCandidate(
                index=partial_index,
                frequency_hz=frequency,
                power_ratio=min(1.0, max(0.0, power_ratio)),
                kind=kind,
                nearest_harmonic_number=harmonic_number,
                deviation_cents=deviation,
                confidence=confidence,
            )
        )

    active_frames = [frame for frame in built_frames if frame.active]
    if active_frames:
        harmonic_values = np.asarray(
            [frame.harmonic_energy_ratio for frame in active_frames], dtype=np.float64
        )
        density_values = np.asarray(
            [frame.spectral_density for frame in active_frames], dtype=np.float64
        )
        correlations = [
            frame.correlation_from_previous
            for frame in active_frames
            if frame.correlation_from_previous is not None
        ]
        mean_harmonic = float(np.mean(harmonic_values, dtype=np.float64))
        harmonic_evolution = min(1.0, float(np.ptp(harmonic_values)))
        density_evolution = min(1.0, float(np.ptp(density_values)))
        mean_correlation = (
            float(np.mean(correlations, dtype=np.float64)) if correlations else 1.0
        )
        useful_change = min(
            1.0,
            max(
                0.0,
                0.40 * harmonic_evolution
                + 0.30 * density_evolution
                + 0.30 * (1.0 - mean_correlation),
            ),
        )
        reason = (
            "Active frame trajectories quantify four-band movement, harmonic evolution, "
            "spectral density, and adjacent spectral correlation."
        )
    else:
        mean_harmonic = 0.0
        harmonic_evolution = 0.0
        density_evolution = 0.0
        mean_correlation = 1.0
        useful_change = 0.0
        reason = "No active frame was available for spectral-evolution analysis."

    return SpectralEvolutionAnalysis(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=spectral_analysis.sample_sha256,
        spectral_analysis_sha256=spectral_analysis.analysis_sha256,
        harmonic_perceptual_analysis_sha256=harmonic_analysis.analysis_sha256,
        frame_size=frame_size,
        hop_size=hop_size,
        fft_size=fft_size,
        low_band_max_hz=low,
        low_mid_band_max_hz=low_mid,
        mid_band_max_hz=mid,
        harmonic_tolerance_cents=tolerance,
        minimum_partial_power_ratio=minimum_partial,
        frames=tuple(built_frames),
        partials=tuple(partials),
        low_ratio=aggregate_bands[0],
        low_mid_ratio=aggregate_bands[1],
        mid_ratio=aggregate_bands[2],
        high_ratio=aggregate_bands[3],
        mean_harmonic_energy_ratio=mean_harmonic,
        mean_inharmonic_energy_ratio=(1.0 - mean_harmonic if active_frames else 0.0),
        harmonic_evolution_score=harmonic_evolution,
        density_evolution_score=density_evolution,
        mean_adjacent_correlation=mean_correlation,
        useful_change_score=useful_change,
        reason=reason,
    )


def analyze_spectral_correlations(
    samples: npt.ArrayLike,
    sample_rate: int,
    spans: Iterable[SpectralSpan],
    *,
    fft_size: int = 4096,
) -> SpectralCorrelationMatrix:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 1 or data.size == 0:
        raise ValueError("spectral correlation expects non-empty mono samples")
    if not bool(np.all(np.isfinite(data))):
        raise ValueError("spectral correlation requires finite samples")
    if int(sample_rate) <= 0 or int(fft_size) <= 0:
        raise ValueError("sample_rate and fft_size must be positive")
    span_tuple = tuple(spans)
    if len(span_tuple) < 2:
        raise ValueError("at least two spans are required")
    if any(span.end_sample > data.size for span in span_tuple):
        raise ValueError("spectral span exceeds source bounds")

    spectra: list[FloatArray] = []
    for span in span_tuple:
        selection = data[span.start_sample : span.end_sample]
        window = _periodic_hann(selection.size)
        transformed = np.fft.rfft(selection * window, n=int(fft_size))
        spectra.append(_normalize_power(np.abs(transformed) ** 2))

    correlations: list[SpectralCorrelation] = []
    for left in range(len(spectra)):
        for right in range(left + 1, len(spectra)):
            correlation = _cosine_similarity(spectra[left], spectra[right])
            correlations.append(
                SpectralCorrelation(
                    left_index=left,
                    right_index=right,
                    correlation=correlation,
                    distance=float(1.0 - correlation),
                )
            )
    return SpectralCorrelationMatrix(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=_sample_hash(data),
        fft_size=int(fft_size),
        spans=span_tuple,
        correlations=tuple(correlations),
    )
