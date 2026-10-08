from __future__ import annotations

import json

import numpy as np
import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.repair import (
    RepairActionStatus,
    RepairDefect,
    RepairPolicy,
    auto_repair_wave_sequence,
    build_repair_policy_set,
)

from v8e_helpers import harmonic_wave, high_harmonic_wave, sine_wave


def test_sequence_processes_entries_in_canonical_order() -> None:
    waves = (sine_wave(amplitude=0.8), sine_wave(amplitude=0.2), high_harmonic_wave())
    result = auto_repair_wave_sequence(waves)
    assert tuple(entry.index for entry in result.entries) == (0, 1, 2)
    assert len(result.before_sequence_sha256) == 64
    assert len(result.after_sequence_sha256) == 64


def test_sequence_uses_repaired_previous_wave_as_context() -> None:
    first = sine_wave(amplitude=0.8) + 0.08
    second = sine_wave(amplitude=0.2)
    result = auto_repair_wave_sequence((first, second))
    second_actions = {
        action.defect: action for action in result.entries[1].result.actions
    }
    assert second_actions[RepairDefect.INTER_WAVE_LEVEL_MISMATCH].status in {
        RepairActionStatus.APPLIED,
        RepairActionStatus.NOT_REQUIRED,
    }
    assert result.entries[1].result.context_sha256 != result.entries[0].result.context_sha256


def test_sequence_auto_repairs_inter_wave_level() -> None:
    waves = (
        sine_wave(amplitude=0.8),
        sine_wave(amplitude=0.12),
        sine_wave(amplitude=0.75),
    )
    result = auto_repair_wave_sequence(waves)
    action = {
        item.defect: item for item in result.entries[1].result.actions
    }[RepairDefect.INTER_WAVE_LEVEL_MISMATCH]
    assert action.status is RepairActionStatus.APPLIED


def test_sequence_compare_policy_keeps_original_sequence_selected() -> None:
    waves = (sine_wave() + 0.1, sine_wave(amplitude=0.2))
    policy = build_repair_policy_set(default_policy=RepairPolicy.COMPARE)
    result = auto_repair_wave_sequence(waves, policy_set=policy)
    assert tuple(entry.result.final_samples for entry in result.entries) == tuple(
        tuple(wave) for wave in waves
    )
    assert result.before_sequence_sha256 == result.after_sequence_sha256


def test_sequence_supports_exactly_61_waves() -> None:
    waves = tuple(
        np.roll(harmonic_wave(), index % 16) * (0.72 + 0.002 * index)
        for index in range(61)
    )
    result = auto_repair_wave_sequence(waves)
    assert len(result.entries) == 61
    assert result.entries[-1].index == 60
    assert all(len(entry.result.final_samples) == 128 for entry in result.entries)


def test_sequence_is_deterministic_and_json_safe() -> None:
    waves = (harmonic_wave(), high_harmonic_wave(), np.roll(harmonic_wave(), 9))
    first = auto_repair_wave_sequence(waves)
    second = auto_repair_wave_sequence(tuple(wave.copy() for wave in waves))
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.to_dict() == second.to_dict()
    assert json.dumps(first.to_dict(), allow_nan=False)


def test_sequence_counts_match_entry_results() -> None:
    waves = (sine_wave() + 0.1, high_harmonic_wave())
    result = auto_repair_wave_sequence(waves)
    assert result.detected_defect_count == sum(
        len(entry.result.detected_defects) for entry in result.entries
    )
    assert result.applied_action_count == sum(
        len(entry.result.applied_actions) for entry in result.entries
    )


def test_sequence_rejects_empty_input() -> None:
    with pytest.raises(AnalysisError):
        auto_repair_wave_sequence(())


def test_sequence_rejects_mixed_lengths() -> None:
    with pytest.raises(AnalysisError):
        auto_repair_wave_sequence((sine_wave(), sine_wave(sample_count=96)))
