from __future__ import annotations

import json

import numpy as np
import pytest

from w_mwxt_wavetable_tool.repair import (
    RepairActionStatus,
    RepairContext,
    RepairDefect,
    RepairPolicy,
    auto_repair_wave,
    build_repair_policy_set,
)

from v8e_helpers import clipped_wave, harmonic_wave, high_harmonic_wave, sine_wave


def action_map(result):
    return {action.defect: action for action in result.actions}


def test_default_auto_repair_applies_detected_safe_actions() -> None:
    wave = np.clip(clipped_wave() + 0.05, -1.0, 1.0)
    context = RepairContext(aliasing_risk=0.6, safe_harmonic_limit=10)
    result = auto_repair_wave(wave, context=context)
    assert RepairDefect.DC_OFFSET.value in result.detected_defects
    assert RepairDefect.CLIPPING.value in result.detected_defects
    assert "remove_dc" in result.applied_actions
    assert "reconstruct_clipped_peaks" in result.applied_actions
    assert result.comparison.selected_detected_count < result.comparison.before_detected_count
    assert result.comparison.selected_is_candidate


def test_compare_policy_preserves_selected_samples_and_builds_candidate() -> None:
    wave = sine_wave() + 0.12
    policy = build_repair_policy_set(default_policy=RepairPolicy.COMPARE)
    result = auto_repair_wave(wave, policy_set=policy)
    assert result.final_samples == tuple(wave)
    assert result.comparison.selected_samples == tuple(wave)
    assert result.comparison.candidate_samples != tuple(wave)
    assert not result.comparison.selected_is_candidate
    assert action_map(result)[RepairDefect.DC_OFFSET].status is RepairActionStatus.PREVIEWED


def test_ignore_policy_records_without_changing_samples() -> None:
    wave = sine_wave() + 0.12
    policy = build_repair_policy_set(
        default_policy=RepairPolicy.IGNORE,
        overrides={RepairDefect.DC_OFFSET: RepairPolicy.IGNORE},
    )
    result = auto_repair_wave(wave, policy_set=policy)
    action = action_map(result)[RepairDefect.DC_OFFSET]
    assert action.status is RepairActionStatus.IGNORED
    assert result.final_samples == tuple(wave)


def test_preserve_policy_records_intentional_defect() -> None:
    wave = clipped_wave()
    policy = build_repair_policy_set(
        default_policy=RepairPolicy.PRESERVE,
        overrides={RepairDefect.CLIPPING: RepairPolicy.PRESERVE},
    )
    result = auto_repair_wave(wave, policy_set=policy)
    action = action_map(result)[RepairDefect.CLIPPING]
    assert action.status is RepairActionStatus.PRESERVED
    assert max(abs(value) for value in result.final_samples) == 1.0


def test_mixed_policies_keep_auto_and_compare_branches_separate() -> None:
    wave = clipped_wave()
    context = RepairContext(detected_pitch_hz=100.0, expected_pitch_hz=110.0)
    policy = build_repair_policy_set(
        default_policy=RepairPolicy.IGNORE,
        overrides={
            RepairDefect.PITCH_ESTIMATE: RepairPolicy.AUTO,
            RepairDefect.CLIPPING: RepairPolicy.COMPARE,
        },
    )
    result = auto_repair_wave(wave, context=context, policy_set=policy)
    actions = action_map(result)
    assert actions[RepairDefect.PITCH_ESTIMATE].status is RepairActionStatus.APPLIED
    assert actions[RepairDefect.PITCH_ESTIMATE].metadata_changed
    assert actions[RepairDefect.CLIPPING].status is RepairActionStatus.PREVIEWED
    assert result.comparison.selected_samples == tuple(wave)
    assert result.comparison.candidate_samples != result.comparison.selected_samples


def test_pitch_auto_action_updates_metadata_without_changing_samples() -> None:
    wave = sine_wave()
    context = RepairContext(detected_pitch_hz=100.0, expected_pitch_hz=110.0)
    result = auto_repair_wave(wave, context=context)
    action = action_map(result)[RepairDefect.PITCH_ESTIMATE]
    assert action.status is RepairActionStatus.APPLIED
    assert not action.changed
    assert action.metadata_changed
    assert result.corrected_pitch_hz == 110.0


def test_unsafe_redundancy_action_requires_review() -> None:
    wave = harmonic_wave()
    context = RepairContext(previous_samples=tuple(wave))
    result = auto_repair_wave(wave, context=context)
    action = action_map(result)[RepairDefect.REDUNDANT_WAVE]
    assert action.status is RepairActionStatus.REVIEW_REQUIRED
    assert result.warnings


def test_redundancy_action_applies_when_both_neighbors_exist() -> None:
    wave = harmonic_wave()
    context = RepairContext(
        previous_samples=tuple(wave),
        next_samples=tuple(high_harmonic_wave()),
    )
    result = auto_repair_wave(wave, context=context)
    action = action_map(result)[RepairDefect.REDUNDANT_WAVE]
    assert action.status is RepairActionStatus.APPLIED
    assert action.changed


def test_clean_wave_produces_only_not_required_actions() -> None:
    wave = sine_wave(amplitude=0.7)
    result = auto_repair_wave(wave)
    assert result.detected_defects == ()
    assert result.applied_actions == ()
    assert all(action.status is RepairActionStatus.NOT_REQUIRED for action in result.actions)
    assert result.final_samples == tuple(wave)


def test_result_contains_all_findings_and_actions_in_canonical_order() -> None:
    result = auto_repair_wave(clipped_wave())
    assert tuple(item.defect for item in result.findings) == tuple(RepairDefect)
    assert tuple(item.defect for item in result.actions) == tuple(RepairDefect)


def test_result_is_deterministic_and_json_safe() -> None:
    wave = np.clip(clipped_wave() + 0.05, -1.0, 1.0)
    context = RepairContext(aliasing_risk=0.4, safe_harmonic_limit=9)
    first = auto_repair_wave(wave, context=context)
    second = auto_repair_wave(wave.copy(), context=context)
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.to_dict() == second.to_dict()
    assert json.dumps(first.to_dict(), allow_nan=False)


def test_auto_repair_never_exceeds_normalized_range() -> None:
    wave = np.clip(clipped_wave() + 0.05, -1.0, 1.0)
    result = auto_repair_wave(
        wave,
        context=RepairContext(target_rms=0.9, aliasing_risk=0.8),
    )
    assert max(abs(value) for value in result.final_samples) <= 1.0


@pytest.mark.parametrize(
    "samples",
    [[0.0], [0.0, float("nan")], [0.0, float("inf")], [0.0, 1.2]],
)
def test_engine_rejects_invalid_input(samples: list[float]) -> None:
    with pytest.raises(ValueError):
        auto_repair_wave(samples)


def test_compare_candidate_can_be_selected_externally_without_hidden_state() -> None:
    wave = sine_wave() + 0.12
    result = auto_repair_wave(
        wave,
        policy_set=build_repair_policy_set(default_policy=RepairPolicy.COMPARE),
    )
    candidate = np.asarray(result.comparison.candidate_samples)
    assert abs(float(np.mean(candidate))) < abs(float(np.mean(wave)))
    assert result.comparison.candidate_metrics.sample_sha256 != result.comparison.before_metrics.sample_sha256
