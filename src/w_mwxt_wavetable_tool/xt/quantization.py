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


XT_SAMPLE_MIN = -127
XT_SAMPLE_MAX = 127
_EPSILON = 1.0e-12
FloatArray = npt.NDArray[np.float64]


class QuantizationAlgorithm(str, Enum):
    NEAREST = "nearest"
    ERROR_FEEDBACK = "error_feedback"


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


def _validate(samples: Sequence[float]) -> FloatArray:
    array = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if array.ndim != 1 or array.size < 2:
        raise AnalysisError("quantization input must contain at least two samples")
    if not np.all(np.isfinite(array)):
        raise AnalysisError("quantization input contains NaN or infinite values")
    if float(np.max(np.abs(array))) > 1.0 + _EPSILON:
        raise AnalysisError("quantization input exceeds normalized range [-1, 1]")
    return array


def _round_half_away(values: FloatArray) -> npt.NDArray[np.int64]:
    magnitude = np.floor(np.abs(values) + 0.5)
    return np.asarray(np.copysign(magnitude, values), dtype=np.int64)


def dequantize_xt_samples(samples: Sequence[int]) -> tuple[float, ...]:
    values = np.asarray(tuple(int(value) for value in samples), dtype=np.int64)
    if values.ndim != 1 or values.size < 2:
        raise AnalysisError("XT quantized samples must contain at least two values")
    if np.any(values < XT_SAMPLE_MIN) or np.any(values > XT_SAMPLE_MAX):
        raise AnalysisError("XT quantized samples must stay in -127..127")
    return tuple(float(value) / XT_SAMPLE_MAX for value in values)


def _quantize_nearest(samples: FloatArray) -> tuple[int, ...]:
    values = _round_half_away(samples * XT_SAMPLE_MAX)
    if np.any(values < XT_SAMPLE_MIN) or np.any(values > XT_SAMPLE_MAX):
        raise AnalysisError("nearest quantization overflowed the XT safe range")
    return tuple(int(value) for value in values)


def _quantize_error_feedback(samples: FloatArray) -> tuple[int, ...]:
    output: list[int] = []
    error = 0.0
    for sample in samples:
        shaped = float(sample) + 0.75 * error
        if abs(shaped) > 1.0:
            # Do not hide a range violation introduced by feedback. Disable feedback
            # for this sample and quantize the already validated source value.
            shaped = float(sample)
            error = 0.0
        quantized = int(_round_half_away(np.asarray([shaped * XT_SAMPLE_MAX]))[0])
        if quantized < XT_SAMPLE_MIN or quantized > XT_SAMPLE_MAX:
            raise AnalysisError("error-feedback quantization overflowed the XT safe range")
        reconstructed = quantized / XT_SAMPLE_MAX
        error = shaped - reconstructed
        output.append(quantized)
    return tuple(output)


def _correlation(left: FloatArray, right: FloatArray) -> float:
    left_centered = left - float(np.mean(left, dtype=np.float64))
    right_centered = right - float(np.mean(right, dtype=np.float64))
    denominator = float(np.linalg.norm(left_centered) * np.linalg.norm(right_centered))
    if denominator <= _EPSILON:
        return 1.0 if np.allclose(left, right, atol=1.0e-12, rtol=0.0) else 0.0
    return float(np.clip(np.dot(left_centered, right_centered) / denominator, -1.0, 1.0))


def _normalized_magnitude(samples: FloatArray) -> FloatArray:
    magnitude = np.abs(np.fft.rfft(samples))[1:]
    norm = float(np.linalg.norm(magnitude))
    if norm <= _EPSILON:
        return np.zeros_like(magnitude, dtype=np.float64)
    return np.asarray(magnitude / norm, dtype=np.float64)


def _band_ratios(samples: FloatArray) -> tuple[float, float, float]:
    power = np.square(np.abs(np.fft.rfft(samples))[1:])
    total = float(np.sum(power, dtype=np.float64))
    if total <= _EPSILON:
        return 0.0, 0.0, 0.0
    low_stop = min(4, power.size)
    mid_stop = min(16, power.size)
    low = float(np.sum(power[:low_stop], dtype=np.float64) / total)
    mid = float(np.sum(power[low_stop:mid_stop], dtype=np.float64) / total)
    high = max(0.0, 1.0 - low - mid)
    return low, mid, high


@dataclass(frozen=True, slots=True)
class QuantizationMetrics:
    rmse: float
    normalized_rmse: float
    maximum_absolute_error: float
    mean_error: float
    correlation: float
    spectral_rmse: float
    h1_error: float
    h2_error: float
    h3_error: float
    low_band_error: float
    mid_band_error: float
    high_band_error: float
    dc_error: float
    extreme_count: int
    forbidden_negative_128_count: int
    quality_score: float

    def __post_init__(self) -> None:
        for name, value in self.to_dict().items():
            if name in {"extreme_count", "forbidden_negative_128_count"}:
                if int(value) < 0:
                    raise AnalysisError(f"{name} must not be negative")
                continue
            if not math.isfinite(float(value)):
                raise AnalysisError(f"quantization metric {name} must be finite")
        if not -1.0 <= self.correlation <= 1.0:
            raise AnalysisError("correlation must be between -1 and 1")
        for name in (
            "normalized_rmse",
            "spectral_rmse",
            "h1_error",
            "h2_error",
            "h3_error",
            "low_band_error",
            "mid_band_error",
            "high_band_error",
            "dc_error",
            "quality_score",
        ):
            if not 0.0 <= float(getattr(self, name)) <= 1.0:
                raise AnalysisError(f"{name} must be a bounded ratio")
        if self.forbidden_negative_128_count != 0:
            raise AnalysisError("-128 is forbidden in generated XT samples")

    def to_dict(self) -> dict[str, float | int]:
        return {
            "rmse": self.rmse,
            "normalized_rmse": self.normalized_rmse,
            "maximum_absolute_error": self.maximum_absolute_error,
            "mean_error": self.mean_error,
            "correlation": self.correlation,
            "spectral_rmse": self.spectral_rmse,
            "h1_error": self.h1_error,
            "h2_error": self.h2_error,
            "h3_error": self.h3_error,
            "low_band_error": self.low_band_error,
            "mid_band_error": self.mid_band_error,
            "high_band_error": self.high_band_error,
            "dc_error": self.dc_error,
            "extreme_count": self.extreme_count,
            "forbidden_negative_128_count": self.forbidden_negative_128_count,
            "quality_score": self.quality_score,
        }


@dataclass(frozen=True, slots=True)
class XtQuantizedWave:
    schema_version: int
    algorithm: QuantizationAlgorithm
    source_samples_sha256: str
    quantized_samples: tuple[int, ...]
    reconstructed_samples: tuple[float, ...]
    metrics: QuantizationMetrics

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported XT-quantization schema version")
        if len(self.source_samples_sha256) != 64:
            raise AnalysisError("source_samples_sha256 must be a SHA-256 digest")
        if len(self.quantized_samples) != len(self.reconstructed_samples):
            raise AnalysisError("quantized and reconstructed lengths are inconsistent")
        if any(value < XT_SAMPLE_MIN or value > XT_SAMPLE_MAX for value in self.quantized_samples):
            raise AnalysisError("quantized samples exceed the XT safe range")
        expected = dequantize_xt_samples(self.quantized_samples)
        if not np.allclose(expected, self.reconstructed_samples, atol=0.0, rtol=0.0):
            raise AnalysisError("reconstructed_samples do not match quantized_samples")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "algorithm": self.algorithm.value,
            "source_samples_sha256": self.source_samples_sha256,
            "quantized_samples": list(self.quantized_samples),
            "reconstructed_samples": list(self.reconstructed_samples),
            "metrics": self.metrics.to_dict(),
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class QuantizationComparison:
    schema_version: int
    source_samples_sha256: str
    candidates: tuple[XtQuantizedWave, ...]
    selected_algorithm: QuantizationAlgorithm
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported quantization-comparison schema version")
        if tuple(item.algorithm for item in self.candidates) != tuple(QuantizationAlgorithm):
            raise AnalysisError("candidates must contain every quantization algorithm")
        if any(item.source_samples_sha256 != self.source_samples_sha256 for item in self.candidates):
            raise AnalysisError("candidate source hashes are inconsistent")
        selected = min(
            self.candidates,
            key=lambda item: (item.metrics.quality_score, list(QuantizationAlgorithm).index(item.algorithm)),
        )
        if selected.algorithm is not self.selected_algorithm:
            raise AnalysisError("selected_algorithm is inconsistent")
        if not self.reason or self.reason.strip() != self.reason:
            raise AnalysisError("reason must be normalized")

    @property
    def selected(self) -> XtQuantizedWave:
        return next(item for item in self.candidates if item.algorithm is self.selected_algorithm)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_samples_sha256": self.source_samples_sha256,
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


def _measure(source: FloatArray, reconstructed: FloatArray, quantized: tuple[int, ...]) -> QuantizationMetrics:
    difference = reconstructed - source
    rmse = float(np.sqrt(np.mean(np.square(difference), dtype=np.float64)))
    source_rms = float(np.sqrt(np.mean(np.square(source), dtype=np.float64)))
    nrmse = min(1.0, rmse / max(source_rms, _EPSILON))
    maximum = float(np.max(np.abs(difference)))
    mean_error = float(np.mean(difference, dtype=np.float64))
    correlation = _correlation(source, reconstructed)
    source_spectrum = _normalized_magnitude(source)
    reconstructed_spectrum = _normalized_magnitude(reconstructed)
    spectral_rmse = min(
        1.0,
        float(np.sqrt(np.mean(np.square(reconstructed_spectrum - source_spectrum), dtype=np.float64))),
    )

    def harmonic_error(index: int) -> float:
        if index - 1 >= source_spectrum.size:
            return 0.0
        return min(1.0, float(abs(reconstructed_spectrum[index - 1] - source_spectrum[index - 1])))

    source_bands = _band_ratios(source)
    reconstructed_bands = _band_ratios(reconstructed)
    band_errors = tuple(min(1.0, abs(left - right)) for left, right in zip(source_bands, reconstructed_bands))
    dc_error = min(1.0, abs(float(np.mean(reconstructed)) - float(np.mean(source))) / 2.0)
    extreme_count = sum(abs(value) == XT_SAMPLE_MAX for value in quantized)
    forbidden_count = sum(value == -128 for value in quantized)
    quality = min(
        1.0,
        0.35 * nrmse
        + 0.25 * spectral_rmse
        + 0.10 * harmonic_error(1)
        + 0.07 * harmonic_error(2)
        + 0.05 * harmonic_error(3)
        + 0.12 * sum(band_errors) / 3.0
        + 0.06 * dc_error,
    )
    return QuantizationMetrics(
        rmse=rmse,
        normalized_rmse=nrmse,
        maximum_absolute_error=maximum,
        mean_error=mean_error,
        correlation=correlation,
        spectral_rmse=spectral_rmse,
        h1_error=harmonic_error(1),
        h2_error=harmonic_error(2),
        h3_error=harmonic_error(3),
        low_band_error=band_errors[0],
        mid_band_error=band_errors[1],
        high_band_error=band_errors[2],
        dc_error=dc_error,
        extreme_count=extreme_count,
        forbidden_negative_128_count=forbidden_count,
        quality_score=quality,
    )


def quantize_xt_samples(
    samples: Sequence[float],
    *,
    algorithm: QuantizationAlgorithm = QuantizationAlgorithm.NEAREST,
) -> XtQuantizedWave:
    source = _validate(samples)
    selected = QuantizationAlgorithm(algorithm)
    quantized = (
        _quantize_nearest(source)
        if selected is QuantizationAlgorithm.NEAREST
        else _quantize_error_feedback(source)
    )
    reconstructed = np.asarray(dequantize_xt_samples(quantized), dtype=np.float64)
    return XtQuantizedWave(
        schema_version=1,
        algorithm=selected,
        source_samples_sha256=_sample_hash(source),
        quantized_samples=quantized,
        reconstructed_samples=tuple(float(value) for value in reconstructed),
        metrics=_measure(source, reconstructed, quantized),
    )


def compare_quantization_algorithms(samples: Sequence[float]) -> QuantizationComparison:
    candidates = tuple(quantize_xt_samples(samples, algorithm=algorithm) for algorithm in QuantizationAlgorithm)
    selected = min(
        candidates,
        key=lambda item: (item.metrics.quality_score, list(QuantizationAlgorithm).index(item.algorithm)),
    )
    return QuantizationComparison(
        schema_version=1,
        source_samples_sha256=candidates[0].source_samples_sha256,
        candidates=candidates,
        selected_algorithm=selected.algorithm,
        reason=(
            "Nearest and deterministic error-feedback quantization were compared with "
            "time, harmonic, spectral, band, and DC errors in the strict -127..127 range."
        ),
    )
