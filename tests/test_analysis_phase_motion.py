
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import (
    PhaseContinuityClass,
    PitchMotionClass,
    analyze_phase_motion,
    analyze_pitch_periodicity,
)
from w_mwxt_wavetable_tool.errors import AnalysisError


SAMPLE_RATE = 48000


def _sine(frequency: float, seconds: float = 1.0, phase: float = 0.0) -> np.ndarray:
    count = int(SAMPLE_RATE * seconds)
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    return 0.7 * np.sin(2.0 * np.pi * frequency * time + phase)


def _frequency_trajectory(frequencies: np.ndarray) -> np.ndarray:
    phase = 2.0 * np.pi * np.cumsum(frequencies, dtype=np.float64) / SAMPLE_RATE
    return 0.7 * np.sin(phase)


def _analyze(samples: np.ndarray, **kwargs: float | int):
    return analyze_phase_motion(
        samples,
        SAMPLE_RATE,
        frame_size=2048,
        hop_size=512,
        minimum_frequency_hz=80.0,
        maximum_frequency_hz=1200.0,
        confidence_threshold=0.50,
        **kwargs,
    )


def test_stable_sine_has_stable_pitch_motion() -> None:
    result = _analyze(_sine(440.0))
    assert result.pitch_motion_class is PitchMotionClass.STABLE
    assert result.pitch_excursion_cents is not None
    assert result.pitch_excursion_cents < 5.0
    assert result.pitch_transition_count > 10


def test_stable_sine_has_high_phase_stability() -> None:
    result = _analyze(_sine(440.0))
    assert result.phase_transition_count > 10
    assert result.phase_stability > 0.95
    assert result.discontinuity_count == 0
    assert result.phase_continuity_class is PhaseContinuityClass.STABLE


def test_phase_jump_is_detected() -> None:
    first = _sine(440.0, 0.5, phase=0.0)
    second = _sine(440.0, 0.5, phase=math.pi * 0.75)
    result = _analyze(np.concatenate([first, second]), phase_discontinuity_threshold_degrees=40.0)
    assert result.discontinuity_count >= 1
    assert result.maximum_phase_error_degrees is not None
    assert result.maximum_phase_error_degrees > 40.0
    assert result.phase_continuity_class is PhaseContinuityClass.DISCONTINUOUS


def test_silence_has_unavailable_phase_and_unvoiced_motion() -> None:
    result = _analyze(np.zeros(SAMPLE_RATE, dtype=np.float64))
    assert result.phase_continuity_class is PhaseContinuityClass.UNAVAILABLE
    assert result.pitch_motion_class is PitchMotionClass.UNVOICED
    assert result.phase_transition_count == 0
    assert result.pitch_transition_count == 0
    assert result.median_phase_error_degrees is None


def test_short_voiced_signal_reports_insufficient_motion() -> None:
    samples = _sine(440.0, seconds=0.02)
    result = _analyze(samples)
    assert result.phase_frame_count == 1
    assert result.pitch_motion_class is PitchMotionClass.INSUFFICIENT
    assert result.phase_continuity_class is PhaseContinuityClass.UNAVAILABLE


def test_upward_glide_classification() -> None:
    count = SAMPLE_RATE
    frequencies = np.linspace(220.0, 440.0, count, dtype=np.float64)
    result = _analyze(_frequency_trajectory(frequencies))
    assert result.pitch_motion_class is PitchMotionClass.GLIDE_UP
    assert result.pitch_slope_cents_per_second is not None
    assert result.pitch_slope_cents_per_second > 25.0
    assert result.direction_consistency >= 0.75


def test_downward_glide_classification() -> None:
    count = SAMPLE_RATE
    frequencies = np.linspace(440.0, 220.0, count, dtype=np.float64)
    result = _analyze(_frequency_trajectory(frequencies))
    assert result.pitch_motion_class is PitchMotionClass.GLIDE_DOWN
    assert result.pitch_slope_cents_per_second is not None
    assert result.pitch_slope_cents_per_second < -25.0


def test_vibrato_classification() -> None:
    count = SAMPLE_RATE * 2
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    frequencies = 440.0 * np.power(2.0, (45.0 * np.sin(2.0 * np.pi * 5.0 * time)) / 1200.0)
    result = _analyze(_frequency_trajectory(frequencies))
    assert result.pitch_motion_class is PitchMotionClass.VIBRATO
    assert result.reversal_count >= 4
    assert result.reversal_rate >= 0.05


def test_two_note_step_classification() -> None:
    first = _sine(220.0, 0.5)
    second = _sine(330.0, 0.5)
    result = _analyze(np.concatenate([first, second]))
    assert result.pitch_motion_class is PitchMotionClass.STEPPED
    assert result.maximum_pitch_step_cents is not None
    assert result.maximum_pitch_step_cents >= 100.0


def test_irregular_pitch_classification() -> None:
    block = SAMPLE_RATE // 8
    frequencies = [220.0, 270.0, 235.0, 350.0, 260.0, 410.0, 300.0, 245.0]
    samples = np.concatenate([_sine(freq, block / SAMPLE_RATE) for freq in frequencies])
    result = _analyze(samples)
    assert result.pitch_motion_class in {PitchMotionClass.IRREGULAR, PitchMotionClass.STEPPED}
    assert result.pitch_excursion_cents is not None
    assert result.pitch_excursion_cents > 100.0


def test_precomputed_pitch_is_reused_exactly() -> None:
    samples = _sine(330.0)
    pitch = analyze_pitch_periodicity(
        samples,
        SAMPLE_RATE,
        frame_size=2048,
        hop_size=512,
        minimum_frequency_hz=80.0,
        maximum_frequency_hz=1200.0,
        confidence_threshold=0.50,
    )
    first = analyze_phase_motion(samples, SAMPLE_RATE, pitch_periodicity=pitch)
    second = analyze_phase_motion(samples, SAMPLE_RATE, pitch_periodicity=pitch)
    assert first.to_dict() == second.to_dict()
    assert first.analysis_sha256 == second.analysis_sha256


def test_source_samples_are_not_modified() -> None:
    samples = _sine(440.0)
    before = samples.copy()
    _analyze(samples)
    assert np.array_equal(samples, before)


def test_hash_changes_when_signal_changes() -> None:
    first = _analyze(_sine(440.0))
    changed = _sine(440.0)
    changed[0] = 0.1
    second = _analyze(changed)
    assert first.sample_sha256 != second.sample_sha256
    assert first.analysis_sha256 != second.analysis_sha256


def test_json_contains_no_nan_or_infinity() -> None:
    rendered = json.dumps(_analyze(np.zeros(4096)).to_dict(), allow_nan=False)
    assert "NaN" not in rendered
    assert "Infinity" not in rendered


@pytest.mark.parametrize("threshold", [0.0, -1.0, float("inf"), float("nan")])
def test_invalid_positive_thresholds_are_rejected(threshold: float) -> None:
    with pytest.raises(AnalysisError):
        _analyze(_sine(440.0), stable_pitch_threshold_cents=threshold)


def test_phase_threshold_above_180_is_rejected() -> None:
    with pytest.raises(AnalysisError):
        _analyze(_sine(440.0), phase_discontinuity_threshold_degrees=181.0)


def test_negative_pitch_deadband_is_rejected() -> None:
    with pytest.raises(AnalysisError):
        _analyze(_sine(440.0), pitch_deadband_cents=-0.1)


def test_mismatched_precomputed_pitch_is_rejected() -> None:
    first = _sine(440.0)
    second = _sine(441.0)
    pitch = analyze_pitch_periodicity(
        first,
        SAMPLE_RATE,
        frame_size=2048,
        hop_size=512,
        minimum_frequency_hz=80.0,
        maximum_frequency_hz=1200.0,
        confidence_threshold=0.50,
    )
    with pytest.raises(AnalysisError):
        analyze_phase_motion(second, SAMPLE_RATE, pitch_periodicity=pitch)


def test_non_finite_samples_are_rejected() -> None:
    samples = _sine(440.0)
    samples[5] = np.nan
    with pytest.raises(AnalysisError):
        _analyze(samples)


def test_multichannel_samples_are_rejected() -> None:
    samples = np.column_stack([_sine(440.0), _sine(440.0)])
    with pytest.raises(AnalysisError):
        _analyze(samples)


def test_phase_frame_projection_strength_is_bounded() -> None:
    result = _analyze(_sine(440.0))
    assert all(0.0 <= frame.projection_strength <= 1.0 for frame in result.frames)


def test_transition_indexes_are_adjacent() -> None:
    result = _analyze(_sine(440.0))
    assert all(
        transition.to_frame_index == transition.from_frame_index + 1
        for transition in result.phase_transitions
    )


def test_custom_discontinuity_threshold_changes_count() -> None:
    first = _sine(440.0, 0.5)
    second = _sine(440.0, 0.5, phase=math.pi / 3.0)
    samples = np.concatenate([first, second])
    strict = _analyze(samples, phase_discontinuity_threshold_degrees=20.0)
    tolerant = _analyze(samples, phase_discontinuity_threshold_degrees=100.0)
    assert strict.discontinuity_count >= tolerant.discontinuity_count


def test_analysis_records_configuration() -> None:
    result = _analyze(
        _sine(440.0),
        phase_discontinuity_threshold_degrees=55.0,
        stable_pitch_threshold_cents=12.0,
        glide_slope_threshold_cents_per_second=30.0,
        stepped_pitch_threshold_cents=90.0,
    )
    assert result.phase_discontinuity_threshold_degrees == 55.0
    assert result.stable_pitch_threshold_cents == 12.0
    assert result.glide_slope_threshold_cents_per_second == 30.0
    assert result.stepped_pitch_threshold_cents == 90.0
