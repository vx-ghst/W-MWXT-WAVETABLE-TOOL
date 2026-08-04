from __future__ import annotations

import json

import numpy as np

from w_mwxt_wavetable_tool.analysis.complexity import analyze_complexity


def test_noise_is_more_complex_than_a_sine() -> None:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    sine = 0.5 * np.sin(2.0 * np.pi * 220.0 * time)
    noise = np.random.default_rng(123).normal(0.0, 0.25, time.size)
    sine_result = analyze_complexity(sine, sample_rate)
    noise_result = analyze_complexity(noise, sample_rate)
    assert noise_result.complexity_score > sine_result.complexity_score
    assert noise_result.spectral_entropy > sine_result.spectral_entropy
    assert noise_result.spectral_bin_density > sine_result.spectral_bin_density


def test_positive_negative_asymmetry_is_signed() -> None:
    samples = np.array([1.0, 1.0, 0.5, -0.1] * 100, dtype=np.float64)
    result = analyze_complexity(samples, 8000)
    assert result.positive_negative_asymmetry > 0.0


def test_scores_are_bounded_and_json_is_finite() -> None:
    samples = np.random.default_rng(5).normal(0.0, 0.2, 4096)
    result = analyze_complexity(samples, 48000)
    for value in (
        result.zero_crossing_density,
        result.active_sample_density,
        result.spectral_bin_density,
        result.spectral_entropy,
        result.temporal_difference_density,
        result.density_score,
        result.complexity_score,
    ):
        assert 0.0 <= value <= 1.0
    json.dumps(result.to_dict(), allow_nan=False, sort_keys=True)


def test_hash_is_deterministic() -> None:
    samples = np.linspace(-1.0, 1.0, 2048)
    assert analyze_complexity(samples, 44100).analysis_sha256 == analyze_complexity(
        samples, 44100
    ).analysis_sha256


def test_long_source_uses_a_deterministic_bounded_center_slice() -> None:
    samples = np.linspace(-1.0, 1.0, 10000)
    result = analyze_complexity(samples, 48000, maximum_samples=2048)
    assert result.analysis_sample_count == 2048
    assert result.analysis_start_sample == (10000 - 2048) // 2
    assert result.analysis_start_sample + result.analysis_sample_count <= result.sample_count


def test_invalid_maximum_samples_is_rejected() -> None:
    import pytest

    with pytest.raises(Exception, match="maximum_samples"):
        analyze_complexity(np.ones(16), 8000, maximum_samples=0)
