from __future__ import annotations

import numpy as np
import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.repair import (
    RepairContext,
    RepairDefect,
    apply_repair_action,
    detect_wave_defects,
    measure_repair_wave,
)

from v8e_helpers import (
    clipped_wave,
    harmonic_wave,
    high_harmonic_wave,
    noisy_wave,
    sine_wave,
    weak_fundamental_wave,
)


def finding(samples: np.ndarray, defect: RepairDefect, context: RepairContext | None = None):
    return {
        item.defect: item
        for item in detect_wave_defects(samples, context=context)
    }[defect]


def correlation(left: np.ndarray, right: np.ndarray) -> float:
    a = left - np.mean(left)
    b = right - np.mean(right)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_remove_dc_action() -> None:
    wave = sine_wave() + 0.12
    result = apply_repair_action(wave, finding(wave, RepairDefect.DC_OFFSET))
    assert abs(np.mean(result.samples)) < 1.0e-12
    assert result.samples_sha256 != measure_repair_wave(wave).sample_sha256


def test_reconstruct_clipped_peaks_action() -> None:
    wave = clipped_wave()
    before = measure_repair_wave(wave)
    result = apply_repair_action(wave, finding(wave, RepairDefect.CLIPPING))
    after = measure_repair_wave(result.samples)
    assert after.clipping_ratio < before.clipping_ratio
    assert max(abs(value) for value in result.samples) <= 1.0


def test_rotate_to_zero_crossing_action() -> None:
    wave = np.roll(sine_wave(phase=0.2), 17)
    result = apply_repair_action(wave, finding(wave, RepairDefect.ZERO_CROSSING))
    assert abs(result.samples[0]) == pytest.approx(min(abs(value) for value in wave), abs=0.05)
    assert dict(result.parameters)["rotation_samples"] >= 0


def test_smooth_loop_seam_action() -> None:
    wave = harmonic_wave()
    wave[-1] = 0.9
    before = measure_repair_wave(wave).seam_value_ratio
    result = apply_repair_action(wave, finding(wave, RepairDefect.LOOP_DISCONTINUITY))
    assert measure_repair_wave(result.samples).seam_value_ratio < before


def test_smooth_derivative_action() -> None:
    wave = harmonic_wave()
    wave[1] = 0.9
    before = measure_repair_wave(wave).seam_slope_ratio
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.DERIVATIVE_DISCONTINUITY),
    )
    assert measure_repair_wave(result.samples).seam_slope_ratio < before


def test_phase_alignment_action() -> None:
    reference = harmonic_wave()
    wave = np.roll(reference, 23)
    context = RepairContext(reference_samples=tuple(reference))
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.PHASE_INVERSION, context),
        context=context,
    )
    assert correlation(reference, np.asarray(result.samples)) > 0.999


def test_polarity_inversion_action() -> None:
    reference = harmonic_wave()
    wave = -reference
    context = RepairContext(reference_samples=tuple(reference))
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.POLARITY_INVERSION, context),
        context=context,
    )
    assert correlation(reference, np.asarray(result.samples)) > 0.999


def test_start_end_envelope_action() -> None:
    wave = harmonic_wave()
    wave[:8] *= 0.1
    before = {
        item.defect: item for item in detect_wave_defects(wave)
    }[RepairDefect.START_END_MISMATCH].score
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.START_END_MISMATCH),
    )
    after = {
        item.defect: item for item in detect_wave_defects(result.samples)
    }[RepairDefect.START_END_MISMATCH].score
    assert after < before


def test_match_amplitude_action() -> None:
    wave = sine_wave(amplitude=0.15)
    context = RepairContext(target_rms=0.5)
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.AMPLITUDE_INCONSISTENCY, context),
        context=context,
    )
    assert measure_repair_wave(result.samples).rms == pytest.approx(0.5)


def test_resample_cycle_length_action() -> None:
    wave = sine_wave(sample_count=96)
    context = RepairContext(expected_sample_count=128)
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.CYCLE_LENGTH, context),
        context=context,
    )
    assert len(result.samples) == 128
    assert dict(result.parameters)["algorithm"] == "windowed_sinc"


def test_update_pitch_metadata_action() -> None:
    wave = sine_wave()
    context = RepairContext(detected_pitch_hz=100.0, expected_pitch_hz=110.0)
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.PITCH_ESTIMATE, context),
        context=context,
    )
    assert result.samples == tuple(wave)
    assert result.corrected_pitch_hz == 110.0


def test_reduce_parasitic_noise_action() -> None:
    wave = noisy_wave()
    before = measure_repair_wave(wave)
    context = RepairContext(tonal_expected=False)
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.PARASITIC_NOISE, context),
        context=context,
    )
    after = measure_repair_wave(result.samples)
    assert after.spectral_flatness < before.spectral_flatness


def test_restore_fundamental_action() -> None:
    wave = weak_fundamental_wave()
    before = measure_repair_wave(wave).fundamental_ratio
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.FUNDAMENTAL_LOSS),
    )
    assert measure_repair_wave(result.samples).fundamental_ratio > before


def test_smooth_spectral_transition_action() -> None:
    reference = sine_wave()
    wave = high_harmonic_wave()
    context = RepairContext(previous_samples=tuple(reference))
    before = {
        item.defect: item
        for item in detect_wave_defects(wave, context=context)
    }[RepairDefect.SPECTRAL_JUMP].score
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.SPECTRAL_JUMP, context),
        context=context,
    )
    after = {
        item.defect: item
        for item in detect_wave_defects(result.samples, context=context)
    }[RepairDefect.SPECTRAL_JUMP].score
    assert after < before


def test_match_inter_wave_level_action() -> None:
    reference = sine_wave(amplitude=0.8)
    wave = sine_wave(amplitude=0.2)
    context = RepairContext(previous_samples=tuple(reference))
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.INTER_WAVE_LEVEL_MISMATCH, context),
        context=context,
    )
    assert measure_repair_wave(result.samples).rms == pytest.approx(
        measure_repair_wave(reference).rms
    )


def test_interpolate_redundant_wave_action() -> None:
    previous = harmonic_wave()
    wave = previous.copy()
    following = np.roll(high_harmonic_wave(), 7)
    context = RepairContext(
        previous_samples=tuple(previous),
        next_samples=tuple(following),
    )
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.REDUNDANT_WAVE, context),
        context=context,
    )
    assert result.samples != tuple(wave)
    assert len(result.samples) == 128


def test_reduce_aliasing_action() -> None:
    wave = high_harmonic_wave()
    context = RepairContext(aliasing_risk=0.8, safe_harmonic_limit=8)
    before = measure_repair_wave(wave).high_band_ratio
    result = apply_repair_action(
        wave,
        finding(wave, RepairDefect.EXCESSIVE_ALIASING, context),
        context=context,
    )
    assert measure_repair_wave(result.samples).high_band_ratio < before


@pytest.mark.parametrize(
    "samples",
    [[0.0], [0.0, float("nan")], [0.0, 1.1]],
)
def test_actions_reject_invalid_samples(samples: list[float]) -> None:
    wave = sine_wave()
    detected = finding(wave + 0.1, RepairDefect.DC_OFFSET)
    with pytest.raises(AnalysisError):
        apply_repair_action(samples, detected)


def test_reference_action_rejects_missing_reference() -> None:
    wave = harmonic_wave()
    detected = finding(wave, RepairDefect.PHASE_INVERSION)
    with pytest.raises(AnalysisError):
        apply_repair_action(wave, detected)
