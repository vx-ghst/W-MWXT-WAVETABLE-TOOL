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


@dataclass(frozen=True, slots=True)
class ComplexityAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    analysis_start_sample: int
    analysis_sample_count: int
    maximum_samples: int
    active_threshold: float
    spectral_relative_threshold: float
    positive_negative_asymmetry: float
    zero_crossing_density: float
    active_sample_density: float
    spectral_bin_density: float
    spectral_entropy: float
    temporal_difference_density: float
    density_score: float
    complexity_score: float
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported complexity schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if not _hash_is_valid(self.sample_sha256):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if self.analysis_start_sample < 0:
            raise ValueError("analysis_start_sample must not be negative")
        if self.analysis_sample_count <= 0 or self.maximum_samples <= 0:
            raise ValueError("analysis_sample_count and maximum_samples must be positive")
        if self.analysis_sample_count > self.maximum_samples:
            raise ValueError("analysis_sample_count must not exceed maximum_samples")
        if self.analysis_start_sample + self.analysis_sample_count > self.sample_count:
            raise ValueError("analysis slice exceeds the source sample range")
        if _finite(self.active_threshold, name="active_threshold") < 0.0:
            raise ValueError("active_threshold must not be negative")
        if not 0.0 < _finite(
            self.spectral_relative_threshold, name="spectral_relative_threshold"
        ) <= 1.0:
            raise ValueError("spectral_relative_threshold must be in (0, 1]")
        if not -1.0 <= _finite(
            self.positive_negative_asymmetry,
            name="positive_negative_asymmetry",
        ) <= 1.0:
            raise ValueError("positive_negative_asymmetry must be between -1 and 1")
        for name in (
            "zero_crossing_density",
            "active_sample_density",
            "spectral_bin_density",
            "spectral_entropy",
            "temporal_difference_density",
            "density_score",
            "complexity_score",
        ):
            _ratio(getattr(self, name), name=name)
        if not self.reason:
            raise ValueError("reason must not be empty")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "analysis_start_sample": self.analysis_start_sample,
            "analysis_sample_count": self.analysis_sample_count,
            "maximum_samples": self.maximum_samples,
            "active_threshold": self.active_threshold,
            "spectral_relative_threshold": self.spectral_relative_threshold,
            "positive_negative_asymmetry": self.positive_negative_asymmetry,
            "zero_crossing_density": self.zero_crossing_density,
            "active_sample_density": self.active_sample_density,
            "spectral_bin_density": self.spectral_bin_density,
            "spectral_entropy": self.spectral_entropy,
            "temporal_difference_density": self.temporal_difference_density,
            "density_score": self.density_score,
            "complexity_score": self.complexity_score,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def analyze_complexity(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    active_threshold: float = 1e-6,
    spectral_relative_threshold: float = 0.01,
    maximum_samples: int = 131072,
) -> ComplexityAnalysis:
    data = validate_mono_samples(samples)
    if sample_rate <= 0:
        raise AnalysisError("sample_rate must be positive")
    if not math.isfinite(active_threshold) or active_threshold < 0.0:
        raise AnalysisError("active_threshold must be finite and non-negative")
    if not math.isfinite(spectral_relative_threshold) or not 0.0 < spectral_relative_threshold <= 1.0:
        raise AnalysisError(
            "spectral_relative_threshold must be finite, positive, and at most one"
        )
    if maximum_samples <= 0:
        raise AnalysisError("maximum_samples must be positive")

    if data.size > maximum_samples:
        analysis_start = (data.size - maximum_samples) // 2
        analysis_data = data[analysis_start : analysis_start + maximum_samples]
    else:
        analysis_start = 0
        analysis_data = data

    positive_energy = float(
        np.sum(np.square(np.maximum(analysis_data, 0.0)), dtype=np.float64)
    )
    negative_energy = float(
        np.sum(np.square(np.minimum(analysis_data, 0.0)), dtype=np.float64)
    )
    energy_sum = positive_energy + negative_energy
    asymmetry = 0.0 if energy_sum <= 1e-24 else float(
        (positive_energy - negative_energy) / energy_sum
    )

    signs = np.signbit(analysis_data)
    zero_crossing_density = 0.0 if analysis_data.size < 2 else float(
        np.count_nonzero(signs[1:] != signs[:-1]) / (analysis_data.size - 1)
    )
    active_density = float(np.mean(np.abs(analysis_data) > active_threshold))

    window = (
        np.hanning(analysis_data.size)
        if analysis_data.size > 1
        else np.ones(1, dtype=np.float64)
    )
    spectrum = np.abs(np.fft.rfft(analysis_data * window))
    if spectrum.size <= 1 or float(np.max(spectrum)) <= 1e-24:
        spectral_density = 0.0
        spectral_entropy = 0.0
    else:
        spectrum = spectrum[1:]
        maximum = float(np.max(spectrum))
        spectral_density = float(np.mean(spectrum >= maximum * spectral_relative_threshold))
        power = np.square(spectrum)
        total = float(np.sum(power, dtype=np.float64))
        if total <= 1e-24:
            spectral_entropy = 0.0
        else:
            probability = power / total
            positive = probability[probability > 0.0]
            entropy = -float(np.sum(positive * np.log(positive), dtype=np.float64))
            spectral_entropy = float(entropy / math.log(probability.size)) if probability.size > 1 else 0.0

    differences = np.abs(np.diff(analysis_data))
    if differences.size == 0:
        difference_density = 0.0
    else:
        reference = float(np.max(np.abs(analysis_data)))
        threshold = max(1e-12, reference * 0.01)
        difference_density = float(np.mean(differences >= threshold))

    density_score = float(
        min(
            1.0,
            max(
                0.0,
                0.30 * active_density
                + 0.30 * spectral_density
                + 0.20 * zero_crossing_density
                + 0.20 * difference_density,
            ),
        )
    )
    complexity_score = float(
        min(
            1.0,
            max(
                0.0,
                0.40 * spectral_entropy
                + 0.25 * spectral_density
                + 0.20 * difference_density
                + 0.15 * zero_crossing_density,
            ),
        )
    )
    reason = (
        "Complexity combines normalized spectral entropy, occupied-bin density, "
        "temporal differences, and zero-crossing density."
    )

    return ComplexityAnalysis(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=_sample_hash(data),
        analysis_start_sample=int(analysis_start),
        analysis_sample_count=int(analysis_data.size),
        maximum_samples=int(maximum_samples),
        active_threshold=float(active_threshold),
        spectral_relative_threshold=float(spectral_relative_threshold),
        positive_negative_asymmetry=asymmetry,
        zero_crossing_density=zero_crossing_density,
        active_sample_density=active_density,
        spectral_bin_density=spectral_density,
        spectral_entropy=spectral_entropy,
        temporal_difference_density=difference_density,
        density_score=density_score,
        complexity_score=complexity_score,
        reason=reason,
    )
