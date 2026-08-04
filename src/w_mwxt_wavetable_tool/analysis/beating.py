from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any

import numpy as np
import numpy.typing as npt

from .framing import validate_mono_samples
from ..errors import AnalysisError


def _canonical_hash(payload: dict[str, Any]) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sample_hash(samples: np.ndarray) -> str:
    return sha256(samples.astype("<f8", copy=False).tobytes(order="C")).hexdigest()


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _ratio(value: float, *, name: str) -> float:
    result = _finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


@dataclass(frozen=True, slots=True)
class BeatingAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    primary_frequency_hz: float | None
    secondary_frequency_hz: float | None
    beat_rate_hz: float
    detune_cents: float
    secondary_to_primary_ratio: float
    confidence: float
    close_fundamentals_detected: bool
    unison_detected: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported beating schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if not _hash_is_valid(self.sample_sha256):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        for name in ("primary_frequency_hz", "secondary_frequency_hz"):
            value = getattr(self, name)
            if value is not None and _finite(value, name=name) <= 0.0:
                raise ValueError(f"{name} must be positive when defined")
        for name in ("beat_rate_hz", "detune_cents"):
            if _finite(getattr(self, name), name=name) < 0.0:
                raise ValueError(f"{name} must not be negative")
        _ratio(self.secondary_to_primary_ratio, name="secondary_to_primary_ratio")
        _ratio(self.confidence, name="confidence")
        if self.close_fundamentals_detected and (
            self.primary_frequency_hz is None or self.secondary_frequency_hz is None
        ):
            raise ValueError("detected close fundamentals require two frequencies")
        if not self.reason:
            raise ValueError("reason must not be empty")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "primary_frequency_hz": self.primary_frequency_hz,
            "secondary_frequency_hz": self.secondary_frequency_hz,
            "beat_rate_hz": self.beat_rate_hz,
            "detune_cents": self.detune_cents,
            "secondary_to_primary_ratio": self.secondary_to_primary_ratio,
            "confidence": self.confidence,
            "close_fundamentals_detected": self.close_fundamentals_detected,
            "unison_detected": self.unison_detected,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _parabolic_frequency(magnitudes: np.ndarray, index: int, bin_hz: float) -> float:
    offset = 0.0
    if 0 < index < magnitudes.size - 1:
        left = float(magnitudes[index - 1])
        center = float(magnitudes[index])
        right = float(magnitudes[index + 1])
        denominator = left - 2.0 * center + right
        if abs(denominator) > 1e-24:
            offset = float(np.clip(0.5 * (left - right) / denominator, -0.5, 0.5))
    return float((index + offset) * bin_hz)


def analyze_beating(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    minimum_frequency_hz: float = 35.0,
    maximum_frequency_hz: float = 2000.0,
    maximum_detune_cents: float = 80.0,
    minimum_secondary_ratio: float = 0.08,
    unison_cents: float = 25.0,
    maximum_samples: int = 131072,
) -> BeatingAnalysis:
    data = validate_mono_samples(samples)
    if sample_rate <= 0:
        raise AnalysisError("sample_rate must be positive")
    if (
        not math.isfinite(minimum_frequency_hz)
        or not math.isfinite(maximum_frequency_hz)
        or minimum_frequency_hz <= 0.0
        or maximum_frequency_hz <= minimum_frequency_hz
    ):
        raise AnalysisError("frequency bounds must be finite and ordered")
    if maximum_frequency_hz >= sample_rate / 2.0:
        raise AnalysisError("maximum_frequency_hz must be below Nyquist")
    if maximum_detune_cents <= 0.0 or not math.isfinite(maximum_detune_cents):
        raise AnalysisError("maximum_detune_cents must be finite and positive")
    if (
        not math.isfinite(minimum_secondary_ratio)
        or not 0.0 < minimum_secondary_ratio <= 1.0
    ):
        raise AnalysisError("minimum_secondary_ratio must be finite and in (0, 1]")
    if (
        not math.isfinite(unison_cents)
        or unison_cents < 0.0
        or unison_cents > maximum_detune_cents
    ):
        raise AnalysisError("unison_cents must be finite and within the detune range")
    if maximum_samples <= 0:
        raise AnalysisError("maximum_samples must be positive")

    if data.size > maximum_samples:
        start = (data.size - maximum_samples) // 2
        analysis_data = data[start : start + maximum_samples]
    else:
        analysis_data = data

    centered = analysis_data - float(np.mean(analysis_data, dtype=np.float64))
    if float(np.dot(centered, centered)) <= 1e-24:
        return BeatingAnalysis(
            schema_version=1,
            sample_rate=int(sample_rate),
            sample_count=int(data.size),
            sample_sha256=_sample_hash(data),
            primary_frequency_hz=None,
            secondary_frequency_hz=None,
            beat_rate_hz=0.0,
            detune_cents=0.0,
            secondary_to_primary_ratio=0.0,
            confidence=0.0,
            close_fundamentals_detected=False,
            unison_detected=False,
            reason="The source is silent and has no detectable fundamental pair.",
        )

    window = np.hanning(centered.size)
    fft_size = 1 << max(14, (4 * centered.size - 1).bit_length())
    magnitudes = np.abs(np.fft.rfft(centered * window, n=fft_size))
    frequencies = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)
    valid = (frequencies >= minimum_frequency_hz) & (frequencies <= maximum_frequency_hz)
    valid_indices = np.flatnonzero(valid)
    if valid_indices.size < 3:
        raise AnalysisError("Frequency search range contains too few FFT bins")

    local_indices = valid_indices[1:-1]
    peaks = local_indices[
        (magnitudes[local_indices] > magnitudes[local_indices - 1])
        & (magnitudes[local_indices] >= magnitudes[local_indices + 1])
    ]
    if peaks.size == 0:
        peaks = np.asarray([valid_indices[int(np.argmax(magnitudes[valid_indices]))]])
    peaks = peaks[np.argsort(magnitudes[peaks], kind="stable")[::-1]]

    primary_index = int(peaks[0])
    primary_magnitude = float(magnitudes[primary_index])
    bin_hz = float(sample_rate / fft_size)
    primary_frequency = _parabolic_frequency(magnitudes, primary_index, bin_hz)

    secondary_index: int | None = None
    secondary_ratio = 0.0
    secondary_frequency: float | None = None
    for candidate in peaks[1:]:
        candidate_frequency = _parabolic_frequency(magnitudes, int(candidate), bin_hz)
        cents = abs(1200.0 * math.log2(candidate_frequency / primary_frequency))
        ratio = 0.0 if primary_magnitude <= 0.0 else float(
            magnitudes[int(candidate)] / primary_magnitude
        )
        if cents <= maximum_detune_cents and ratio >= minimum_secondary_ratio:
            secondary_index = int(candidate)
            secondary_ratio = float(min(1.0, max(0.0, ratio)))
            secondary_frequency = candidate_frequency
            break

    if secondary_index is None or secondary_frequency is None:
        return BeatingAnalysis(
            schema_version=1,
            sample_rate=int(sample_rate),
            sample_count=int(data.size),
            sample_sha256=_sample_hash(data),
            primary_frequency_hz=primary_frequency,
            secondary_frequency_hz=None,
            beat_rate_hz=0.0,
            detune_cents=0.0,
            secondary_to_primary_ratio=0.0,
            confidence=0.0,
            close_fundamentals_detected=False,
            unison_detected=False,
            reason="No secondary peak satisfies the close-frequency and level gates.",
        )

    low = min(primary_frequency, secondary_frequency)
    high = max(primary_frequency, secondary_frequency)
    beat_rate = float(high - low)
    detune = float(abs(1200.0 * math.log2(high / low)))
    closeness = float(max(0.0, 1.0 - detune / maximum_detune_cents))
    confidence = float(min(1.0, secondary_ratio * 0.6 + closeness * 0.4))
    unison = bool(detune <= unison_cents)
    reason = (
        "Two close spectral peaks satisfy the detune and relative-level gates; "
        "their frequency difference is the estimated beat rate."
    )

    return BeatingAnalysis(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=_sample_hash(data),
        primary_frequency_hz=low,
        secondary_frequency_hz=high,
        beat_rate_hz=beat_rate,
        detune_cents=detune,
        secondary_to_primary_ratio=secondary_ratio,
        confidence=confidence,
        close_fundamentals_detected=True,
        unison_detected=unison,
        reason=reason,
    )
