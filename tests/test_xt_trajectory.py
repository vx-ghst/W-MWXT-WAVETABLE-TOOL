from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.xt.projection import (
    PROJECTION_SCHEMA_VERSION,
    XtProjectionSet,
    XtProjectionWeights,
    project_wave_xt_native,
    reconstruct_xt_native,
)
from w_mwxt_wavetable_tool.xt.trajectory import (
    XtInterpolationCurve,
    XtPhasePathPolicy,
    XtTrajectoryConfig,
    XtTrajectorySlotKind,
    build_xt_wavetable_trajectory_document,
    load_and_build_xt_wavetable_trajectory,
)


def _stored_pattern(seed: int, scale: float = 1.0) -> tuple[int, ...]:
    values = []
    for index in range(64):
        raw = ((seed + index * 29 + (index * index * 3)) % 255) - 127
        values.append(int(np.clip(round(raw * scale), -127, 127)))
    return tuple(values)


def _projection_document() -> dict:
    stored_sets = (
        _stored_pattern(3, 0.65),
        _stored_pattern(3, 0.62),
        _stored_pattern(91, 0.92),
        _stored_pattern(127, 0.78),
    )
    waves = []
    for index, stored in enumerate(stored_sets):
        source = tuple(value / 127.0 for value in reconstruct_xt_native(stored))
        waves.append(
            project_wave_xt_native(
                source,
                index=index,
                candidate_index=100 + index,
                source_wave_sha256=f"{index + 1:064x}",
            )
        )
    result = XtProjectionSet(
        schema_version=PROJECTION_SCHEMA_VERSION,
        tool_version="0.6.0",
        source_reconstructed_wave_set_sha256="a" * 64,
        source_code_v6_analysis_sha256=None,
        weights=XtProjectionWeights(),
        waves=tuple(waves),
        decision_reason="test projection",
    )
    return result.to_dict()


def test_builds_exact_slot_count_and_preserves_every_anchor() -> None:
    document = _projection_document()
    config = XtTrajectoryConfig(
        target_slot_count=13,
        phase_path_policy=XtPhasePathPolicy.PRESERVE,
        minimum_intermediates_per_transition=1,
    )
    result = build_xt_wavetable_trajectory_document(document, config=config)
    assert result.anchor_count == 4
    assert result.interpolated_slot_count == 9
    assert len(result.slots) == 13
    assert result.anchor_slot_numbers[0] == 1
    assert result.anchor_slot_numbers[-1] == 13
    assert [slot.source_wave_index for slot in result.slots if slot.kind is XtTrajectorySlotKind.ANCHOR] == [0, 1, 2, 3]
    for anchor, slot_number in zip(result.anchors, result.anchor_slot_numbers, strict=True):
        assert result.slots[slot_number - 1].stored_samples == anchor.stored_samples


def test_all_slots_obey_xt_native_invariants() -> None:
    result = build_xt_wavetable_trajectory_document(
        _projection_document(),
        config=XtTrajectoryConfig(target_slot_count=17),
    )
    for slot in result.slots:
        assert len(slot.stored_samples) == 64
        assert min(slot.stored_samples) >= -127
        assert max(slot.stored_samples) <= 127
        assert -128 not in slot.stored_samples
        assert len(slot.reconstructed_samples) == 128
        assert slot.reconstructed_samples == reconstruct_xt_native(slot.stored_samples)
    assert result.to_dict()["boundaries"]["generates_sysex"] is False
    assert result.to_dict()["boundaries"]["allows_negative_128"] is False


def test_spacing_allocates_more_positions_to_larger_transitions() -> None:
    result = build_xt_wavetable_trajectory_document(
        _projection_document(),
        config=XtTrajectoryConfig(
            target_slot_count=21,
            phase_path_policy=XtPhasePathPolicy.PRESERVE,
            minimum_intermediates_per_transition=1,
        ),
    )
    distances = [transition.combined_distance for transition in result.transitions]
    allocations = [transition.allocated_intermediate_count for transition in result.transitions]
    largest = int(np.argmax(distances))
    smallest = int(np.argmin(distances))
    assert allocations[largest] >= allocations[smallest]
    assert sum(allocations) == 21 - result.anchor_count


def test_global_phase_path_respects_fidelity_bound_and_is_deterministic() -> None:
    config = XtTrajectoryConfig(
        target_slot_count=19,
        phase_path_policy=XtPhasePathPolicy.GLOBAL,
        max_objective_increase=0.02,
    )
    first = build_xt_wavetable_trajectory_document(_projection_document(), config=config)
    second = build_xt_wavetable_trajectory_document(_projection_document(), config=config)
    assert first.to_dict() == second.to_dict()
    assert first.analysis_sha256 == second.analysis_sha256
    assert all(anchor.objective_increase <= 0.02 + 1e-12 for anchor in first.anchors)


def test_interpolation_curve_is_explicit_and_changes_blend_fraction() -> None:
    linear = build_xt_wavetable_trajectory_document(
        _projection_document(),
        config=XtTrajectoryConfig(
            target_slot_count=14,
            phase_path_policy=XtPhasePathPolicy.PRESERVE,
            interpolation_curve=XtInterpolationCurve.LINEAR,
        ),
    )
    smooth = build_xt_wavetable_trajectory_document(
        _projection_document(),
        config=XtTrajectoryConfig(
            target_slot_count=14,
            phase_path_policy=XtPhasePathPolicy.PRESERVE,
            interpolation_curve=XtInterpolationCurve.SMOOTHSTEP,
        ),
    )
    pairs = [
        (left, right)
        for left, right in zip(linear.slots, smooth.slots, strict=True)
        if left.kind is XtTrajectorySlotKind.INTERPOLATED
        and left.position_fraction not in {0.5}
    ]
    assert pairs
    linear_interpolated, smooth_interpolated = pairs[0]
    assert linear_interpolated.position_fraction == smooth_interpolated.position_fraction
    assert linear_interpolated.blend_fraction != smooth_interpolated.blend_fraction


def test_hash_integrity_is_verified(tmp_path: Path) -> None:
    document = _projection_document()
    path = tmp_path / "projection.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    result = load_and_build_xt_wavetable_trajectory(
        path,
        config=XtTrajectoryConfig(target_slot_count=11, minimum_intermediates_per_transition=0),
    )
    assert result.anchor_count == 4
    corrupted = copy.deepcopy(document)
    corrupted["waves"][0]["stored_samples"][0] += 1
    path.write_text(json.dumps(corrupted), encoding="utf-8")
    with pytest.raises(AnalysisError, match="mismatch"):
        load_and_build_xt_wavetable_trajectory(path)


def test_rejects_impossible_slot_policy() -> None:
    with pytest.raises(AnalysisError, match="cannot fit"):
        build_xt_wavetable_trajectory_document(
            _projection_document(),
            config=XtTrajectoryConfig(
                target_slot_count=5,
                minimum_intermediates_per_transition=1,
            ),
        )


def test_write_is_byte_deterministic(tmp_path: Path) -> None:
    result = build_xt_wavetable_trajectory_document(
        _projection_document(),
        config=XtTrajectoryConfig(target_slot_count=15),
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_json, first_md = result.write(first_dir)
    second_json, second_md = result.write(second_dir)
    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_md.read_bytes() == second_md.read_bytes()
