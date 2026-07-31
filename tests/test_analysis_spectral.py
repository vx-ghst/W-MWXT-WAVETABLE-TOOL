from __future__ import annotations

from types import SimpleNamespace
import json

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import analyze_audio_source_spectral, analyze_spectral
from w_mwxt_wavetable_tool.errors import AnalysisError


def sine(frequency: float, *, sample_rate: int = 48000, seconds: float = 1.0, amplitude: float = 0.8) -> np.ndarray:
    t = np.arange(int(sample_rate * seconds), dtype=np.float64) / sample_rate
    return amplitude * np.sin(2.0 * np.pi * frequency * t)


def test_sine_dominant_frequency_matches_fft_bin() -> None:
    result = analyze_spectral(sine(750.0), 48000, frame_size=4096, hop_size=1024)
    assert result.dominant_frequency_hz == pytest.approx(750.0, abs=result.frequency_resolution_hz)


def test_sine_centroid_is_near_frequency() -> None:
    result = analyze_spectral(sine(1000.0), 48000)
    assert result.centroid_hz == pytest.approx(1000.0, abs=20.0)


def test_sine_bandwidth_is_narrow() -> None:
    result = analyze_spectral(sine(1000.0), 48000)
    assert result.bandwidth_hz is not None
    assert result.bandwidth_hz < 100.0


def test_sine_flatness_is_low() -> None:
    result = analyze_spectral(sine(1000.0), 48000)
    assert result.flatness is not None
    assert result.flatness < 0.01


def test_sine_entropy_is_low() -> None:
    result = analyze_spectral(sine(1000.0), 48000)
    assert result.entropy is not None
    assert result.entropy < 0.25


def test_low_frequency_energy_uses_low_band() -> None:
    result = analyze_spectral(sine(100.0), 48000)
    assert result.low_band_ratio is not None
    assert result.low_band_ratio > 0.95


def test_mid_frequency_energy_uses_mid_band() -> None:
    result = analyze_spectral(sine(1000.0), 48000)
    assert result.mid_band_ratio is not None
    assert result.mid_band_ratio > 0.95


def test_high_frequency_energy_uses_high_band() -> None:
    result = analyze_spectral(sine(8000.0), 48000)
    assert result.high_band_ratio is not None
    assert result.high_band_ratio > 0.95


def test_band_ratios_sum_to_one() -> None:
    result = analyze_spectral(sine(1000.0) + 0.5 * sine(8000.0), 48000)
    total = result.low_band_ratio + result.mid_band_ratio + result.high_band_ratio  # type: ignore[operator]
    assert total == pytest.approx(1.0, abs=1e-12)


def test_silence_is_finite_and_inactive() -> None:
    result = analyze_spectral(np.zeros(5000), 48000)
    assert result.active_frame_count == 0
    assert result.centroid_hz is None
    assert result.spectral_stationarity is None
    assert sum(result.normalized_mean_power_spectrum) == 0.0
    json.dumps(result.to_dict(), allow_nan=False)


def test_dc_only_signal_is_removed() -> None:
    result = analyze_spectral(np.full(5000, 0.25), 48000, remove_dc=True)
    assert result.active_frame_count == 0


def test_dc_can_be_preserved_explicitly() -> None:
    result = analyze_spectral(np.full(5000, 0.25), 48000, remove_dc=False)
    assert result.active_frame_count > 0
    assert result.dominant_frequency_hz == 0.0


def test_seeded_white_noise_has_high_flatness() -> None:
    noise = np.random.default_rng(1234).normal(0.0, 0.2, 48000)
    result = analyze_spectral(noise, 48000)
    assert result.flatness is not None
    assert result.flatness > 0.45


def test_seeded_white_noise_has_high_entropy() -> None:
    noise = np.random.default_rng(4321).normal(0.0, 0.2, 48000)
    result = analyze_spectral(noise, 48000)
    assert result.entropy is not None
    assert result.entropy > 0.85


def test_last_full_frame_is_end_aligned() -> None:
    samples = sine(440.0, seconds=0.3)
    result = analyze_spectral(samples, 48000, frame_size=4096, hop_size=3000)
    assert result.frames[-1].start_sample == samples.size - 4096


def test_short_signal_uses_one_partial_frame() -> None:
    samples = sine(440.0, seconds=0.01)
    result = analyze_spectral(samples, 48000, frame_size=4096)
    assert result.frame_count == 1
    assert result.frames[0].sample_count == samples.size


def test_default_fft_size_is_next_power_of_two() -> None:
    result = analyze_spectral(sine(440.0), 48000, frame_size=3000)
    assert result.fft_size == 4096


def test_explicit_fft_size_is_recorded() -> None:
    result = analyze_spectral(sine(440.0), 48000, frame_size=2048, fft_size=8192)
    assert result.fft_size == 8192
    assert result.frequency_resolution_hz == pytest.approx(48000 / 8192)


def test_identical_analysis_has_identical_hash() -> None:
    samples = sine(440.0)
    first = analyze_spectral(samples, 48000)
    second = analyze_spectral(samples.copy(), 48000)
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.to_dict() == second.to_dict()


def test_changed_sample_changes_hash() -> None:
    samples = sine(440.0)
    changed = samples.copy()
    changed[123] += 1e-6
    assert analyze_spectral(samples, 48000).analysis_sha256 != analyze_spectral(changed, 48000).analysis_sha256


def test_report_hash_is_lowercase_sha256() -> None:
    result = analyze_spectral(sine(440.0), 48000)
    assert len(result.analysis_sha256) == 64
    assert result.analysis_sha256 == result.analysis_sha256.lower()
    assert result.to_dict()["analysis_sha256"] == result.analysis_sha256


def test_stationary_sine_has_low_flux() -> None:
    result = analyze_spectral(sine(440.0, seconds=2.0), 48000)
    assert result.median_spectral_flux is not None
    assert result.median_spectral_flux < 0.05


def test_abrupt_frequency_change_increases_flux() -> None:
    samples = np.concatenate((sine(300.0), sine(4000.0)))
    result = analyze_spectral(samples, 48000)
    assert result.maximum_spectral_flux is not None
    assert result.maximum_spectral_flux > 0.2


def test_audio_source_wrapper_preserves_sample_identity() -> None:
    samples = sine(440.0)
    source = SimpleNamespace(
        metadata=SimpleNamespace(sample_rate=48000),
        mono_samples=samples,
    )
    direct = analyze_spectral(samples, 48000)
    wrapped = analyze_audio_source_spectral(source)
    assert wrapped.sample_sha256 == direct.sample_sha256


def test_invalid_shapes_are_rejected() -> None:
    with pytest.raises(AnalysisError):
        analyze_spectral(np.zeros((2, 3)), 48000)
    with pytest.raises(AnalysisError):
        analyze_spectral(np.array([], dtype=np.float64), 48000)


def test_non_finite_samples_are_rejected() -> None:
    with pytest.raises(AnalysisError):
        analyze_spectral(np.array([0.0, np.nan]), 48000)


def test_invalid_configuration_is_rejected() -> None:
    samples = sine(440.0)
    with pytest.raises(AnalysisError):
        analyze_spectral(samples, 0)
    with pytest.raises(AnalysisError):
        analyze_spectral(samples, 48000, frame_size=2048, fft_size=1024)
    with pytest.raises(AnalysisError):
        analyze_spectral(samples, 48000, fft_size=3000)
    with pytest.raises(AnalysisError):
        analyze_spectral(samples, 48000, low_band_max_hz=5000, mid_band_max_hz=1000)
