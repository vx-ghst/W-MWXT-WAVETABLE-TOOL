from __future__ import annotations

import numpy as np
import pytest

from w_mwxt_wavetable_tool.repair import (
    RepairContext,
    RepairDefect,
    RepairThresholds,
    detect_wave_defects,
)

from v8e_helpers import (
    clipped_wave,
    harmonic_wave,
    high_harmonic_wave,
    noisy_wave,
    sine_wave,
    weak_fundamental_wave,
)


def finding_map(samples: np.ndarray, context: RepairContext | None = None):
    return {
        finding.defect: finding
        for finding in detect_wave_defects(samples, context=context)
    }


def test_detector_returns_every_defect_in_canonical_order() -> None:
    findings = detect_wave_defects(sine_wave())
    assert tuple(item.defect for item in findings) == tuple(RepairDefect)
    assert len(findings) == 17


def test_dc_offset_detection() -> None:
    findings = finding_map(sine_wave() + 0.15)
    assert findings[RepairDefect.DC_OFFSET].detected
    assert findings[RepairDefect.DC_OFFSET].score > 0.20


def test_clipping_detection() -> None:
    findings = finding_map(clipped_wave())
    assert findings[RepairDefect.CLIPPING].detected
    assert findings[RepairDefect.CLIPPING].metric_map["clipping_ratio"] > 0.01


def test_incorrect_zero_crossing_detection() -> None:
    findings = finding_map(np.linspace(0.2, 0.8, 128, dtype=np.float64))
    assert findings[RepairDefect.ZERO_CROSSING].detected


def test_loop_discontinuity_detection() -> None:
    wave = harmonic_wave()
    wave[-1] = 0.9
    findings = finding_map(wave)
    assert findings[RepairDefect.LOOP_DISCONTINUITY].detected


def test_derivative_discontinuity_detection() -> None:
    wave = harmonic_wave()
    wave[1] = 0.9
    findings = finding_map(wave)
    assert findings[RepairDefect.DERIVATIVE_DISCONTINUITY].detected


def test_phase_shift_detection_with_reference() -> None:
    reference = harmonic_wave()
    shifted = np.roll(reference, 24)
    context = RepairContext(reference_samples=tuple(reference))
    finding = finding_map(shifted, context)[RepairDefect.PHASE_INVERSION]
    assert finding.detected
    assert abs(finding.metric_map["phase_shift_samples"]) >= 20


def test_phase_detection_is_explicitly_unevaluated_without_reference() -> None:
    finding = finding_map(harmonic_wave())[RepairDefect.PHASE_INVERSION]
    assert not finding.evaluated
    assert not finding.detected
    assert not finding.auto_safe


def test_polarity_inversion_detection() -> None:
    reference = harmonic_wave()
    context = RepairContext(reference_samples=tuple(reference))
    finding = finding_map(-reference, context)[RepairDefect.POLARITY_INVERSION]
    assert finding.detected
    assert finding.metric_map["raw_correlation"] < -0.99


def test_start_end_envelope_mismatch_detection() -> None:
    wave = harmonic_wave()
    wave[:8] *= 0.1
    wave[-8:] *= 1.0
    finding = finding_map(wave)[RepairDefect.START_END_MISMATCH]
    assert finding.detected


def test_amplitude_inconsistency_detection_from_target_rms() -> None:
    context = RepairContext(target_rms=0.7)
    finding = finding_map(sine_wave(amplitude=0.1), context)[
        RepairDefect.AMPLITUDE_INCONSISTENCY
    ]
    assert finding.detected
    assert finding.metric_map["amplitude_delta_db"] > 10.0


def test_amplitude_detection_is_unevaluated_without_target() -> None:
    finding = finding_map(sine_wave())[RepairDefect.AMPLITUDE_INCONSISTENCY]
    assert not finding.evaluated


def test_cycle_length_detection() -> None:
    context = RepairContext(expected_sample_count=128)
    finding = finding_map(sine_wave(sample_count=96), context)[RepairDefect.CYCLE_LENGTH]
    assert finding.detected
    assert finding.metric_map["sample_count"] == 96.0


def test_correct_cycle_length_is_not_detected() -> None:
    finding = finding_map(sine_wave())[RepairDefect.CYCLE_LENGTH]
    assert not finding.detected


def test_pitch_estimate_detection() -> None:
    context = RepairContext(detected_pitch_hz=100.0, expected_pitch_hz=110.0)
    finding = finding_map(sine_wave(), context)[RepairDefect.PITCH_ESTIMATE]
    assert finding.detected
    assert finding.metric_map["pitch_error_cents"] > 100.0


def test_pitch_detection_is_unevaluated_without_pair() -> None:
    finding = finding_map(sine_wave())[RepairDefect.PITCH_ESTIMATE]
    assert not finding.evaluated


def test_parasitic_noise_detection() -> None:
    finding = finding_map(noisy_wave(), RepairContext(tonal_expected=False))[
        RepairDefect.PARASITIC_NOISE
    ]
    assert finding.detected


def test_fundamental_loss_detection() -> None:
    finding = finding_map(weak_fundamental_wave())[
        RepairDefect.FUNDAMENTAL_LOSS
    ]
    assert finding.detected
    assert finding.score > 0.9


def test_fundamental_loss_is_disabled_for_non_tonal_material() -> None:
    context = RepairContext(tonal_expected=False)
    finding = finding_map(weak_fundamental_wave(), context)[
        RepairDefect.FUNDAMENTAL_LOSS
    ]
    assert not finding.evaluated


def test_spectral_jump_detection() -> None:
    reference = sine_wave()
    context = RepairContext(previous_samples=tuple(reference))
    finding = finding_map(high_harmonic_wave(), context)[RepairDefect.SPECTRAL_JUMP]
    assert finding.detected


def test_inter_wave_level_mismatch_detection() -> None:
    reference = sine_wave(amplitude=0.8)
    context = RepairContext(previous_samples=tuple(reference))
    finding = finding_map(sine_wave(amplitude=0.15), context)[
        RepairDefect.INTER_WAVE_LEVEL_MISMATCH
    ]
    assert finding.detected


def test_redundant_wave_detection_and_auto_safety() -> None:
    reference = harmonic_wave()
    context = RepairContext(
        previous_samples=tuple(reference),
        next_samples=tuple(np.roll(reference, 10)),
    )
    finding = finding_map(reference.copy(), context)[RepairDefect.REDUNDANT_WAVE]
    assert finding.detected
    assert finding.auto_safe


def test_redundant_wave_without_next_requires_review() -> None:
    reference = harmonic_wave()
    context = RepairContext(previous_samples=tuple(reference))
    finding = finding_map(reference.copy(), context)[RepairDefect.REDUNDANT_WAVE]
    assert finding.detected
    assert not finding.auto_safe


def test_aliasing_detection_from_explicit_risk() -> None:
    context = RepairContext(aliasing_risk=0.8)
    finding = finding_map(sine_wave(), context)[RepairDefect.EXCESSIVE_ALIASING]
    assert finding.detected
    assert finding.score == pytest.approx(0.8)


def test_aliasing_detection_can_be_derived_from_wave() -> None:
    context = RepairContext(safe_harmonic_limit=8)
    finding = finding_map(high_harmonic_wave(), context)[
        RepairDefect.EXCESSIVE_ALIASING
    ]
    assert finding.detected


def test_threshold_change_controls_detection() -> None:
    wave = sine_wave() + 0.03
    default = {
        item.defect: item for item in detect_wave_defects(wave)
    }[RepairDefect.DC_OFFSET]
    strict = {
        item.defect: item
        for item in detect_wave_defects(
            wave,
            thresholds=RepairThresholds(dc_ratio=0.20),
        )
    }[RepairDefect.DC_OFFSET]
    assert default.detected
    assert not strict.detected
