from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any

import numpy as np
import numpy.typing as npt

from ..audio import AudioSource
from ..errors import AnalysisError
from .framing import iter_frames, validate_mono_samples

FloatArray = npt.NDArray[np.float64]


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


def _sample_sha256(samples: FloatArray) -> str:
    canonical = samples.astype("<f8", copy=False).tobytes(order="C")
    return sha256(canonical).hexdigest()


def _next_power_of_two(value: int) -> int:
    return 1 << (value - 1).bit_length()


def _periodic_hann(length: int) -> FloatArray:
    if length <= 0:
        raise AnalysisError("window length must be positive")
    if length == 1:
        return np.ones(1, dtype=np.float64)
    indexes = np.arange(length, dtype=np.float64)
    return 0.5 - 0.5 * np.cos((2.0 * np.pi * indexes) / float(length))


def _weighted_quantile_frequency(
    frequencies: FloatArray,
    normalized_power: FloatArray,
    ratio: float,
) -> float:
    index = int(np.searchsorted(np.cumsum(normalized_power), ratio, side="left"))
    index = min(index, frequencies.size - 1)
    return float(frequencies[index])


def _spectrum_descriptors(
    frequencies: FloatArray,
    normalized_power: FloatArray,
    *,
    low_band_max_hz: float,
    mid_band_max_hz: float,
) -> dict[str, float]:
    centroid = float(np.sum(frequencies * normalized_power, dtype=np.float64))
    bandwidth = float(
        np.sqrt(
            np.sum(
                ((frequencies - centroid) ** 2) * normalized_power,
                dtype=np.float64,
            )
        )
    )
    rolloff_85 = _weighted_quantile_frequency(frequencies, normalized_power, 0.85)
    rolloff_95 = _weighted_quantile_frequency(frequencies, normalized_power, 0.95)

    positive = np.maximum(normalized_power, np.finfo(np.float64).tiny)
    arithmetic_mean = float(np.mean(positive, dtype=np.float64))
    geometric_mean = float(np.exp(np.mean(np.log(positive), dtype=np.float64)))
    flatness = min(1.0, geometric_mean / arithmetic_mean)
    crest = float(np.max(normalized_power) / arithmetic_mean)

    if normalized_power.size <= 1:
        entropy = 0.0
    else:
        nonzero = normalized_power[normalized_power > 0.0]
        entropy = float(
            -np.sum(nonzero * np.log(nonzero), dtype=np.float64)
            / math.log(normalized_power.size)
        )
        entropy = min(1.0, max(0.0, entropy))

    dominant_index = int(np.argmax(normalized_power))
    dominant_frequency = float(frequencies[dominant_index])
    dominant_power_ratio = float(normalized_power[dominant_index])

    low_mask = frequencies < low_band_max_hz
    mid_mask = (frequencies >= low_band_max_hz) & (frequencies < mid_band_max_hz)
    high_mask = frequencies >= mid_band_max_hz

    low_ratio = float(np.sum(normalized_power[low_mask], dtype=np.float64))
    mid_ratio = float(np.sum(normalized_power[mid_mask], dtype=np.float64))
    high_ratio = float(np.sum(normalized_power[high_mask], dtype=np.float64))
    band_total = low_ratio + mid_ratio + high_ratio
    if band_total > 0.0:
        low_ratio /= band_total
        mid_ratio /= band_total
        high_ratio = max(0.0, 1.0 - low_ratio - mid_ratio)

    return {
        "centroid_hz": centroid,
        "bandwidth_hz": bandwidth,
        "rolloff_85_hz": rolloff_85,
        "rolloff_95_hz": rolloff_95,
        "flatness": flatness,
        "crest": crest,
        "entropy": entropy,
        "dominant_frequency_hz": dominant_frequency,
        "dominant_power_ratio": min(1.0, max(0.0, dominant_power_ratio)),
        "low_band_ratio": min(1.0, max(0.0, low_ratio)),
        "mid_band_ratio": min(1.0, max(0.0, mid_ratio)),
        "high_band_ratio": min(1.0, max(0.0, high_ratio)),
    }


@dataclass(frozen=True, slots=True)
class SpectralFrameAnalysis:
    start_sample: int
    center_seconds: float
    sample_count: int
    rms: float
    active: bool
    spectral_energy: float
    centroid_hz: float | None
    bandwidth_hz: float | None
    rolloff_85_hz: float | None
    rolloff_95_hz: float | None
    flatness: float | None
    crest: float | None
    entropy: float | None
    dominant_frequency_hz: float | None
    dominant_power_ratio: float | None
    low_band_ratio: float | None
    mid_band_ratio: float | None
    high_band_ratio: float | None
    spectral_flux_from_previous: float | None

    def __post_init__(self) -> None:
        if self.start_sample < 0:
            raise ValueError("start_sample must not be negative")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        center = _require_finite(self.center_seconds, name="center_seconds")
        if center < 0.0:
            raise ValueError("center_seconds must not be negative")
        rms = _require_finite(self.rms, name="rms")
        energy = _require_finite(self.spectral_energy, name="spectral_energy")
        if rms < 0.0 or energy < 0.0:
            raise ValueError("rms and spectral_energy must not be negative")
        optional_nonnegative = (
            (self.centroid_hz, "centroid_hz"),
            (self.bandwidth_hz, "bandwidth_hz"),
            (self.rolloff_85_hz, "rolloff_85_hz"),
            (self.rolloff_95_hz, "rolloff_95_hz"),
            (self.crest, "crest"),
            (self.dominant_frequency_hz, "dominant_frequency_hz"),
            (self.spectral_flux_from_previous, "spectral_flux_from_previous"),
        )
        for value, name in optional_nonnegative:
            checked = _optional_finite(value, name=name)
            if checked is not None and checked < 0.0:
                raise ValueError(f"{name} must not be negative")
        for value, name in (
            (self.flatness, "flatness"),
            (self.entropy, "entropy"),
            (self.dominant_power_ratio, "dominant_power_ratio"),
            (self.low_band_ratio, "low_band_ratio"),
            (self.mid_band_ratio, "mid_band_ratio"),
            (self.high_band_ratio, "high_band_ratio"),
        ):
            if value is not None:
                _require_ratio(value, name=name)
        descriptor_values = (
            self.centroid_hz,
            self.bandwidth_hz,
            self.rolloff_85_hz,
            self.rolloff_95_hz,
            self.flatness,
            self.crest,
            self.entropy,
            self.dominant_frequency_hz,
            self.dominant_power_ratio,
            self.low_band_ratio,
            self.mid_band_ratio,
            self.high_band_ratio,
        )
        if self.active:
            if any(value is None for value in descriptor_values):
                raise ValueError("active spectral frames require all descriptors")
            assert self.low_band_ratio is not None
            assert self.mid_band_ratio is not None
            assert self.high_band_ratio is not None
            if not math.isclose(
                self.low_band_ratio + self.mid_band_ratio + self.high_band_ratio,
                1.0,
                abs_tol=1e-9,
            ):
                raise ValueError("spectral band ratios must sum to one")
        elif any(value is not None for value in descriptor_values):
            raise ValueError("inactive spectral frames must not expose descriptors")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_sample": self.start_sample,
            "center_seconds": self.center_seconds,
            "sample_count": self.sample_count,
            "rms": self.rms,
            "active": self.active,
            "spectral_energy": self.spectral_energy,
            "centroid_hz": self.centroid_hz,
            "bandwidth_hz": self.bandwidth_hz,
            "rolloff_85_hz": self.rolloff_85_hz,
            "rolloff_95_hz": self.rolloff_95_hz,
            "flatness": self.flatness,
            "crest": self.crest,
            "entropy": self.entropy,
            "dominant_frequency_hz": self.dominant_frequency_hz,
            "dominant_power_ratio": self.dominant_power_ratio,
            "low_band_ratio": self.low_band_ratio,
            "mid_band_ratio": self.mid_band_ratio,
            "high_band_ratio": self.high_band_ratio,
            "spectral_flux_from_previous": self.spectral_flux_from_previous,
        }


@dataclass(frozen=True, slots=True)
class SpectralAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    frame_size: int
    hop_size: int
    fft_size: int
    window: str
    remove_dc: bool
    active_rms_threshold: float
    low_band_max_hz: float
    mid_band_max_hz: float
    frequency_resolution_hz: float
    nyquist_hz: float
    frequencies_hz: tuple[float, ...]
    normalized_mean_power_spectrum: tuple[float, ...]
    frames: tuple[SpectralFrameAnalysis, ...]
    active_frame_count: int
    active_frame_ratio: float
    mean_spectral_energy: float
    spectral_energy_std: float
    centroid_hz: float | None
    bandwidth_hz: float | None
    rolloff_85_hz: float | None
    rolloff_95_hz: float | None
    flatness: float | None
    crest: float | None
    entropy: float | None
    dominant_frequency_hz: float | None
    dominant_power_ratio: float | None
    low_band_ratio: float | None
    mid_band_ratio: float | None
    high_band_ratio: float | None
    median_spectral_flux: float | None
    maximum_spectral_flux: float | None
    spectral_stationarity: float | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported spectral-analysis schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if len(self.sample_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sample_sha256
        ):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if self.frame_size <= 0 or self.hop_size <= 0 or self.fft_size < self.frame_size:
            raise ValueError("spectral frame and FFT sizes are invalid")
        if self.window != "periodic_hann":
            raise ValueError("Unsupported spectral window")
        threshold = _require_finite(
            self.active_rms_threshold, name="active_rms_threshold"
        )
        if threshold < 0.0:
            raise ValueError("active_rms_threshold must not be negative")
        low = _require_finite(self.low_band_max_hz, name="low_band_max_hz")
        mid = _require_finite(self.mid_band_max_hz, name="mid_band_max_hz")
        if low <= 0.0 or mid <= low:
            raise ValueError("spectral band boundaries are invalid")
        resolution = _require_finite(
            self.frequency_resolution_hz, name="frequency_resolution_hz"
        )
        nyquist = _require_finite(self.nyquist_hz, name="nyquist_hz")
        if resolution <= 0.0 or nyquist <= 0.0:
            raise ValueError("spectral frequency metadata must be positive")
        if len(self.frequencies_hz) != self.fft_size // 2 + 1:
            raise ValueError("frequency grid length is inconsistent")
        if len(self.normalized_mean_power_spectrum) != len(self.frequencies_hz):
            raise ValueError("mean spectrum length is inconsistent")
        if not self.frames:
            raise ValueError("frames must not be empty")
        if self.active_frame_count != sum(frame.active for frame in self.frames):
            raise ValueError("active_frame_count is inconsistent")
        _require_ratio(self.active_frame_ratio, name="active_frame_ratio")
        for name in ("mean_spectral_energy", "spectral_energy_std"):
            value = _require_finite(getattr(self, name), name=name)
            if value < 0.0:
                raise ValueError(f"{name} must not be negative")
        spectrum = np.asarray(self.normalized_mean_power_spectrum, dtype=np.float64)
        if np.any(~np.isfinite(spectrum)) or np.any(spectrum < 0.0):
            raise ValueError("normalized mean spectrum must be finite and non-negative")
        spectrum_sum = float(np.sum(spectrum, dtype=np.float64))
        if self.active_frame_count == 0:
            if spectrum_sum != 0.0:
                raise ValueError("inactive analysis must expose a zero mean spectrum")
        elif not math.isclose(spectrum_sum, 1.0, abs_tol=1e-9):
            raise ValueError("active normalized mean spectrum must sum to one")
        optional_nonnegative = (
            "centroid_hz",
            "bandwidth_hz",
            "rolloff_85_hz",
            "rolloff_95_hz",
            "crest",
            "dominant_frequency_hz",
            "median_spectral_flux",
            "maximum_spectral_flux",
        )
        for name in optional_nonnegative:
            value = _optional_finite(getattr(self, name), name=name)
            if value is not None and value < 0.0:
                raise ValueError(f"{name} must not be negative")
        for name in (
            "flatness",
            "entropy",
            "dominant_power_ratio",
            "low_band_ratio",
            "mid_band_ratio",
            "high_band_ratio",
            "spectral_stationarity",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_ratio(value, name=name)

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "frame_size": self.frame_size,
            "hop_size": self.hop_size,
            "fft_size": self.fft_size,
            "window": self.window,
            "remove_dc": self.remove_dc,
            "active_rms_threshold": self.active_rms_threshold,
            "low_band_max_hz": self.low_band_max_hz,
            "mid_band_max_hz": self.mid_band_max_hz,
            "frequency_resolution_hz": self.frequency_resolution_hz,
            "nyquist_hz": self.nyquist_hz,
            "frequencies_hz": list(self.frequencies_hz),
            "normalized_mean_power_spectrum": list(
                self.normalized_mean_power_spectrum
            ),
            "frames": [frame.to_dict() for frame in self.frames],
            "frame_count": self.frame_count,
            "active_frame_count": self.active_frame_count,
            "active_frame_ratio": self.active_frame_ratio,
            "mean_spectral_energy": self.mean_spectral_energy,
            "spectral_energy_std": self.spectral_energy_std,
            "centroid_hz": self.centroid_hz,
            "bandwidth_hz": self.bandwidth_hz,
            "rolloff_85_hz": self.rolloff_85_hz,
            "rolloff_95_hz": self.rolloff_95_hz,
            "flatness": self.flatness,
            "crest": self.crest,
            "entropy": self.entropy,
            "dominant_frequency_hz": self.dominant_frequency_hz,
            "dominant_power_ratio": self.dominant_power_ratio,
            "low_band_ratio": self.low_band_ratio,
            "mid_band_ratio": self.mid_band_ratio,
            "high_band_ratio": self.high_band_ratio,
            "median_spectral_flux": self.median_spectral_flux,
            "maximum_spectral_flux": self.maximum_spectral_flux,
            "spectral_stationarity": self.spectral_stationarity,
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


def analyze_spectral(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    frame_size: int = 4096,
    hop_size: int = 1024,
    fft_size: int | None = None,
    remove_dc: bool = True,
    active_rms_threshold: float = 1.0e-8,
    low_band_max_hz: float = 250.0,
    mid_band_max_hz: float = 4000.0,
) -> SpectralAnalysis:
    data = validate_mono_samples(samples)
    if sample_rate <= 0:
        raise AnalysisError("sample_rate must be positive")
    if frame_size <= 0 or hop_size <= 0:
        raise AnalysisError("frame_size and hop_size must be positive")
    resolved_fft_size = _next_power_of_two(frame_size) if fft_size is None else fft_size
    if resolved_fft_size <= 0 or resolved_fft_size < frame_size:
        raise AnalysisError("fft_size must be at least frame_size")
    if resolved_fft_size & (resolved_fft_size - 1):
        raise AnalysisError("fft_size must be a power of two")
    if not math.isfinite(active_rms_threshold) or active_rms_threshold < 0.0:
        raise AnalysisError("active_rms_threshold must be finite and non-negative")
    if (
        not math.isfinite(low_band_max_hz)
        or not math.isfinite(mid_band_max_hz)
        or low_band_max_hz <= 0.0
        or mid_band_max_hz <= low_band_max_hz
    ):
        raise AnalysisError("spectral band boundaries are invalid")

    frequencies = np.fft.rfftfreq(resolved_fft_size, d=1.0 / float(sample_rate))
    frame_models: list[SpectralFrameAnalysis] = []
    active_power_spectra: list[FloatArray] = []
    active_energies: list[float] = []
    fluxes: list[float] = []
    previous_normalized_power: FloatArray | None = None

    for start, frame in iter_frames(data, frame_size=frame_size, hop_size=hop_size):
        frame_rms = float(np.sqrt(np.mean(frame * frame, dtype=np.float64)))
        centered = frame - float(np.mean(frame, dtype=np.float64)) if remove_dc else frame
        window = _periodic_hann(frame.size)
        window_energy = float(np.sum(window * window, dtype=np.float64))
        if window_energy <= 0.0:
            window = np.ones(frame.size, dtype=np.float64)
            window_energy = float(frame.size)
        spectrum = np.fft.rfft(centered * window, n=resolved_fft_size)
        power = (np.abs(spectrum) ** 2).astype(np.float64, copy=False) / window_energy
        if remove_dc:
            power[0] = 0.0
        spectral_energy = float(np.sum(power, dtype=np.float64))
        active = frame_rms > active_rms_threshold and spectral_energy > 0.0

        if active:
            normalized_power = power / spectral_energy
            descriptors = _spectrum_descriptors(
                frequencies,
                normalized_power,
                low_band_max_hz=low_band_max_hz,
                mid_band_max_hz=mid_band_max_hz,
            )
            if previous_normalized_power is None:
                flux = None
            else:
                positive_change = np.maximum(
                    normalized_power - previous_normalized_power, 0.0
                )
                flux = float(np.sqrt(np.sum(positive_change**2, dtype=np.float64)))
                fluxes.append(flux)
            previous_normalized_power = normalized_power
            active_power_spectra.append(power.copy())
            active_energies.append(spectral_energy)
            frame_models.append(
                SpectralFrameAnalysis(
                    start_sample=start,
                    center_seconds=(start + frame.size / 2.0) / float(sample_rate),
                    sample_count=frame.size,
                    rms=frame_rms,
                    active=True,
                    spectral_energy=spectral_energy,
                    spectral_flux_from_previous=flux,
                    **descriptors,
                )
            )
        else:
            previous_normalized_power = None
            frame_models.append(
                SpectralFrameAnalysis(
                    start_sample=start,
                    center_seconds=(start + frame.size / 2.0) / float(sample_rate),
                    sample_count=frame.size,
                    rms=frame_rms,
                    active=False,
                    spectral_energy=spectral_energy,
                    centroid_hz=None,
                    bandwidth_hz=None,
                    rolloff_85_hz=None,
                    rolloff_95_hz=None,
                    flatness=None,
                    crest=None,
                    entropy=None,
                    dominant_frequency_hz=None,
                    dominant_power_ratio=None,
                    low_band_ratio=None,
                    mid_band_ratio=None,
                    high_band_ratio=None,
                    spectral_flux_from_previous=None,
                )
            )

    active_count = len(active_power_spectra)
    if active_count:
        mean_power = np.mean(np.stack(active_power_spectra), axis=0, dtype=np.float64)
        mean_power_sum = float(np.sum(mean_power, dtype=np.float64))
        normalized_mean = mean_power / mean_power_sum
        aggregate = _spectrum_descriptors(
            frequencies,
            normalized_mean,
            low_band_max_hz=low_band_max_hz,
            mid_band_max_hz=mid_band_max_hz,
        )
        mean_energy = float(np.mean(active_energies, dtype=np.float64))
        energy_std = float(np.std(active_energies, dtype=np.float64))
    else:
        normalized_mean = np.zeros(frequencies.size, dtype=np.float64)
        aggregate = {
            "centroid_hz": None,
            "bandwidth_hz": None,
            "rolloff_85_hz": None,
            "rolloff_95_hz": None,
            "flatness": None,
            "crest": None,
            "entropy": None,
            "dominant_frequency_hz": None,
            "dominant_power_ratio": None,
            "low_band_ratio": None,
            "mid_band_ratio": None,
            "high_band_ratio": None,
        }
        mean_energy = 0.0
        energy_std = 0.0

    if fluxes:
        median_flux = float(np.median(np.asarray(fluxes, dtype=np.float64)))
        maximum_flux = float(np.max(np.asarray(fluxes, dtype=np.float64)))
        stationarity = 1.0 / (1.0 + median_flux)
    else:
        median_flux = None
        maximum_flux = None
        stationarity = None

    return SpectralAnalysis(
        schema_version=1,
        sample_rate=sample_rate,
        sample_count=data.size,
        sample_sha256=_sample_sha256(data),
        frame_size=frame_size,
        hop_size=hop_size,
        fft_size=resolved_fft_size,
        window="periodic_hann",
        remove_dc=remove_dc,
        active_rms_threshold=float(active_rms_threshold),
        low_band_max_hz=float(low_band_max_hz),
        mid_band_max_hz=float(mid_band_max_hz),
        frequency_resolution_hz=float(sample_rate / resolved_fft_size),
        nyquist_hz=float(sample_rate / 2.0),
        frequencies_hz=tuple(float(value) for value in frequencies),
        normalized_mean_power_spectrum=tuple(float(value) for value in normalized_mean),
        frames=tuple(frame_models),
        active_frame_count=active_count,
        active_frame_ratio=active_count / len(frame_models),
        mean_spectral_energy=mean_energy,
        spectral_energy_std=energy_std,
        median_spectral_flux=median_flux,
        maximum_spectral_flux=maximum_flux,
        spectral_stationarity=stationarity,
        **aggregate,
    )


def analyze_audio_source_spectral(
    source: AudioSource,
    **kwargs: Any,
) -> SpectralAnalysis:
    return analyze_spectral(
        source.mono_samples,
        source.metadata.sample_rate,
        **kwargs,
    )
