from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any, Iterable, Sequence

import numpy as np
import numpy.typing as npt

from ..errors import AnalysisError
from .quantization import (
    QuantizationAlgorithm,
    XtQuantizedWave,
    quantize_xt_samples,
)
from .resampling import (
    NormalizationPolicy,
    ResampledWave,
    ResamplingAlgorithm,
    resample_periodic_wave,
)


SOURCE_SAMPLE_COUNT = 128
STORED_SAMPLE_COUNT = 64
_EPSILON = 1.0e-12
FloatArray = npt.NDArray[np.float64]


class WaveTransform(str, Enum):
    IDENTITY = "identity"
    POLARITY_INVERTED = "polarity_inverted"
    TIME_REVERSED = "time_reversed"
    TIME_REVERSED_POLARITY = "time_reversed_polarity"
    MIRRORED = "mirrored"
    MIRRORED_POLARITY = "mirrored_polarity"


class HalfWaveMethod(str, Enum):
    PAIRWISE_LEAST_SQUARES = "pairwise_least_squares"
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"
    RESAMPLED_WINDOWED_SINC = "resampled_windowed_sinc"
    RESAMPLED_FOURIER = "resampled_fourier"
    RESAMPLED_LINEAR = "resampled_linear"


_RESAMPLING_BY_METHOD = {
    HalfWaveMethod.RESAMPLED_WINDOWED_SINC: ResamplingAlgorithm.WINDOWED_SINC,
    HalfWaveMethod.RESAMPLED_FOURIER: ResamplingAlgorithm.FOURIER,
    HalfWaveMethod.RESAMPLED_LINEAR: ResamplingAlgorithm.LINEAR,
}


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


def _validate_source(samples: Sequence[float]) -> FloatArray:
    array = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if array.shape != (SOURCE_SAMPLE_COUNT,):
        raise AnalysisError("symmetry optimization requires exactly 128 source samples")
    if not np.all(np.isfinite(array)):
        raise AnalysisError("source wave contains NaN or infinite values")
    if float(np.max(np.abs(array))) > 1.0 + _EPSILON:
        raise AnalysisError("source wave exceeds normalized range [-1, 1]")
    if float(np.max(np.abs(array))) <= _EPSILON:
        raise AnalysisError("silent source waves are not valid symmetry candidates")
    return array


def _mirror(samples: FloatArray) -> FloatArray:
    return np.concatenate((samples[:1], samples[:0:-1])).astype(np.float64, copy=False)


def apply_wave_transform(
    samples: Sequence[float],
    transform: WaveTransform,
    phase_rotation_samples: int,
) -> tuple[float, ...]:
    source = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if source.shape != (SOURCE_SAMPLE_COUNT,):
        raise AnalysisError("wave transform requires 128 samples")
    phase = int(phase_rotation_samples)
    if not 0 <= phase < SOURCE_SAMPLE_COUNT:
        raise AnalysisError("phase_rotation_samples must be in 0..127")
    selected = WaveTransform(transform)
    result = source.copy()
    if selected in {WaveTransform.TIME_REVERSED, WaveTransform.TIME_REVERSED_POLARITY}:
        result = result[::-1]
    elif selected in {WaveTransform.MIRRORED, WaveTransform.MIRRORED_POLARITY}:
        result = _mirror(result)
    if selected in {
        WaveTransform.POLARITY_INVERTED,
        WaveTransform.TIME_REVERSED_POLARITY,
        WaveTransform.MIRRORED_POLARITY,
    }:
        result = -result
    result = np.roll(result, -phase)
    return tuple(float(value) for value in result)


def invert_wave_transform(
    samples: Sequence[float],
    transform: WaveTransform,
    phase_rotation_samples: int,
) -> tuple[float, ...]:
    result = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if result.shape != (SOURCE_SAMPLE_COUNT,):
        raise AnalysisError("inverse wave transform requires 128 samples")
    selected = WaveTransform(transform)
    result = np.roll(result, int(phase_rotation_samples))
    if selected in {
        WaveTransform.POLARITY_INVERTED,
        WaveTransform.TIME_REVERSED_POLARITY,
        WaveTransform.MIRRORED_POLARITY,
    }:
        result = -result
    if selected in {WaveTransform.TIME_REVERSED, WaveTransform.TIME_REVERSED_POLARITY}:
        result = result[::-1]
    elif selected in {WaveTransform.MIRRORED, WaveTransform.MIRRORED_POLARITY}:
        result = _mirror(result)
    return tuple(float(value) for value in result)


def reconstruct_xt_float(stored_samples: Sequence[float]) -> tuple[float, ...]:
    stored = tuple(float(value) for value in stored_samples)
    if len(stored) != STORED_SAMPLE_COUNT:
        raise AnalysisError("stored XT float wave must contain exactly 64 samples")
    if any(not math.isfinite(value) or abs(value) > 1.0 + _EPSILON for value in stored):
        raise AnalysisError("stored XT float samples must be finite and normalized")
    return stored + tuple(-value for value in reversed(stored))


def _half_wave(
    transformed: FloatArray,
    method: HalfWaveMethod,
    normalization: NormalizationPolicy,
) -> tuple[FloatArray, ResampledWave | None]:
    selected = HalfWaveMethod(method)
    if selected is HalfWaveMethod.PAIRWISE_LEAST_SQUARES:
        return (
            np.asarray(
                0.5 * (transformed[:STORED_SAMPLE_COUNT] - transformed[::-1][:STORED_SAMPLE_COUNT]),
                dtype=np.float64,
            ),
            None,
        )
    if selected is HalfWaveMethod.FIRST_HALF:
        return np.asarray(transformed[:STORED_SAMPLE_COUNT], dtype=np.float64), None
    if selected is HalfWaveMethod.SECOND_HALF:
        return np.asarray(-transformed[::-1][:STORED_SAMPLE_COUNT], dtype=np.float64), None
    resampled = resample_periodic_wave(
        transformed,
        STORED_SAMPLE_COUNT,
        algorithm=_RESAMPLING_BY_METHOD[selected],
        normalization=normalization,
    )
    return np.asarray(resampled.samples, dtype=np.float64), resampled


@dataclass(frozen=True, slots=True)
class SymmetryTreatment:
    transform: WaveTransform
    phase_rotation_samples: int
    half_wave_method: HalfWaveMethod
    quantization_algorithm: QuantizationAlgorithm
    normalization: NormalizationPolicy

    def __post_init__(self) -> None:
        object.__setattr__(self, "transform", WaveTransform(self.transform))
        object.__setattr__(self, "half_wave_method", HalfWaveMethod(self.half_wave_method))
        object.__setattr__(
            self,
            "quantization_algorithm",
            QuantizationAlgorithm(self.quantization_algorithm),
        )
        object.__setattr__(self, "normalization", NormalizationPolicy(self.normalization))
        if not 0 <= self.phase_rotation_samples < SOURCE_SAMPLE_COUNT:
            raise AnalysisError("phase_rotation_samples must be in 0..127")

    @property
    def treatment_id(self) -> str:
        return (
            f"{self.transform.value}:p{self.phase_rotation_samples:03d}:"
            f"{self.half_wave_method.value}:{self.quantization_algorithm.value}:"
            f"{self.normalization.value}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "transform": self.transform.value,
            "phase_rotation_samples": self.phase_rotation_samples,
            "half_wave_method": self.half_wave_method.value,
            "quantization_algorithm": self.quantization_algorithm.value,
            "normalization": self.normalization.value,
            "treatment_id": self.treatment_id,
        }


@dataclass(frozen=True, slots=True)
class SymmetryCandidate:
    schema_version: int
    source_samples_sha256: str
    treatment: SymmetryTreatment
    stored_float_samples: tuple[float, ...]
    quantization: XtQuantizedWave
    reconstructed_transformed: tuple[float, ...]
    reconstructed_aligned: tuple[float, ...]
    resampling: ResampledWave | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported symmetry-candidate schema version")
        if len(self.source_samples_sha256) != 64:
            raise AnalysisError("source_samples_sha256 must be a SHA-256 digest")
        if len(self.stored_float_samples) != STORED_SAMPLE_COUNT:
            raise AnalysisError("stored_float_samples must contain 64 values")
        if len(self.reconstructed_transformed) != SOURCE_SAMPLE_COUNT:
            raise AnalysisError("reconstructed_transformed must contain 128 values")
        if len(self.reconstructed_aligned) != SOURCE_SAMPLE_COUNT:
            raise AnalysisError("reconstructed_aligned must contain 128 values")
        expected = reconstruct_xt_float(self.quantization.reconstructed_samples)
        if not np.allclose(expected, self.reconstructed_transformed, atol=0.0, rtol=0.0):
            raise AnalysisError("reconstructed_transformed does not match quantized samples")
        if self.resampling is None and self.treatment.half_wave_method in _RESAMPLING_BY_METHOD:
            raise AnalysisError("resampled methods require resampling evidence")
        if self.resampling is not None:
            expected_algorithm = _RESAMPLING_BY_METHOD.get(self.treatment.half_wave_method)
            if expected_algorithm is not self.resampling.algorithm:
                raise AnalysisError("resampling evidence does not match the half-wave method")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_samples_sha256": self.source_samples_sha256,
            "treatment": self.treatment.to_dict(),
            "stored_float_samples": list(self.stored_float_samples),
            "quantization": self.quantization.to_dict(),
            "reconstructed_transformed": list(self.reconstructed_transformed),
            "reconstructed_aligned": list(self.reconstructed_aligned),
            "resampling": None if self.resampling is None else self.resampling.to_dict(),
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def build_symmetry_candidate(
    samples: Sequence[float],
    treatment: SymmetryTreatment,
) -> SymmetryCandidate:
    source = _validate_source(samples)
    transformed = np.asarray(
        apply_wave_transform(source, treatment.transform, treatment.phase_rotation_samples),
        dtype=np.float64,
    )
    stored_float, resampling = _half_wave(
        transformed,
        treatment.half_wave_method,
        treatment.normalization,
    )
    peak = float(np.max(np.abs(stored_float)))
    if peak > 1.0 + _EPSILON:
        stored_float = np.asarray(stored_float / peak, dtype=np.float64)
    quantization = quantize_xt_samples(
        stored_float,
        algorithm=treatment.quantization_algorithm,
    )
    reconstructed_transformed = reconstruct_xt_float(quantization.reconstructed_samples)
    reconstructed_aligned = invert_wave_transform(
        reconstructed_transformed,
        treatment.transform,
        treatment.phase_rotation_samples,
    )
    return SymmetryCandidate(
        schema_version=1,
        source_samples_sha256=_sample_hash(source),
        treatment=treatment,
        stored_float_samples=tuple(float(value) for value in stored_float),
        quantization=quantization,
        reconstructed_transformed=reconstructed_transformed,
        reconstructed_aligned=reconstructed_aligned,
        resampling=resampling,
    )


def generate_symmetry_candidates(
    samples: Sequence[float],
    *,
    phases: Iterable[int] = range(SOURCE_SAMPLE_COUNT),
    transforms: Iterable[WaveTransform] = tuple(WaveTransform),
    half_wave_methods: Iterable[HalfWaveMethod] = tuple(HalfWaveMethod),
    quantization_algorithms: Iterable[QuantizationAlgorithm] = tuple(QuantizationAlgorithm),
    normalization: NormalizationPolicy = NormalizationPolicy.NONE,
) -> tuple[SymmetryCandidate, ...]:
    source = _validate_source(samples)
    phase_values = tuple(int(value) for value in phases)
    if not phase_values or len(set(phase_values)) != len(phase_values):
        raise AnalysisError("phases must be a non-empty unique sequence")
    if any(value < 0 or value >= SOURCE_SAMPLE_COUNT for value in phase_values):
        raise AnalysisError("phases must stay in 0..127")
    transform_values = tuple(WaveTransform(value) for value in transforms)
    method_values = tuple(HalfWaveMethod(value) for value in half_wave_methods)
    quantization_values = tuple(QuantizationAlgorithm(value) for value in quantization_algorithms)
    if not transform_values or not method_values or not quantization_values:
        raise AnalysisError("candidate dimensions must not be empty")
    candidates: list[SymmetryCandidate] = []
    seen: set[str] = set()
    for transform in transform_values:
        for phase in phase_values:
            for method in method_values:
                for quantization in quantization_values:
                    treatment = SymmetryTreatment(
                        transform=transform,
                        phase_rotation_samples=phase,
                        half_wave_method=method,
                        quantization_algorithm=quantization,
                        normalization=NormalizationPolicy(normalization),
                    )
                    if treatment.treatment_id in seen:
                        raise AnalysisError("duplicate symmetry treatment generated")
                    seen.add(treatment.treatment_id)
                    candidates.append(build_symmetry_candidate(source, treatment))
    return tuple(candidates)
