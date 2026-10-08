from __future__ import annotations

import math

import numpy as np
import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.xt.resampling import (
    NormalizationPolicy,
    ResamplingAlgorithm,
    compare_resampling_algorithms,
    resample_periodic_wave,
)


def wave(*harmonics: tuple[int, float]) -> np.ndarray:
    phase = 2.0 * np.pi * np.arange(128, dtype=np.float64) / 128.0
    result = sum(amplitude * np.sin(number * phase) for number, amplitude in harmonics)
    return result / max(1.0, float(np.max(np.abs(result))))


@pytest.mark.parametrize("algorithm", tuple(ResamplingAlgorithm))
def test_resamplers_are_deterministic_and_bounded(algorithm: ResamplingAlgorithm) -> None:
    source = wave((1, 0.8), (5, 0.2), (27, 0.1))
    left = resample_periodic_wave(source, 64, algorithm=algorithm)
    right = resample_periodic_wave(source, 64, algorithm=algorithm)
    assert left.to_dict() == right.to_dict()
    assert len(left.samples) == 64
    assert max(abs(value) for value in left.samples) <= 1.0 + 1e-12
    assert 0.0 <= left.metrics.quality_score <= 1.0


def test_antialiasing_algorithms_reduce_high_harmonic_contamination() -> None:
    source = wave((1, 0.8), (45, 0.4))
    sinc = resample_periodic_wave(source, 64, algorithm=ResamplingAlgorithm.WINDOWED_SINC)
    fourier = resample_periodic_wave(source, 64, algorithm=ResamplingAlgorithm.FOURIER)
    linear = resample_periodic_wave(source, 64, algorithm=ResamplingAlgorithm.LINEAR)
    assert sinc.metrics.aliasing_risk < linear.metrics.aliasing_risk
    assert fourier.metrics.aliasing_risk < linear.metrics.aliasing_risk
    assert not linear.anti_alias
    assert sinc.anti_alias and fourier.anti_alias


@pytest.mark.parametrize("policy", tuple(NormalizationPolicy))
def test_normalization_policies_are_explicit(policy: NormalizationPolicy) -> None:
    source = 0.75 * wave((1, 1.0), (3, 0.15))
    result = resample_periodic_wave(
        source,
        64,
        algorithm=ResamplingAlgorithm.WINDOWED_SINC,
        normalization=policy,
    )
    assert result.normalization is policy
    assert result.metrics.applied_scale > 0.0
    assert result.metrics.extreme_count >= 0


def test_bass_protect_preserves_fundamental_without_clipping() -> None:
    source = 0.95 * wave((1, 1.0), (2, 0.2), (20, 0.05))
    result = resample_periodic_wave(
        source,
        64,
        algorithm=ResamplingAlgorithm.WINDOWED_SINC,
        normalization=NormalizationPolicy.BASS_PROTECT,
    )
    assert math.isclose(result.metrics.fundamental_amplitude_ratio, 1.0, abs_tol=0.03)
    assert result.metrics.target_peak <= 1.0 + 1e-12


def test_algorithm_comparison_contains_all_candidates_and_selects_minimum() -> None:
    result = compare_resampling_algorithms(wave((1, 0.8), (45, 0.4)), 64)
    assert tuple(item.algorithm for item in result.candidates) == tuple(ResamplingAlgorithm)
    assert result.selected.metrics.quality_score == min(item.metrics.quality_score for item in result.candidates)
    assert len(result.analysis_sha256) == 64


@pytest.mark.parametrize("bad", [[0.0], [0.0, float("nan")], [0.0, 1.1]])
def test_resampling_rejects_invalid_input(bad: list[float]) -> None:
    with pytest.raises(AnalysisError):
        resample_periodic_wave(bad, 64)
