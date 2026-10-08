from __future__ import annotations

import numpy as np
import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.xt.quantization import (
    QuantizationAlgorithm,
    compare_quantization_algorithms,
    dequantize_xt_samples,
    quantize_xt_samples,
)


def test_exact_extremes_use_safe_minus_127_to_127_range() -> None:
    source = np.linspace(-1.0, 1.0, 64, dtype=np.float64)
    result = quantize_xt_samples(source)
    assert min(result.quantized_samples) == -127
    assert max(result.quantized_samples) == 127
    assert -128 not in result.quantized_samples
    assert result.metrics.forbidden_negative_128_count == 0


@pytest.mark.parametrize("algorithm", tuple(QuantizationAlgorithm))
def test_quantization_is_deterministic_and_roundtrips(algorithm: QuantizationAlgorithm) -> None:
    source = 0.93 * np.sin(2.0 * np.pi * np.arange(64) / 64.0)
    left = quantize_xt_samples(source, algorithm=algorithm)
    right = quantize_xt_samples(source, algorithm=algorithm)
    assert left.to_dict() == right.to_dict()
    assert dequantize_xt_samples(left.quantized_samples) == left.reconstructed_samples
    assert 0.0 <= left.metrics.quality_score <= 1.0


def test_quantization_comparison_selects_lowest_error() -> None:
    source = 0.75 * np.sin(2.0 * np.pi * np.arange(64) / 64.0)
    result = compare_quantization_algorithms(source)
    assert tuple(item.algorithm for item in result.candidates) == tuple(QuantizationAlgorithm)
    assert result.selected.metrics.quality_score == min(item.metrics.quality_score for item in result.candidates)


@pytest.mark.parametrize("bad", [[0.0], [0.0, float("inf")], [0.0, -1.01]])
def test_quantization_rejects_invalid_input(bad: list[float]) -> None:
    with pytest.raises(AnalysisError):
        quantize_xt_samples(bad)


def test_dequantization_rejects_forbidden_negative_128() -> None:
    with pytest.raises(AnalysisError, match="-127..127"):
        dequantize_xt_samples([-128, 0])


def test_error_feedback_keeps_valid_extremes_without_hidden_overflow() -> None:
    source = np.asarray([1.0, -1.0] * 32, dtype=np.float64)
    result = quantize_xt_samples(source, algorithm=QuantizationAlgorithm.ERROR_FEEDBACK)
    assert set(result.quantized_samples) == {-127, 127}
    assert result.metrics.forbidden_negative_128_count == 0
