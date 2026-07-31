from __future__ import annotations

import math

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import (
    PeriodicityClass,
    analyze_audio_source_pitch_periodicity,
    analyze_pitch_periodicity,
)
from w_mwxt_wavetable_tool.audio.models import (
    AudioContainerFormat,
    AudioMeasurements,
    AudioMetadata,
    AudioSource,
    MonoConversionReport,
    MonoPolicy,
    MonoStrategy,
)
from w_mwxt_wavetable_tool.errors import AnalysisError


def _sine(
    frequency_hz: float,
    *,
    sample_rate: int = 44100,
    duration_seconds: float = 1.0,
    amplitude: float = 0.8,
) -> np.ndarray:
    times = np.arange(int(sample_rate * duration_seconds), dtype=np.float64) / sample_rate
    return amplitude * np.sin(2.0 * np.pi * frequency_hz * times)


def _assert_json_numbers_finite(value: object) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _assert_json_numbers_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_json_numbers_finite(nested)
    elif isinstance(value, float):
        assert math.isfinite(value)


def _audio_source(samples: np.ndarray, sample_rate: int = 44100) -> AudioSource:
    samples = np.asarray(samples, dtype=np.float64)
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples))))
    mean = float(np.mean(samples))
    metadata = AudioMetadata(
        source_path=__file__,
        container=AudioContainerFormat.WAV,
        libsndfile_format="WAV",
        subtype="FLOAT",
        endian="FILE",
        sample_rate=sample_rate,
        channels=1,
        frames=samples.size,
        duration_seconds=samples.size / sample_rate,
        source_bytes=1,
        source_mtime_ns=1,
        source_sha256="1" * 64,
        source_extension=".wav",
        extension_matches_container=True,
    )
    measurements = AudioMeasurements(
        sample_count=samples.size,
        minimum=float(np.min(samples)),
        maximum=float(np.max(samples)),
        peak_absolute=peak,
        rms=rms,
        mean=mean,
        dc_offset=mean,
        is_silent=peak == 0.0,
        has_dc_offset=abs(mean) > 1e-4,
        all_finite=True,
    )
    conversion = MonoConversionReport(
        policy=MonoPolicy.AUTO,
        strategy=MonoStrategy.MONO_PASSTHROUGH,
        source_channels=1,
        selected_channel=0,
        channel_rms=(rms,),
        stereo_correlation=None,
        reason="test",
    )
    return AudioSource(metadata, samples, measurements, conversion)


def test_a4_sine_pitch_and_note_are_detected() -> None:
    analysis = analyze_pitch_periodicity(_sine(440.0), 44100)
    assert analysis.frequency_hz == pytest.approx(440.0, abs=0.1)
    assert analysis.note_name == "A4"
    assert analysis.nearest_midi_note == 69
    assert analysis.cents_deviation == pytest.approx(0.0, abs=0.5)
    assert analysis.periodicity_score > 0.99
    assert analysis.periodicity_class is PeriodicityClass.STABLE_PERIODIC


def test_detuned_pitch_reports_signed_cents() -> None:
    frequency = 440.0 * 2.0 ** (25.0 / 1200.0)
    analysis = analyze_pitch_periodicity(_sine(frequency), 44100)
    assert analysis.note_name == "A4"
    assert analysis.cents_deviation == pytest.approx(25.0, abs=0.75)


def test_square_wave_reports_its_fundamental() -> None:
    signal = np.sign(_sine(110.0)) * 0.5
    analysis = analyze_pitch_periodicity(signal, 44100)
    assert analysis.frequency_hz == pytest.approx(110.0, abs=0.2)
    assert analysis.note_name == "A2"


def test_harmonic_rich_signal_reports_the_fundamental() -> None:
    signal = (
        0.1 * _sine(110.0, amplitude=1.0)
        + 0.7 * _sine(220.0, amplitude=1.0)
        + 0.3 * _sine(330.0, amplitude=1.0)
    )
    analysis = analyze_pitch_periodicity(signal, 44100)
    assert analysis.frequency_hz == pytest.approx(110.0, abs=0.3)


def test_dc_offset_does_not_change_pitch() -> None:
    analysis = analyze_pitch_periodicity(0.5 + _sine(440.0, amplitude=0.2), 44100)
    assert analysis.frequency_hz == pytest.approx(440.0, abs=0.1)


def test_silence_is_classified_without_pitch() -> None:
    analysis = analyze_pitch_periodicity(np.zeros(44100), 44100)
    assert analysis.periodicity_class is PeriodicityClass.SILENT
    assert analysis.frequency_hz is None
    assert analysis.note_name is None
    assert analysis.voiced_frame_count == 0
    assert analysis.periodicity_score == 0.0


def test_seeded_white_noise_is_aperiodic() -> None:
    signal = np.random.default_rng(1234).normal(0.0, 0.1, 44100)
    analysis = analyze_pitch_periodicity(signal, 44100)
    assert analysis.periodicity_class is PeriodicityClass.APERIODIC
    assert analysis.frequency_hz is None
    assert analysis.voiced_frame_count == 0


def test_vibrato_is_classified_as_quasi_periodic() -> None:
    sample_rate = 44100
    times = np.arange(sample_rate, dtype=np.float64) / sample_rate
    instantaneous = 440.0 * 2.0 ** ((30.0 * np.sin(2.0 * np.pi * 5.0 * times)) / 1200.0)
    phase = 2.0 * np.pi * np.cumsum(instantaneous) / sample_rate
    signal = 0.8 * np.sin(phase)
    analysis = analyze_pitch_periodicity(signal, sample_rate)
    assert analysis.periodicity_class is PeriodicityClass.QUASI_PERIODIC
    assert analysis.pitch_spread_cents is not None
    assert 15.0 < analysis.pitch_spread_cents <= 120.0
    assert analysis.quasi_periodicity_score > 0.5


def test_periodicity_in_fewer_than_half_active_frames_is_intermittent() -> None:
    sample_rate = 44100
    noise = np.random.default_rng(99).normal(0.0, 0.1, sample_rate)
    periodic = _sine(440.0, duration_seconds=0.5)
    analysis = analyze_pitch_periodicity(
        np.concatenate([noise, periodic]),
        sample_rate,
    )
    assert analysis.periodicity_class is PeriodicityClass.INTERMITTENT_PERIODIC
    assert 0.0 < analysis.voiced_active_ratio < 0.5


def test_two_distant_notes_are_unstable_periodic() -> None:
    signal = np.concatenate(
        [
            _sine(440.0, duration_seconds=0.5),
            _sine(660.0, duration_seconds=0.5),
        ]
    )
    analysis = analyze_pitch_periodicity(signal, 44100)
    assert analysis.periodicity_class is PeriodicityClass.UNSTABLE_PERIODIC
    assert analysis.pitch_spread_cents is not None
    assert analysis.pitch_spread_cents > 120.0


def test_short_signal_uses_one_partial_frame() -> None:
    signal = _sine(440.0, duration_seconds=0.02)
    analysis = analyze_pitch_periodicity(signal, 44100)
    assert analysis.frame_count == 1
    assert analysis.frames[0].sample_count == signal.size
    assert analysis.frames[0].start_sample == 0


def test_frame_placement_is_end_aligned_and_deterministic() -> None:
    signal = _sine(440.0, duration_seconds=0.3)
    first = analyze_pitch_periodicity(signal, 44100, frame_size=2048, hop_size=700)
    second = analyze_pitch_periodicity(signal, 44100, frame_size=2048, hop_size=700)
    starts = tuple(frame.start_sample for frame in first.frames)
    assert starts[-1] == signal.size - 2048
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256


def test_sample_change_changes_hashes() -> None:
    signal = _sine(440.0, duration_seconds=0.1)
    changed = signal.copy()
    changed[0] += 1e-6
    first = analyze_pitch_periodicity(signal, 44100)
    second = analyze_pitch_periodicity(changed, 44100)
    assert first.sample_sha256 != second.sample_sha256
    assert first.analysis_sha256 != second.analysis_sha256


def test_analysis_does_not_modify_input() -> None:
    signal = _sine(440.0, duration_seconds=0.1)
    before = signal.copy()
    analyze_pitch_periodicity(signal, 44100)
    assert np.array_equal(signal, before)


def test_serialization_contains_no_nan_or_infinity() -> None:
    payload = analyze_pitch_periodicity(np.zeros(1024), 44100).to_dict()
    _assert_json_numbers_finite(payload)
    assert payload["frequency_hz"] is None
    assert payload["pitch_spread_cents"] is None


def test_audio_source_wrapper_reuses_canonical_sample_hash() -> None:
    source = _audio_source(_sine(440.0, duration_seconds=0.1))
    analysis = analyze_audio_source_pitch_periodicity(source)
    assert analysis.sample_sha256 == source.sample_sha256
    assert analysis.sample_rate == source.metadata.sample_rate
    assert analysis.sample_count == source.metadata.frames


def test_custom_reference_a4_is_used_for_note_description() -> None:
    analysis = analyze_pitch_periodicity(
        _sine(432.0),
        44100,
        reference_a4_hz=432.0,
    )
    assert analysis.note_name == "A4"
    assert analysis.cents_deviation == pytest.approx(0.0, abs=0.5)


@pytest.mark.parametrize("sample_rate", [0, -1])
def test_invalid_sample_rate_is_rejected(sample_rate: int) -> None:
    with pytest.raises(AnalysisError):
        analyze_pitch_periodicity(np.ones(64), sample_rate)


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [(0.0, 1000.0), (-1.0, 1000.0), (1000.0, 1000.0), (2000.0, 1000.0)],
)
def test_invalid_frequency_bounds_are_rejected(minimum: float, maximum: float) -> None:
    with pytest.raises(AnalysisError):
        analyze_pitch_periodicity(
            np.ones(64),
            44100,
            minimum_frequency_hz=minimum,
            maximum_frequency_hz=maximum,
        )


def test_frequency_bound_at_nyquist_is_rejected() -> None:
    with pytest.raises(AnalysisError):
        analyze_pitch_periodicity(np.ones(64), 8000, maximum_frequency_hz=4000.0)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, math.nan])
def test_invalid_confidence_is_rejected(confidence: float) -> None:
    with pytest.raises(AnalysisError):
        analyze_pitch_periodicity(
            np.ones(64),
            44100,
            confidence_threshold=confidence,
        )


def test_non_finite_samples_are_rejected() -> None:
    with pytest.raises(AnalysisError):
        analyze_pitch_periodicity(np.array([0.0, math.nan]), 44100)
