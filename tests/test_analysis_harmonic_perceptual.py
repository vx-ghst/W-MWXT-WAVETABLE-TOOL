from __future__ import annotations

from types import SimpleNamespace
import json

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import analyze_spectral
from w_mwxt_wavetable_tool.analysis.harmonic_perceptual import (
    HarmonicPeak,
    analyze_audio_source_harmonic_perceptual,
    analyze_harmonic_perceptual,
)
from w_mwxt_wavetable_tool.errors import AnalysisError


def sine(
    frequency: float,
    *,
    sample_rate: int = 48000,
    seconds: float = 1.0,
    amplitude: float = 0.8,
) -> np.ndarray:
    t = np.arange(int(sample_rate * seconds), dtype=np.float64) / sample_rate
    return amplitude * np.sin(2.0 * np.pi * frequency * t)


def harmonic_tone(
    fundamental: float = 250.0,
    *,
    sample_rate: int = 48000,
    seconds: float = 1.0,
) -> np.ndarray:
    return (
        0.75 * sine(fundamental, sample_rate=sample_rate, seconds=seconds)
        + 0.35 * sine(2 * fundamental, sample_rate=sample_rate, seconds=seconds)
        + 0.20 * sine(3 * fundamental, sample_rate=sample_rate, seconds=seconds)
        + 0.10 * sine(4 * fundamental, sample_rate=sample_rate, seconds=seconds)
        + 0.05 * sine(5 * fundamental, sample_rate=sample_rate, seconds=seconds)
    )


def analyze(samples: np.ndarray, fundamental: float | None = 250.0):
    spectral = analyze_spectral(samples, 48000, frame_size=4096, hop_size=1024)
    return analyze_harmonic_perceptual(
        spectral,
        fundamental_frequency_hz=fundamental,
    )


def test_harmonic_tone_detects_multiple_harmonics() -> None:
    result = analyze(harmonic_tone())
    assert result.detected_harmonic_count >= 5


def test_harmonic_numbers_are_ordered() -> None:
    result = analyze(harmonic_tone())
    numbers = [peak.harmonic_number for peak in result.harmonic_peaks]
    assert numbers == sorted(numbers)


def test_fundamental_peak_is_detected() -> None:
    result = analyze(harmonic_tone())
    assert result.harmonic_peaks[0].harmonic_number == 1
    assert result.harmonic_peaks[0].observed_frequency_hz == pytest.approx(
        250.0, abs=15.0
    )


def test_harmonic_energy_is_high_for_harmonic_tone() -> None:
    result = analyze(harmonic_tone())
    assert result.harmonic_energy_ratio is not None
    assert result.harmonic_energy_ratio > 0.95


def test_residual_energy_complements_harmonic_energy() -> None:
    result = analyze(harmonic_tone())
    assert result.harmonic_energy_ratio is not None
    assert result.residual_energy_ratio is not None
    assert result.harmonic_energy_ratio + result.residual_energy_ratio == pytest.approx(1.0)


def test_harmonic_to_residual_is_positive_for_clean_tone() -> None:
    result = analyze(harmonic_tone())
    assert result.harmonic_to_residual_db is not None
    assert result.harmonic_to_residual_db > 5.0


def test_fundamental_power_exceeds_fifth_harmonic() -> None:
    result = analyze(harmonic_tone())
    fifth = next(peak for peak in result.harmonic_peaks if peak.harmonic_number == 5)
    assert result.fundamental_power_ratio is not None
    assert result.fundamental_power_ratio > fifth.band_power_ratio


def test_odd_even_ratios_sum_to_one() -> None:
    result = analyze(harmonic_tone())
    assert result.odd_harmonic_ratio is not None
    assert result.even_harmonic_ratio is not None
    assert result.odd_harmonic_ratio + result.even_harmonic_ratio == pytest.approx(1.0)


def test_tristimulus_ratios_sum_to_one() -> None:
    result = analyze(harmonic_tone())
    values = (result.tristimulus_1, result.tristimulus_2, result.tristimulus_3)
    assert all(value is not None for value in values)
    assert sum(value for value in values if value is not None) == pytest.approx(1.0)


def test_inharmonicity_is_low_for_exact_harmonics() -> None:
    result = analyze(harmonic_tone())
    assert result.inharmonicity_cents is not None
    assert result.inharmonicity_cents < 35.0


def test_detuned_partial_increases_inharmonicity() -> None:
    base = harmonic_tone()
    detuned = (
        0.75 * sine(250.0)
        + 0.35 * sine(500.0)
        + 0.20 * sine(760.0)
        + 0.10 * sine(1000.0)
    )
    base_result = analyze(base)
    detuned_result = analyze(detuned)
    assert base_result.inharmonicity_cents is not None
    assert detuned_result.inharmonicity_cents is not None
    assert detuned_result.inharmonicity_cents > base_result.inharmonicity_cents


def test_falling_harmonics_have_negative_slope() -> None:
    result = analyze(harmonic_tone())
    assert result.harmonic_slope_db_per_octave is not None
    assert result.harmonic_slope_db_per_octave < 0.0


def test_bark_energy_ratios_sum_to_one() -> None:
    result = analyze(harmonic_tone())
    assert sum(result.bark_band_energy_ratio) == pytest.approx(1.0)


def test_bark_band_count_is_configurable() -> None:
    spectral = analyze_spectral(harmonic_tone(), 48000)
    result = analyze_harmonic_perceptual(
        spectral,
        fundamental_frequency_hz=250.0,
        bark_band_count=12,
    )
    assert len(result.bark_band_energy_ratio) == 12


def test_bark_centroid_is_defined_for_active_signal() -> None:
    result = analyze(harmonic_tone())
    assert result.bark_centroid is not None
    assert result.bark_centroid > 0.0


def test_brightness_is_higher_for_high_tone() -> None:
    low = analyze(sine(250.0), 250.0)
    high = analyze(sine(8000.0), 8000.0)
    assert low.perceptual_brightness is not None
    assert high.perceptual_brightness is not None
    assert high.perceptual_brightness > low.perceptual_brightness


def test_clean_sine_has_high_spectral_concentration() -> None:
    result = analyze(sine(1000.0), 1000.0)
    assert result.spectral_concentration is not None
    assert result.spectral_concentration > 0.7


def test_seeded_noise_has_high_spectral_noisiness() -> None:
    noise = np.random.default_rng(1234).normal(0.0, 0.2, 48000)
    result = analyze(noise, None)
    assert result.spectral_noisiness is not None
    assert result.spectral_noisiness > 0.4


def test_unpitched_analysis_keeps_perceptual_descriptors() -> None:
    result = analyze(harmonic_tone(), None)
    assert result.fundamental_frequency_hz is None
    assert result.harmonic_energy_ratio is None
    assert result.harmonic_peaks == ()
    assert result.bark_centroid is not None


def test_silence_is_finite_and_serializable() -> None:
    result = analyze(np.zeros(5000), None)
    assert result.bark_centroid is None
    assert sum(result.bark_band_energy_ratio) == 0.0
    assert result.perceptual_brightness is None
    json.dumps(result.to_dict(), allow_nan=False)


def test_wrong_fundamental_reduces_harmonic_energy() -> None:
    samples = harmonic_tone()
    correct = analyze(samples, 250.0)
    wrong = analyze(samples, 330.0)
    assert correct.harmonic_energy_ratio is not None
    assert wrong.harmonic_energy_ratio is not None
    assert correct.harmonic_energy_ratio > wrong.harmonic_energy_ratio


def test_maximum_harmonics_limits_peak_count() -> None:
    spectral = analyze_spectral(harmonic_tone(), 48000)
    result = analyze_harmonic_perceptual(
        spectral,
        fundamental_frequency_hz=250.0,
        maximum_harmonics=3,
    )
    assert result.detected_harmonic_count <= 3
    assert all(peak.harmonic_number <= 3 for peak in result.harmonic_peaks)


def test_minimum_power_threshold_filters_weak_harmonics() -> None:
    spectral = analyze_spectral(harmonic_tone(), 48000)
    loose = analyze_harmonic_perceptual(
        spectral,
        fundamental_frequency_hz=250.0,
        minimum_harmonic_power_ratio=1e-8,
    )
    strict = analyze_harmonic_perceptual(
        spectral,
        fundamental_frequency_hz=250.0,
        minimum_harmonic_power_ratio=0.05,
    )
    assert strict.detected_harmonic_count < loose.detected_harmonic_count


def test_identical_analysis_has_identical_hash() -> None:
    spectral = analyze_spectral(harmonic_tone(), 48000)
    first = analyze_harmonic_perceptual(
        spectral, fundamental_frequency_hz=250.0
    )
    second = analyze_harmonic_perceptual(
        spectral, fundamental_frequency_hz=250.0
    )
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.to_dict() == second.to_dict()


def test_changed_fundamental_changes_hash() -> None:
    spectral = analyze_spectral(harmonic_tone(), 48000)
    first = analyze_harmonic_perceptual(
        spectral, fundamental_frequency_hz=250.0
    )
    second = analyze_harmonic_perceptual(
        spectral, fundamental_frequency_hz=251.0
    )
    assert first.analysis_sha256 != second.analysis_sha256


def test_spectral_hash_is_embedded() -> None:
    spectral = analyze_spectral(harmonic_tone(), 48000)
    result = analyze_harmonic_perceptual(
        spectral, fundamental_frequency_hz=250.0
    )
    assert result.spectral_analysis_sha256 == spectral.analysis_sha256


def test_audio_source_wrapper_reuses_spectral_analysis() -> None:
    samples = harmonic_tone()
    spectral = analyze_spectral(samples, 48000)
    source = SimpleNamespace(
        metadata=SimpleNamespace(sample_rate=48000),
        mono_samples=samples,
    )
    result = analyze_audio_source_harmonic_perceptual(
        source,
        fundamental_frequency_hz=250.0,
        spectral_analysis=spectral,
    )
    assert result.sample_sha256 == spectral.sample_sha256


def test_audio_source_wrapper_can_build_spectral_analysis() -> None:
    samples = harmonic_tone()
    source = SimpleNamespace(
        metadata=SimpleNamespace(sample_rate=48000),
        mono_samples=samples,
    )
    result = analyze_audio_source_harmonic_perceptual(
        source,
        fundamental_frequency_hz=250.0,
    )
    assert result.detected_harmonic_count >= 5


def test_invalid_configuration_is_rejected() -> None:
    spectral = analyze_spectral(harmonic_tone(), 48000)
    with pytest.raises(AnalysisError):
        analyze_harmonic_perceptual(
            spectral, fundamental_frequency_hz=0.0
        )
    with pytest.raises(AnalysisError):
        analyze_harmonic_perceptual(
            spectral, fundamental_frequency_hz=30000.0
        )
    with pytest.raises(AnalysisError):
        analyze_harmonic_perceptual(
            spectral,
            fundamental_frequency_hz=250.0,
            maximum_harmonics=0,
        )
    with pytest.raises(AnalysisError):
        analyze_harmonic_perceptual(
            spectral,
            fundamental_frequency_hz=250.0,
            harmonic_window_cents=0.0,
        )
    with pytest.raises(AnalysisError):
        analyze_harmonic_perceptual(
            spectral,
            fundamental_frequency_hz=250.0,
            minimum_harmonic_power_ratio=2.0,
        )


def test_harmonic_peak_model_rejects_invalid_number() -> None:
    with pytest.raises(ValueError):
        HarmonicPeak(
            harmonic_number=0,
            expected_frequency_hz=100.0,
            observed_frequency_hz=100.0,
            deviation_cents=0.0,
            band_power_ratio=0.5,
            peak_power_ratio=0.4,
        )
