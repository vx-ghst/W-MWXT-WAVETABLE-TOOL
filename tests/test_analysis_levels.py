from __future__ import annotations

import math

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import analyze_levels
from w_mwxt_wavetable_tool.errors import AnalysisError


def test_silence_has_defined_non_finite_safe_metrics() -> None:
    result = analyze_levels(np.zeros(1024, dtype=np.float64))
    assert result.is_silent
    assert result.peak_absolute == 0.0
    assert result.rms == 0.0
    assert result.peak_dbfs is None
    assert result.rms_dbfs is None
    assert result.crest_factor is None
    assert result.crest_factor_db is None
    assert result.saturation_likelihood == 0.0
    assert not result.saturation_probable


def test_sine_level_metrics_match_known_values() -> None:
    phase = np.arange(4096, dtype=np.float64) * (2.0 * np.pi / 64.0)
    samples = 0.5 * np.sin(phase)
    result = analyze_levels(samples)
    assert result.peak_absolute == pytest.approx(0.5, abs=1e-12)
    assert result.rms == pytest.approx(0.5 / math.sqrt(2.0), rel=1e-12)
    assert result.crest_factor == pytest.approx(math.sqrt(2.0), rel=1e-12)
    assert result.peak_dbfs == pytest.approx(-6.020599913279624, rel=1e-12)
    assert result.rms_dbfs == pytest.approx(-9.030899869919436, rel=1e-12)
    assert not result.is_clipped


def test_dc_offset_is_reported_without_modification() -> None:
    samples = np.full(32, 0.125, dtype=np.float64)
    before = samples.copy()
    result = analyze_levels(samples)
    assert result.dc_offset == pytest.approx(0.125)
    assert result.has_dc_offset
    assert np.array_equal(samples, before)


def test_clipping_and_flat_extremes_produce_explainable_saturation_estimate() -> None:
    samples = np.array([0.0, 1.0, 1.0, 1.0, 0.5, -1.0, -1.0, -1.0, 0.0])
    result = analyze_levels(samples)
    assert result.is_clipped
    assert result.clipped_sample_count == 6
    assert result.flat_extreme_sample_count == 6
    assert result.saturation_probable
    assert result.saturation_likelihood == 1.0
    assert "clipping threshold" in result.saturation_reason


def test_near_clip_sine_is_not_flat_saturation() -> None:
    phase = np.arange(4096, dtype=np.float64) * (2.0 * np.pi / 127.0)
    samples = 0.99 * np.sin(phase)
    result = analyze_levels(samples)
    assert result.near_clip_sample_count > 0
    assert result.flat_extreme_sample_count == 0
    assert not result.saturation_probable


def test_peak_asymmetry_sign_is_explicit() -> None:
    positive = analyze_levels(np.array([-0.25, 0.75], dtype=np.float64))
    negative = analyze_levels(np.array([-0.75, 0.25], dtype=np.float64))
    assert positive.peak_asymmetry == pytest.approx(0.5)
    assert negative.peak_asymmetry == pytest.approx(-0.5)


@pytest.mark.parametrize(
    "samples",
    [
        np.empty(0, dtype=np.float64),
        np.zeros((2, 2), dtype=np.float64),
        np.array([0.0, np.nan]),
        np.array([0.0, np.inf]),
    ],
)
def test_invalid_level_inputs_are_rejected(samples: np.ndarray) -> None:
    with pytest.raises(AnalysisError):
        analyze_levels(samples)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"clipping_threshold": 0.0},
        {"near_clip_threshold": 0.0},
        {"near_clip_threshold": 1.1},
        {"silence_threshold": -1.0},
        {"dc_threshold": -1.0},
        {"flat_derivative_tolerance": -1.0},
        {"saturation_probability_threshold": 1.1},
    ],
)
def test_invalid_level_configuration_is_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(AnalysisError):
        analyze_levels(np.zeros(16), **kwargs)
