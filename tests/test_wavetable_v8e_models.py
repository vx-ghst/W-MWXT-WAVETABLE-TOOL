from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json

import pytest

from v8e_transition_helpers import ALL_INTERPOLATION_METHODS, smooth_candidates, transition_context

from w_mwxt_wavetable_tool.wavetable import (
    CodeV8EStatus,
    ContinuityStatus,
    GenerationMethod,
    InterpolationPolicy,
    TransitionDensityPolicy,
    TransitionPositionKind,
    WavetableContractError,
    interpolate_xt_wave,
)


def test_interpolation_policy_hash_changes_with_method_order():
    first = InterpolationPolicy(
        method_priority=(
            GenerationMethod.WAVEFORM_INTERPOLATION,
            GenerationMethod.SPECTRAL_INTERPOLATION,
        )
    )
    second = InterpolationPolicy(
        method_priority=(
            GenerationMethod.SPECTRAL_INTERPOLATION,
            GenerationMethod.WAVEFORM_INTERPOLATION,
        )
    )
    assert first.analysis_sha256 != second.analysis_sha256


def test_density_policy_hash_changes_with_density():
    first = TransitionDensityPolicy(base_active_fraction=0.2)
    second = TransitionDensityPolicy(base_active_fraction=0.3, complexity_weight=0.7)
    assert first.analysis_sha256 != second.analysis_sha256


def test_interpolated_wave_json_payload_is_canonicalizable():
    left, right = smooth_candidates(2)
    wave = interpolate_xt_wave(
        left,
        right,
        0.5,
        GenerationMethod.WAVEFORM_INTERPOLATION,
    )
    encoded = json.dumps(wave.to_dict(), sort_keys=True, allow_nan=False)
    assert wave.analysis_sha256 in encoded


def test_transition_map_positions_are_sorted_and_unique():
    result = transition_context(4)[-1]
    records = result.primary_variant.transition_map.records
    positions = tuple(item.position for item in records)
    assert positions == tuple(sorted(set(positions)))


def test_transition_map_records_partition_kinds():
    transition_map = transition_context(4)[-1].primary_variant.transition_map
    kinds = tuple(item.kind for item in transition_map.records)
    assert kinds.count(TransitionPositionKind.INTERPOLATED) == transition_map.active_transition_count
    assert kinds.count(TransitionPositionKind.REPEATED_STAGE) == transition_map.repeated_transition_count
    assert kinds.count(TransitionPositionKind.EDGE_HOLD) == transition_map.edge_hold_count


def test_transition_records_link_to_slot_hashes():
    result = transition_context(4)[-1]
    variant = result.primary_variant
    for record in variant.transition_map.records:
        assert record.stored_samples_sha256 == variant.build.slots[
            record.position
        ].stored_samples_sha256


def test_active_record_has_interpolation_method_and_progress():
    result = transition_context(2)[-1]
    active = next(
        item
        for item in result.primary_variant.transition_map.records
        if item.kind is TransitionPositionKind.INTERPOLATED
    )
    assert active.active_stage
    assert active.method is not None and active.method.is_interpolation
    assert active.raw_progress is not None
    assert active.shaped_progress is not None


def test_repeated_record_is_not_active():
    from w_mwxt_wavetable_tool.wavetable import TransitionDensityPolicy

    result = transition_context(
        2,
        density_policy=TransitionDensityPolicy(
            base_active_fraction=0.05,
            complexity_weight=0.0,
        ),
    )[-1]
    repeated = next(
        item
        for item in result.primary_variant.transition_map.records
        if item.kind is TransitionPositionKind.REPEATED_STAGE
    )
    assert not repeated.active_stage
    assert repeated.method is not None


def test_edge_hold_has_one_source_and_no_progress():
    result = transition_context(1)[-1]
    record = result.primary_variant.transition_map.records[0]
    assert record.kind is TransitionPositionKind.EDGE_HOLD
    assert len(record.source_candidate_ids) == 1
    assert record.raw_progress is None
    assert record.shaped_progress is None
    assert record.method is None


def test_complete_analysis_primary_variant_is_rank_one():
    result = transition_context(4, requested_variants=3)[-1]
    assert result.status is CodeV8EStatus.COMPLETE
    assert result.primary_variant.rank == 1
    assert result.primary_variant.variant_id == result.primary_variant_id


def test_continuity_status_matches_counts():
    report = transition_context(4)[-1].primary_variant.continuity
    expected = (
        ContinuityStatus.FAIL
        if report.failure_count
        else ContinuityStatus.WARNING
        if report.warning_count
        else ContinuityStatus.PASS
    )
    assert report.status is expected


def test_analysis_json_is_deterministic():
    first = transition_context(4, requested_variants=2)[-1]
    second = transition_context(4, requested_variants=2)[-1]
    assert first.to_json() == second.to_json()
    assert first.to_json().endswith("\n")


def test_analysis_hash_changes_when_density_policy_changes():
    first = transition_context(
        2,
        density_policy=TransitionDensityPolicy(
            base_active_fraction=0.10,
            complexity_weight=0.0,
        ),
    )[-1]
    second = transition_context(
        2,
        density_policy=TransitionDensityPolicy(
            base_active_fraction=0.90,
            complexity_weight=0.0,
        ),
    )[-1]
    assert first.analysis_sha256 != second.analysis_sha256


def test_interpolated_wave_rejects_tampered_source_identity():
    left, right = smooth_candidates(2)
    wave = interpolate_xt_wave(
        left,
        right,
        0.5,
        GenerationMethod.WAVEFORM_INTERPOLATION,
    )
    with pytest.raises(WavetableContractError):
        replace(wave, source_candidate_ids=(left.candidate_id, left.candidate_id))


def test_transition_record_rejects_tampered_hash():
    result = transition_context(2)[-1]
    record = result.primary_variant.transition_map.records[0]
    with pytest.raises(WavetableContractError):
        replace(record, stored_samples_sha256="not-a-hash")


def test_transition_interval_rejects_non_contiguous_positions():
    result = transition_context(2)[-1]
    plan = result.primary_variant.transition_map.intervals[0]
    with pytest.raises(WavetableContractError):
        replace(plan, open_positions=plan.open_positions[:-1])


def test_transition_map_rejects_duplicate_record_positions():
    result = transition_context(2)[-1]
    transition_map = result.primary_variant.transition_map
    if len(transition_map.records) < 2:
        pytest.skip("variant has fewer than two open positions")
    duplicate = replace(
        transition_map.records[1],
        position=transition_map.records[0].position,
    )
    with pytest.raises(WavetableContractError):
        replace(
            transition_map,
            records=(transition_map.records[0], duplicate, *transition_map.records[2:]),
        )


def test_v8e_variant_rejects_wrong_build_identity():
    result = transition_context(2)[-1]
    variant = result.primary_variant
    wrong_build = replace(variant.build, variant_id="wrong-id")
    with pytest.raises(WavetableContractError):
        replace(variant, build=wrong_build)


def test_complete_analysis_rejects_wrong_primary_id():
    result = transition_context(2)[-1]
    with pytest.raises(WavetableContractError):
        replace(result, primary_variant_id="missing-variant")


def test_policy_and_result_models_are_frozen():
    policy = InterpolationPolicy()
    density = TransitionDensityPolicy()
    result = transition_context(2)[-1]
    with pytest.raises(FrozenInstanceError):
        policy.protect_level = False
    with pytest.raises(FrozenInstanceError):
        density.base_active_fraction = 0.9
    with pytest.raises(FrozenInstanceError):
        result.primary_variant.objective_score = 0.0
