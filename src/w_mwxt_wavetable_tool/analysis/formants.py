from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any

import numpy as np

from .spectral import SpectralAnalysis


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


def _triangular_kernel(radius: int) -> np.ndarray:
    if radius <= 0:
        return np.ones(1, dtype=np.float64)
    rising = np.arange(1, radius + 2, dtype=np.float64)
    kernel = np.concatenate((rising, rising[-2::-1]))
    return kernel / float(np.sum(kernel, dtype=np.float64))


@dataclass(frozen=True, slots=True)
class FormantCandidate:
    index: int
    frequency_hz: float
    bandwidth_hz: float
    envelope_power_ratio: float
    prominence_db: float
    confidence: float

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("index must not be negative")
        if _finite(self.frequency_hz, name="frequency_hz") <= 0.0:
            raise ValueError("frequency_hz must be positive")
        if _finite(self.bandwidth_hz, name="bandwidth_hz") <= 0.0:
            raise ValueError("bandwidth_hz must be positive")
        _ratio(self.envelope_power_ratio, name="envelope_power_ratio")
        if _finite(self.prominence_db, name="prominence_db") < 0.0:
            raise ValueError("prominence_db must not be negative")
        _ratio(self.confidence, name="confidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "frequency_hz": self.frequency_hz,
            "bandwidth_hz": self.bandwidth_hz,
            "envelope_power_ratio": self.envelope_power_ratio,
            "prominence_db": self.prominence_db,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class FormantAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    spectral_analysis_sha256: str
    minimum_frequency_hz: float
    maximum_frequency_hz: float
    smoothing_bandwidth_hz: float
    minimum_prominence_db: float
    minimum_separation_hz: float
    maximum_candidates: int
    candidates: tuple[FormantCandidate, ...]
    aggregate_confidence: float
    formant_structure_detected: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported formant-analysis schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in ("sample_sha256", "spectral_analysis_sha256"):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        minimum = _finite(self.minimum_frequency_hz, name="minimum_frequency_hz")
        maximum = _finite(self.maximum_frequency_hz, name="maximum_frequency_hz")
        if minimum <= 0.0 or maximum <= minimum:
            raise ValueError("formant frequency bounds are invalid")
        if maximum > self.sample_rate / 2.0 + 1.0e-12:
            raise ValueError("maximum_frequency_hz must not exceed Nyquist")
        if _finite(self.smoothing_bandwidth_hz, name="smoothing_bandwidth_hz") <= 0.0:
            raise ValueError("smoothing_bandwidth_hz must be positive")
        if _finite(self.minimum_prominence_db, name="minimum_prominence_db") < 0.0:
            raise ValueError("minimum_prominence_db must not be negative")
        if _finite(self.minimum_separation_hz, name="minimum_separation_hz") <= 0.0:
            raise ValueError("minimum_separation_hz must be positive")
        if self.maximum_candidates <= 0:
            raise ValueError("maximum_candidates must be positive")
        if len(self.candidates) > self.maximum_candidates:
            raise ValueError("candidate count exceeds maximum_candidates")
        if tuple(candidate.index for candidate in self.candidates) != tuple(
            range(len(self.candidates))
        ):
            raise ValueError("candidate indexes must be contiguous")
        frequencies = tuple(candidate.frequency_hz for candidate in self.candidates)
        if frequencies != tuple(sorted(frequencies)):
            raise ValueError("formant candidates must be ordered by frequency")
        if any(
            right - left < self.minimum_separation_hz - 1.0e-9
            for left, right in zip(frequencies, frequencies[1:])
        ):
            raise ValueError("formant candidates violate minimum separation")
        _ratio(self.aggregate_confidence, name="aggregate_confidence")
        if self.formant_structure_detected != bool(self.candidates):
            raise ValueError("formant_structure_detected is inconsistent")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "spectral_analysis_sha256": self.spectral_analysis_sha256,
            "minimum_frequency_hz": self.minimum_frequency_hz,
            "maximum_frequency_hz": self.maximum_frequency_hz,
            "smoothing_bandwidth_hz": self.smoothing_bandwidth_hz,
            "minimum_prominence_db": self.minimum_prominence_db,
            "minimum_separation_hz": self.minimum_separation_hz,
            "maximum_candidates": self.maximum_candidates,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "candidate_count": len(self.candidates),
            "aggregate_confidence": self.aggregate_confidence,
            "formant_structure_detected": self.formant_structure_detected,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def analyze_formants(
    spectral_analysis: SpectralAnalysis,
    *,
    minimum_frequency_hz: float = 90.0,
    maximum_frequency_hz: float = 5000.0,
    smoothing_bandwidth_hz: float = 180.0,
    minimum_prominence_db: float = 1.5,
    minimum_separation_hz: float = 180.0,
    maximum_candidates: int = 5,
) -> FormantAnalysis:
    """Estimate broad spectral-envelope peaks without claiming phonetic identity."""

    if not isinstance(spectral_analysis, SpectralAnalysis):
        raise TypeError("spectral_analysis must be a SpectralAnalysis")
    minimum = _finite(minimum_frequency_hz, name="minimum_frequency_hz")
    maximum = min(
        _finite(maximum_frequency_hz, name="maximum_frequency_hz"),
        float(spectral_analysis.nyquist_hz),
    )
    if minimum <= 0.0 or maximum <= minimum:
        raise ValueError("formant frequency bounds are invalid")
    smoothing = _finite(smoothing_bandwidth_hz, name="smoothing_bandwidth_hz")
    if smoothing <= 0.0:
        raise ValueError("smoothing_bandwidth_hz must be positive")
    prominence_threshold = _finite(
        minimum_prominence_db, name="minimum_prominence_db"
    )
    if prominence_threshold < 0.0:
        raise ValueError("minimum_prominence_db must not be negative")
    separation = _finite(minimum_separation_hz, name="minimum_separation_hz")
    if separation <= 0.0:
        raise ValueError("minimum_separation_hz must be positive")
    if int(maximum_candidates) <= 0:
        raise ValueError("maximum_candidates must be positive")

    frequencies = np.asarray(spectral_analysis.frequencies_hz, dtype=np.float64)
    power = np.asarray(
        spectral_analysis.normalized_mean_power_spectrum,
        dtype=np.float64,
    )
    active_mask = (frequencies >= minimum) & (frequencies <= maximum)
    selected_frequency = frequencies[active_mask]
    selected_power = power[active_mask]

    if spectral_analysis.active_frame_count == 0 or selected_power.size < 3:
        candidates: tuple[FormantCandidate, ...] = ()
        aggregate_confidence = 0.0
        reason = "No active spectral envelope is available for formant estimation."
    else:
        resolution = float(spectral_analysis.frequency_resolution_hz)
        maximum_radius = max(1, (selected_power.size - 1) // 2)
        radius = min(
            maximum_radius,
            max(1, int(round((smoothing / resolution) / 2.0))),
        )
        kernel = _triangular_kernel(radius)
        log_power = 10.0 * np.log10(
            np.maximum(selected_power, np.finfo(np.float64).tiny)
        )
        smoothed = np.convolve(log_power, kernel, mode="same")
        linear_envelope = np.power(10.0, smoothed / 10.0)
        envelope_total = float(np.sum(linear_envelope, dtype=np.float64))

        local_indexes = [
            index
            for index in range(1, smoothed.size - 1)
            if smoothed[index] > smoothed[index - 1]
            and smoothed[index] >= smoothed[index + 1]
        ]
        search_radius = max(2, int(round(separation / resolution)))
        ranked: list[tuple[float, float, int, float]] = []
        for index in local_indexes:
            left_start = max(0, index - search_radius)
            right_end = min(smoothed.size, index + search_radius + 1)
            left_min = float(np.min(smoothed[left_start : index + 1]))
            right_min = float(np.min(smoothed[index:right_end]))
            prominence = max(0.0, float(smoothed[index] - max(left_min, right_min)))
            if prominence + 1.0e-12 < prominence_threshold:
                continue
            ratio = (
                float(linear_envelope[index] / envelope_total)
                if envelope_total > 0.0
                else 0.0
            )
            confidence = min(
                1.0,
                max(
                    0.0,
                    0.65 * min(1.0, prominence / 12.0)
                    + 0.35 * min(1.0, ratio * 20.0),
                ),
            )
            ranked.append((confidence, prominence, index, ratio))

        ranked.sort(key=lambda item: (-item[0], -item[1], selected_frequency[item[2]]))
        accepted: list[tuple[float, float, int, float]] = []
        for item in ranked:
            frequency = float(selected_frequency[item[2]])
            if any(
                abs(frequency - float(selected_frequency[other[2]]))
                < separation - 1.0e-12
                for other in accepted
            ):
                continue
            accepted.append(item)
            if len(accepted) == int(maximum_candidates):
                break
        accepted.sort(key=lambda item: selected_frequency[item[2]])

        built: list[FormantCandidate] = []
        half_level_db = 3.0
        for candidate_index, (confidence, prominence, peak_index, ratio) in enumerate(
            accepted
        ):
            peak_level = float(smoothed[peak_index])
            left = peak_index
            while left > 0 and smoothed[left] >= peak_level - half_level_db:
                left -= 1
            right = peak_index
            while (
                right < smoothed.size - 1
                and smoothed[right] >= peak_level - half_level_db
            ):
                right += 1
            bandwidth = max(
                resolution,
                float(selected_frequency[right] - selected_frequency[left]),
            )
            built.append(
                FormantCandidate(
                    index=candidate_index,
                    frequency_hz=float(selected_frequency[peak_index]),
                    bandwidth_hz=bandwidth,
                    envelope_power_ratio=min(1.0, max(0.0, ratio)),
                    prominence_db=prominence,
                    confidence=confidence,
                )
            )
        candidates = tuple(built)
        aggregate_confidence = (
            float(sum(candidate.confidence for candidate in candidates) / len(candidates))
            if candidates
            else 0.0
        )
        reason = (
            f"Detected {len(candidates)} broad spectral-envelope peak(s) within "
            "the configured formant search range."
            if candidates
            else "No spectral-envelope peak met the configured prominence and separation gates."
        )

    return FormantAnalysis(
        schema_version=1,
        sample_rate=spectral_analysis.sample_rate,
        sample_count=spectral_analysis.sample_count,
        sample_sha256=spectral_analysis.sample_sha256,
        spectral_analysis_sha256=spectral_analysis.analysis_sha256,
        minimum_frequency_hz=minimum,
        maximum_frequency_hz=maximum,
        smoothing_bandwidth_hz=smoothing,
        minimum_prominence_db=prominence_threshold,
        minimum_separation_hz=separation,
        maximum_candidates=int(maximum_candidates),
        candidates=candidates,
        aggregate_confidence=aggregate_confidence,
        formant_structure_detected=bool(candidates),
        reason=reason,
    )
