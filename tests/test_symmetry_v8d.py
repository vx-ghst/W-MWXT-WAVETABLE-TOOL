from __future__ import annotations

import numpy as np
import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.xt.quantization import QuantizationAlgorithm
from w_mwxt_wavetable_tool.xt.resampling import NormalizationPolicy
from w_mwxt_wavetable_tool.xt.symmetry_candidates import (
    HalfWaveMethod,
    SymmetryTreatment,
    WaveTransform,
    apply_wave_transform,
    build_symmetry_candidate,
    generate_symmetry_candidates,
    invert_wave_transform,
)


def source() -> np.ndarray:
    phase = 2.0 * np.pi * np.arange(128) / 128.0
    return 0.7 * np.sin(phase) + 0.18 * np.sin(4.0 * phase + 0.3) + 0.05


@pytest.mark.parametrize("transform", tuple(WaveTransform))
@pytest.mark.parametrize("phase", [0, 1, 37, 127])
def test_transform_inverse_is_exact(transform: WaveTransform, phase: int) -> None:
    original = source()
    transformed = apply_wave_transform(original, transform, phase)
    restored = invert_wave_transform(transformed, transform, phase)
    assert np.allclose(restored, original, atol=1e-12, rtol=0.0)


@pytest.mark.parametrize("method", tuple(HalfWaveMethod))
def test_every_half_wave_method_builds_valid_xt_candidate(method: HalfWaveMethod) -> None:
    treatment = SymmetryTreatment(
        transform=WaveTransform.IDENTITY,
        phase_rotation_samples=3,
        half_wave_method=method,
        quantization_algorithm=QuantizationAlgorithm.NEAREST,
        normalization=NormalizationPolicy.NONE,
    )
    result = build_symmetry_candidate(source(), treatment)
    assert len(result.stored_float_samples) == 64
    assert len(result.quantization.quantized_samples) == 64
    assert len(result.reconstructed_aligned) == 128
    assert -128 not in result.quantization.quantized_samples
    assert len(result.analysis_sha256) == 64


def test_candidate_cartesian_product_is_complete_and_unique() -> None:
    result = generate_symmetry_candidates(
        source(),
        phases=(0, 1),
        transforms=(WaveTransform.IDENTITY, WaveTransform.POLARITY_INVERTED),
        half_wave_methods=(HalfWaveMethod.PAIRWISE_LEAST_SQUARES, HalfWaveMethod.RESAMPLED_FOURIER),
        quantization_algorithms=tuple(QuantizationAlgorithm),
    )
    assert len(result) == 2 * 2 * 2 * 2
    assert len({item.treatment.treatment_id for item in result}) == len(result)


def test_candidate_generator_rejects_duplicate_phases() -> None:
    with pytest.raises(AnalysisError, match="unique"):
        generate_symmetry_candidates(source(), phases=(0, 0))


def test_treatment_normalizes_serialized_enum_values() -> None:
    treatment = SymmetryTreatment(
        transform="identity",
        phase_rotation_samples=0,
        half_wave_method="pairwise_least_squares",
        quantization_algorithm="nearest",
        normalization="none",
    )
    assert treatment.transform is WaveTransform.IDENTITY
    assert treatment.half_wave_method is HalfWaveMethod.PAIRWISE_LEAST_SQUARES
    assert treatment.quantization_algorithm is QuantizationAlgorithm.NEAREST
    assert treatment.normalization is NormalizationPolicy.NONE
