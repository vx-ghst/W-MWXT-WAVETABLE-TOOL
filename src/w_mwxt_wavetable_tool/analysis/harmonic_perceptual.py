from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any

import numpy as np

from ..audio import AudioSource
from ..errors import AnalysisError
from .spectral import SpectralAnalysis, analyze_audio_source_spectral


def _require_finite(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked):
        raise ValueError(f"{name} must be finite")
    return checked


def _optional_finite(value: float | None, *, name: str) -> float | None:
    if value is None:
        return None
    return _require_finite(value, name=name)


def _require_ratio(value: float, *, name: str) -> float:
    checked = _require_finite(value, name=name)
    if not 0.0 <= checked <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return checked


def _bark_value(frequency_hz: np.ndarray) -> np.ndarray:
    frequencies = np.asarray(frequency_hz, dtype=np.float64)
    return (
        13.0 * np.arctan(0.00076 * frequencies)
        + 3.5 * np.arctan((frequencies / 7500.0) ** 2)
    )


def _normalized_entropy(values: np.ndarray) -> float:
    if values.size <= 1:
        return 0.0
    nonzero = values[values > 0.0]
    if nonzero.size == 0:
        return 0.0
    entropy = float(-np.sum(nonzero * np.log(nonzero), dtype=np.float64))
    return min(1.0, max(0.0, entropy / math.log(values.size)))


@dataclass(frozen=True, slots=True)
class HarmonicPeak:
    harmonic_number: int
    expected_frequency_hz: float
    observed_frequency_hz: float
    deviation_cents: float
    band_power_ratio: float
    peak_power_ratio: float

    def __post_init__(self) -> None:
        if self.harmonic_number <= 0:
            raise ValueError("harmonic_number must be positive")
        for name in (
            "expected_frequency_hz",
            "observed_frequency_hz",
            "band_power_ratio",
            "peak_power_ratio",
        ):
            checked = _require_finite(getattr(self, name), name=name)
            if checked < 0.0:
                raise ValueError(f"{name} must not be negative")
        _require_finite(self.deviation_cents, name="deviation_cents")
        _require_ratio(self.band_power_ratio, name="band_power_ratio")
        _require_ratio(self.peak_power_ratio, name="peak_power_ratio")

    def to_dict(self) -> dict[str, Any]:
        return {
            "harmonic_number": self.harmonic_number,
            "expected_frequency_hz": self.expected_frequency_hz,
            "observed_frequency_hz": self.observed_frequency_hz,
            "deviation_cents": self.deviation_cents,
            "band_power_ratio": self.band_power_ratio,
            "peak_power_ratio": self.peak_power_ratio,
        }


@dataclass(frozen=True, slots=True)
class HarmonicPerceptualAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    spectral_analysis_sha256: str
    fundamental_frequency_hz: float | None
    maximum_harmonics: int
    harmonic_window_cents: float
    minimum_harmonic_power_ratio: float
    bark_band_count: int
    bark_band_energy_ratio: tuple[float, ...]
    bark_centroid: float | None
    bark_spread: float | None
    bark_entropy: float | None
    perceptual_brightness: float | None
    spectral_concentration: float | None
    spectral_noisiness: float | None
    harmonic_peaks: tuple[HarmonicPeak, ...]
    detected_harmonic_count: int
    harmonic_energy_ratio: float | None
    residual_energy_ratio: float | None
    harmonic_to_residual_db: float | None
    fundamental_power_ratio: float | None
    odd_harmonic_ratio: float | None
    even_harmonic_ratio: float | None
    tristimulus_1: float | None
    tristimulus_2: float | None
    tristimulus_3: float | None
    inharmonicity_cents: float | None
    harmonic_slope_db_per_octave: float | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported harmonic-perceptual schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for digest_name in ("sample_sha256", "spectral_analysis_sha256"):
            digest = getattr(self, digest_name)
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError(f"{digest_name} must be a lowercase SHA-256 digest")
        fundamental = _optional_finite(
            self.fundamental_frequency_hz, name="fundamental_frequency_hz"
        )
        if fundamental is not None and fundamental <= 0.0:
            raise ValueError("fundamental_frequency_hz must be positive")
        if self.maximum_harmonics <= 0 or self.bark_band_count <= 0:
            raise ValueError("harmonic and Bark counts must be positive")
        window = _require_finite(
            self.harmonic_window_cents, name="harmonic_window_cents"
        )
        if window <= 0.0:
            raise ValueError("harmonic_window_cents must be positive")
        _require_ratio(
            self.minimum_harmonic_power_ratio,
            name="minimum_harmonic_power_ratio",
        )
        if len(self.bark_band_energy_ratio) != self.bark_band_count:
            raise ValueError("Bark-band energy length is inconsistent")
        bark = np.asarray(self.bark_band_energy_ratio, dtype=np.float64)
        if np.any(~np.isfinite(bark)) or np.any(bark < 0.0):
            raise ValueError("Bark-band energies must be finite and non-negative")
        bark_sum = float(np.sum(bark, dtype=np.float64))
        if bark_sum != 0.0 and not math.isclose(bark_sum, 1.0, abs_tol=1e-9):
            raise ValueError("active Bark-band energies must sum to one")
        for name in (
            "bark_centroid",
            "bark_spread",
            "inharmonicity_cents",
        ):
            value = _optional_finite(getattr(self, name), name=name)
            if value is not None and value < 0.0:
                raise ValueError(f"{name} must not be negative")
        _optional_finite(
            self.harmonic_to_residual_db,
            name="harmonic_to_residual_db",
        )
        _optional_finite(
            self.harmonic_slope_db_per_octave,
            name="harmonic_slope_db_per_octave",
        )
        for name in (
            "bark_entropy",
            "perceptual_brightness",
            "spectral_concentration",
            "spectral_noisiness",
            "harmonic_energy_ratio",
            "residual_energy_ratio",
            "fundamental_power_ratio",
            "odd_harmonic_ratio",
            "even_harmonic_ratio",
            "tristimulus_1",
            "tristimulus_2",
            "tristimulus_3",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_ratio(value, name=name)
        if self.detected_harmonic_count != len(self.harmonic_peaks):
            raise ValueError("detected_harmonic_count is inconsistent")
        if self.fundamental_frequency_hz is None and self.harmonic_peaks:
            raise ValueError("unpitched analyses must not expose harmonic peaks")
        if (
            self.harmonic_energy_ratio is not None
            and self.residual_energy_ratio is not None
            and not math.isclose(
                self.harmonic_energy_ratio + self.residual_energy_ratio,
                1.0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError("harmonic and residual ratios must sum to one")
        tristimulus = (self.tristimulus_1, self.tristimulus_2, self.tristimulus_3)
        if all(value is not None for value in tristimulus):
            if not math.isclose(sum(value for value in tristimulus if value is not None), 1.0, abs_tol=1e-9):
                raise ValueError("tristimulus ratios must sum to one")
        if self.odd_harmonic_ratio is not None and self.even_harmonic_ratio is not None:
            if not math.isclose(
                self.odd_harmonic_ratio + self.even_harmonic_ratio,
                1.0,
                abs_tol=1e-9,
            ):
                raise ValueError("odd and even harmonic ratios must sum to one")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "spectral_analysis_sha256": self.spectral_analysis_sha256,
            "fundamental_frequency_hz": self.fundamental_frequency_hz,
            "maximum_harmonics": self.maximum_harmonics,
            "harmonic_window_cents": self.harmonic_window_cents,
            "minimum_harmonic_power_ratio": self.minimum_harmonic_power_ratio,
            "bark_band_count": self.bark_band_count,
            "bark_band_energy_ratio": list(self.bark_band_energy_ratio),
            "bark_centroid": self.bark_centroid,
            "bark_spread": self.bark_spread,
            "bark_entropy": self.bark_entropy,
            "perceptual_brightness": self.perceptual_brightness,
            "spectral_concentration": self.spectral_concentration,
            "spectral_noisiness": self.spectral_noisiness,
            "harmonic_peaks": [peak.to_dict() for peak in self.harmonic_peaks],
            "detected_harmonic_count": self.detected_harmonic_count,
            "harmonic_energy_ratio": self.harmonic_energy_ratio,
            "residual_energy_ratio": self.residual_energy_ratio,
            "harmonic_to_residual_db": self.harmonic_to_residual_db,
            "fundamental_power_ratio": self.fundamental_power_ratio,
            "odd_harmonic_ratio": self.odd_harmonic_ratio,
            "even_harmonic_ratio": self.even_harmonic_ratio,
            "tristimulus_1": self.tristimulus_1,
            "tristimulus_2": self.tristimulus_2,
            "tristimulus_3": self.tristimulus_3,
            "inharmonicity_cents": self.inharmonicity_cents,
            "harmonic_slope_db_per_octave": self.harmonic_slope_db_per_octave,
        }

    @property
    def analysis_sha256(self) -> str:
        rendered = json.dumps(
            self._content_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(rendered).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _bark_descriptors(
    frequencies: np.ndarray,
    normalized_power: np.ndarray,
    *,
    band_count: int,
) -> tuple[tuple[float, ...], float | None, float | None, float | None]:
    total = float(np.sum(normalized_power, dtype=np.float64))
    if total <= 0.0:
        return tuple(0.0 for _ in range(band_count)), None, None, None
    bark_positions = _bark_value(frequencies)
    indexes = np.floor(bark_positions).astype(np.int64)
    indexes = np.clip(indexes, 0, band_count - 1)
    band_energy = np.bincount(
        indexes,
        weights=normalized_power,
        minlength=band_count,
    ).astype(np.float64, copy=False)
    band_energy /= float(np.sum(band_energy, dtype=np.float64))
    centers = np.arange(band_count, dtype=np.float64) + 0.5
    centroid = float(np.sum(centers * band_energy, dtype=np.float64))
    spread = float(
        np.sqrt(
            np.sum(((centers - centroid) ** 2) * band_energy, dtype=np.float64)
        )
    )
    entropy = _normalized_entropy(band_energy)
    return (
        tuple(float(value) for value in band_energy),
        centroid,
        spread,
        entropy,
    )


def _harmonic_peaks(
    spectral_analysis: SpectralAnalysis,
    *,
    fundamental_frequency_hz: float,
    maximum_harmonics: int,
    harmonic_window_cents: float,
    minimum_harmonic_power_ratio: float,
) -> tuple[HarmonicPeak, ...]:
    frequencies = np.asarray(spectral_analysis.frequencies_hz, dtype=np.float64)
    normalized_power = np.asarray(
        spectral_analysis.normalized_mean_power_spectrum,
        dtype=np.float64,
    )
    available_harmonics = min(
        maximum_harmonics,
        int(math.floor(spectral_analysis.nyquist_hz / fundamental_frequency_hz)),
    )
    if available_harmonics <= 0:
        return ()

    assignments: list[list[int]] = [[] for _ in range(available_harmonics)]
    minimum_tolerance_hz = spectral_analysis.frequency_resolution_hz * 1.5
    for bin_index, frequency in enumerate(frequencies):
        if frequency <= 0.0:
            continue
        harmonic_number = int(round(frequency / fundamental_frequency_hz))
        if harmonic_number < 1 or harmonic_number > available_harmonics:
            continue
        expected = harmonic_number * fundamental_frequency_hz
        cents = abs(1200.0 * math.log2(frequency / expected))
        if cents <= harmonic_window_cents or abs(frequency - expected) <= minimum_tolerance_hz:
            assignments[harmonic_number - 1].append(bin_index)

    peaks: list[HarmonicPeak] = []
    for harmonic_number, bin_indexes in enumerate(assignments, start=1):
        if not bin_indexes:
            continue
        selected_power = normalized_power[bin_indexes]
        band_power = float(np.sum(selected_power, dtype=np.float64))
        local_peak_index = int(np.argmax(selected_power))
        peak_bin = bin_indexes[local_peak_index]
        peak_power = float(normalized_power[peak_bin])
        if peak_power < minimum_harmonic_power_ratio:
            continue
        expected = harmonic_number * fundamental_frequency_hz
        observed = float(frequencies[peak_bin])
        deviation = float(1200.0 * math.log2(observed / expected))
        peaks.append(
            HarmonicPeak(
                harmonic_number=harmonic_number,
                expected_frequency_hz=float(expected),
                observed_frequency_hz=observed,
                deviation_cents=deviation,
                band_power_ratio=min(1.0, max(0.0, band_power)),
                peak_power_ratio=min(1.0, max(0.0, peak_power)),
            )
        )
    return tuple(peaks)


def _harmonic_aggregates(
    peaks: tuple[HarmonicPeak, ...],
) -> dict[str, float | None]:
    if not peaks:
        return {
            "harmonic_energy_ratio": 0.0,
            "residual_energy_ratio": 1.0,
            "harmonic_to_residual_db": None,
            "fundamental_power_ratio": 0.0,
            "odd_harmonic_ratio": None,
            "even_harmonic_ratio": None,
            "tristimulus_1": None,
            "tristimulus_2": None,
            "tristimulus_3": None,
            "inharmonicity_cents": None,
            "harmonic_slope_db_per_octave": None,
        }

    powers = np.asarray([peak.band_power_ratio for peak in peaks], dtype=np.float64)
    harmonic_numbers = np.asarray(
        [peak.harmonic_number for peak in peaks], dtype=np.int64
    )
    harmonic_energy = min(1.0, float(np.sum(powers, dtype=np.float64)))
    residual = max(0.0, 1.0 - harmonic_energy)
    if harmonic_energy > 0.0 and residual > 0.0:
        ratio_db = float(10.0 * math.log10(harmonic_energy / residual))
    else:
        ratio_db = None

    harmonic_total = float(np.sum(powers, dtype=np.float64))
    if harmonic_total > 0.0:
        odd = float(np.sum(powers[harmonic_numbers % 2 == 1], dtype=np.float64)) / harmonic_total
        even = max(0.0, 1.0 - odd)
        t1 = float(np.sum(powers[harmonic_numbers == 1], dtype=np.float64)) / harmonic_total
        t2 = float(
            np.sum(
                powers[(harmonic_numbers >= 2) & (harmonic_numbers <= 4)],
                dtype=np.float64,
            )
        ) / harmonic_total
        t3 = max(0.0, 1.0 - t1 - t2)
        deviations = np.asarray(
            [abs(peak.deviation_cents) for peak in peaks], dtype=np.float64
        )
        inharmonicity = float(
            np.sum(deviations * powers, dtype=np.float64) / harmonic_total
        )
    else:
        odd = even = t1 = t2 = t3 = inharmonicity = None

    fundamental_power = float(
        np.sum(powers[harmonic_numbers == 1], dtype=np.float64)
    )

    positive_mask = powers > 0.0
    if int(np.count_nonzero(positive_mask)) >= 2:
        x = np.log2(harmonic_numbers[positive_mask].astype(np.float64))
        y = 10.0 * np.log10(powers[positive_mask])
        x_mean = float(np.mean(x, dtype=np.float64))
        y_mean = float(np.mean(y, dtype=np.float64))
        denominator = float(np.sum((x - x_mean) ** 2, dtype=np.float64))
        if denominator > 0.0:
            slope = float(
                np.sum((x - x_mean) * (y - y_mean), dtype=np.float64)
                / denominator
            )
        else:
            slope = None
    else:
        slope = None

    return {
        "harmonic_energy_ratio": harmonic_energy,
        "residual_energy_ratio": residual,
        "harmonic_to_residual_db": ratio_db,
        "fundamental_power_ratio": min(1.0, max(0.0, fundamental_power)),
        "odd_harmonic_ratio": odd,
        "even_harmonic_ratio": even,
        "tristimulus_1": t1,
        "tristimulus_2": t2,
        "tristimulus_3": t3,
        "inharmonicity_cents": inharmonicity,
        "harmonic_slope_db_per_octave": slope,
    }


def analyze_harmonic_perceptual(
    spectral_analysis: SpectralAnalysis,
    *,
    fundamental_frequency_hz: float | None,
    maximum_harmonics: int = 64,
    harmonic_window_cents: float = 35.0,
    minimum_harmonic_power_ratio: float = 1.0e-6,
    bark_band_count: int = 24,
) -> HarmonicPerceptualAnalysis:
    if maximum_harmonics <= 0:
        raise AnalysisError("maximum_harmonics must be positive")
    if not math.isfinite(harmonic_window_cents) or harmonic_window_cents <= 0.0:
        raise AnalysisError("harmonic_window_cents must be finite and positive")
    if (
        not math.isfinite(minimum_harmonic_power_ratio)
        or not 0.0 <= minimum_harmonic_power_ratio <= 1.0
    ):
        raise AnalysisError(
            "minimum_harmonic_power_ratio must be between zero and one"
        )
    if bark_band_count <= 0:
        raise AnalysisError("bark_band_count must be positive")
    if fundamental_frequency_hz is not None:
        if (
            not math.isfinite(fundamental_frequency_hz)
            or fundamental_frequency_hz <= 0.0
        ):
            raise AnalysisError("fundamental_frequency_hz must be finite and positive")
        if fundamental_frequency_hz >= spectral_analysis.nyquist_hz:
            raise AnalysisError(
                "fundamental_frequency_hz must be below the Nyquist frequency"
            )

    frequencies = np.asarray(spectral_analysis.frequencies_hz, dtype=np.float64)
    normalized_power = np.asarray(
        spectral_analysis.normalized_mean_power_spectrum,
        dtype=np.float64,
    )
    bark_energy, bark_centroid, bark_spread, bark_entropy = _bark_descriptors(
        frequencies,
        normalized_power,
        band_count=bark_band_count,
    )

    if spectral_analysis.centroid_hz is None:
        brightness = None
    else:
        brightness = min(
            1.0,
            max(0.0, spectral_analysis.centroid_hz / spectral_analysis.nyquist_hz),
        )
    concentration = (
        None
        if spectral_analysis.entropy is None
        else min(1.0, max(0.0, 1.0 - spectral_analysis.entropy))
    )
    noisiness = spectral_analysis.flatness

    if fundamental_frequency_hz is None or spectral_analysis.active_frame_count == 0:
        peaks: tuple[HarmonicPeak, ...] = ()
        if fundamental_frequency_hz is None:
            aggregates = {
                "harmonic_energy_ratio": None,
                "residual_energy_ratio": None,
                "harmonic_to_residual_db": None,
                "fundamental_power_ratio": None,
                "odd_harmonic_ratio": None,
                "even_harmonic_ratio": None,
                "tristimulus_1": None,
                "tristimulus_2": None,
                "tristimulus_3": None,
                "inharmonicity_cents": None,
                "harmonic_slope_db_per_octave": None,
            }
        else:
            aggregates = _harmonic_aggregates(peaks)
    else:
        peaks = _harmonic_peaks(
            spectral_analysis,
            fundamental_frequency_hz=fundamental_frequency_hz,
            maximum_harmonics=maximum_harmonics,
            harmonic_window_cents=harmonic_window_cents,
            minimum_harmonic_power_ratio=minimum_harmonic_power_ratio,
        )
        aggregates = _harmonic_aggregates(peaks)

    return HarmonicPerceptualAnalysis(
        schema_version=1,
        sample_rate=spectral_analysis.sample_rate,
        sample_count=spectral_analysis.sample_count,
        sample_sha256=spectral_analysis.sample_sha256,
        spectral_analysis_sha256=spectral_analysis.analysis_sha256,
        fundamental_frequency_hz=(
            None
            if fundamental_frequency_hz is None
            else float(fundamental_frequency_hz)
        ),
        maximum_harmonics=maximum_harmonics,
        harmonic_window_cents=float(harmonic_window_cents),
        minimum_harmonic_power_ratio=float(minimum_harmonic_power_ratio),
        bark_band_count=bark_band_count,
        bark_band_energy_ratio=bark_energy,
        bark_centroid=bark_centroid,
        bark_spread=bark_spread,
        bark_entropy=bark_entropy,
        perceptual_brightness=brightness,
        spectral_concentration=concentration,
        spectral_noisiness=noisiness,
        harmonic_peaks=peaks,
        detected_harmonic_count=len(peaks),
        **aggregates,
    )


def analyze_audio_source_harmonic_perceptual(
    source: AudioSource,
    *,
    fundamental_frequency_hz: float | None,
    spectral_analysis: SpectralAnalysis | None = None,
    spectral_kwargs: dict[str, Any] | None = None,
    **kwargs: Any,
) -> HarmonicPerceptualAnalysis:
    resolved_spectral = spectral_analysis
    if resolved_spectral is None:
        resolved_spectral = analyze_audio_source_spectral(
            source,
            **({} if spectral_kwargs is None else spectral_kwargs),
        )
    source_sample_sha256 = getattr(source, "sample_sha256", None)
    if (
        source_sample_sha256 is not None
        and source_sample_sha256 != resolved_spectral.sample_sha256
    ):
        raise AnalysisError("spectral analysis sample identity does not match audio source")
    return analyze_harmonic_perceptual(
        resolved_spectral,
        fundamental_frequency_hz=fundamental_frequency_hz,
        **kwargs,
    )
