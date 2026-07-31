
from __future__ import annotations

import json

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import NoiseClass, analyze_noise, analyze_pitch_periodicity
from w_mwxt_wavetable_tool.errors import AnalysisError

SAMPLE_RATE = 48000


def _sine(frequency: float = 440.0, seconds: float = 1.0, amplitude: float = 0.7) -> np.ndarray:
    time = np.arange(int(SAMPLE_RATE * seconds), dtype=np.float64) / SAMPLE_RATE
    return amplitude * np.sin(2.0 * np.pi * frequency * time)


def _analyze(samples: np.ndarray, **kwargs):
    return analyze_noise(
        samples,
        SAMPLE_RATE,
        frame_size=4096,
        hop_size=1024,
        minimum_frequency_hz=80.0,
        maximum_frequency_hz=1200.0,
        confidence_threshold=0.50,
        **kwargs,
    )


def test_silence_is_classified_silent() -> None:
    result = _analyze(np.zeros(SAMPLE_RATE, dtype=np.float64))
    assert result.noise_class is NoiseClass.SILENT
    assert result.snr_db is None
    assert result.signal_rms == 0.0


def test_clean_sine_uses_periodic_residual() -> None:
    result = _analyze(_sine())
    assert result.periodic_residual_frame_count == result.frame_count
    assert result.noise_floor_rms < result.signal_rms * 0.02
    assert result.noise_class in {NoiseClass.PRISTINE, NoiseClass.SIGNAL_DOMINATED}


def test_tone_plus_seeded_noise_has_finite_snr() -> None:
    rng = np.random.default_rng(1234)
    samples = _sine() + rng.normal(0.0, 0.01, SAMPLE_RATE)
    result = _analyze(samples)
    assert result.snr_db is not None
    assert 20.0 < result.snr_db < 50.0
    assert result.noise_floor_rms > 0.0


def test_seeded_white_noise_is_noise_dominated() -> None:
    samples = np.random.default_rng(7).normal(0.0, 0.1, SAMPLE_RATE)
    result = _analyze(samples)
    assert result.noise_class is NoiseClass.NOISE_DOMINATED
    assert result.snr_db is not None and result.snr_db < 6.0


def test_lower_quantile_is_recorded() -> None:
    result = _analyze(_sine(), lower_quantile=0.35)
    assert result.lower_quantile == 0.35
    assert result.lower_quantile_frame_count == int(np.ceil(result.frame_count * 0.35))


def test_noise_stationarity_is_bounded() -> None:
    result = _analyze(_sine() + np.random.default_rng(8).normal(0.0, 0.005, SAMPLE_RATE))
    assert 0.0 <= result.noise_stationarity <= 1.0


def test_precomputed_pitch_is_reused() -> None:
    samples = _sine(330.0)
    pitch = analyze_pitch_periodicity(
        samples,
        SAMPLE_RATE,
        frame_size=4096,
        hop_size=1024,
        minimum_frequency_hz=80.0,
        maximum_frequency_hz=1200.0,
        confidence_threshold=0.50,
    )
    first = analyze_noise(samples, SAMPLE_RATE, pitch_periodicity=pitch)
    second = analyze_noise(samples, SAMPLE_RATE, pitch_periodicity=pitch)
    assert first.to_dict() == second.to_dict()


def test_mismatched_pitch_is_rejected() -> None:
    first = _sine(440.0)
    second = _sine(441.0)
    pitch = analyze_pitch_periodicity(first, SAMPLE_RATE)
    with pytest.raises(AnalysisError):
        analyze_noise(second, SAMPLE_RATE, pitch_periodicity=pitch)


def test_source_samples_are_not_modified() -> None:
    samples = _sine()
    before = samples.copy()
    _analyze(samples)
    assert np.array_equal(samples, before)


def test_hash_changes_when_signal_changes() -> None:
    first = _analyze(_sine())
    changed = _sine()
    changed[0] = 0.1
    second = _analyze(changed)
    assert first.sample_sha256 != second.sample_sha256
    assert first.analysis_sha256 != second.analysis_sha256


def test_json_contains_no_nan_or_infinity() -> None:
    rendered = json.dumps(_analyze(np.zeros(4096)).to_dict(), allow_nan=False)
    assert "NaN" not in rendered and "Infinity" not in rendered


@pytest.mark.parametrize("value", [0.0, -0.1, 1.1, float("nan")])
def test_invalid_lower_quantile_is_rejected(value: float) -> None:
    with pytest.raises(AnalysisError):
        _analyze(_sine(), lower_quantile=value)


def test_non_finite_samples_are_rejected() -> None:
    samples = _sine()
    samples[10] = np.inf
    with pytest.raises(AnalysisError):
        _analyze(samples)


def test_multichannel_samples_are_rejected() -> None:
    samples = np.column_stack([_sine(), _sine()])
    with pytest.raises(AnalysisError):
        _analyze(samples)
