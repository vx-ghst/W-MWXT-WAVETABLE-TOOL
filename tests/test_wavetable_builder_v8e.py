from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from v8e_transition_helpers import (
    corpus,
    rejected_v8d,
    relaxed_continuity_thresholds,
    required_lock,
    smooth_candidates,
    transition_context,
)
from v8d_placement_helpers import variants_context

from w_mwxt_wavetable_tool.wavetable import (
    CodeV8EStatus,
    ContinuityStatus,
    InterpolationPolicy,
    TransitionPositionKind,
    WavetableBuildStatus,
    WavetableContractError,
    build_wavetable_transitions,
)


@pytest.mark.parametrize("count", (1, 2, 8))
def test_v8e_builds_exactly_sixty_one_slots(count):
    _, _, _, _, result = transition_context(count)
    assert result.status is CodeV8EStatus.COMPLETE
    assert len(result.primary_variant.build.slots) == 61
    assert tuple(slot.position for slot in result.primary_variant.build.slots) == tuple(range(61))


def test_sixty_one_selected_keyframes_need_no_transition_records():
    request, v8b, v8c, v8d = variants_context(
        61,
        candidates=corpus(61),
        requested_variants=1,
    )
    result = build_wavetable_transitions(
        request,
        v8b,
        v8c,
        v8d,
        continuity_thresholds=relaxed_continuity_thresholds(),
    )
    assert result.status is CodeV8EStatus.COMPLETE
    variant = result.primary_variant
    assert len(variant.build.slots) == 61
    assert variant.transition_map.open_position_count == 0
    assert not variant.transition_map.records


def test_every_v8d_keyframe_is_preserved_byte_for_byte():
    request, _, _, v8d, result = transition_context(8)
    candidates = {item.candidate_id: item for item in request.candidates}
    source_variant = next(
        item for item in v8d.variants if item.variant_id == result.primary_variant.v8d_variant_id
    )
    build = result.primary_variant.build
    for assignment in source_variant.placement.assignments:
        assert build.slots[assignment.position].stored_samples == candidates[
            assignment.candidate_id
        ].stored_samples


def test_required_locked_keyframe_remains_locked_and_exact():
    items = smooth_candidates(3)
    lock = required_lock(30, items[1].candidate_id)
    request, _, _, v8d, result = transition_context(
        3,
        candidates=items,
        locks=(lock,),
    )
    source_variant = next(
        item for item in v8d.variants if item.variant_id == result.primary_variant.v8d_variant_id
    )
    assignment = next(
        item for item in source_variant.placement.assignments if item.candidate_id == items[1].candidate_id
    )
    slot = result.primary_variant.build.slots[assignment.position]
    assert assignment.position == 30
    assert slot.locked
    assert slot.stored_samples == items[1].stored_samples


def test_essential_positions_remain_structural_and_non_transition():
    _, _, _, v8d, result = transition_context(4)
    source_variant = next(
        item for item in v8d.variants if item.variant_id == result.primary_variant.v8d_variant_id
    )
    build = result.primary_variant.build
    essential_assignments = tuple(
        item for item in source_variant.placement.assignments if item.essential
    )
    assert essential_assignments
    for assignment in essential_assignments:
        slot = build.slots[assignment.position]
        assert slot.structural
        assert not slot.transition
        assert slot.role.value == "essential"


def test_transition_records_exactly_match_v8d_open_positions():
    _, _, _, v8d, result = transition_context(4)
    source_variant = next(
        item for item in v8d.variants if item.variant_id == result.primary_variant.v8d_variant_id
    )
    record_positions = tuple(item.position for item in result.primary_variant.transition_map.records)
    assert record_positions == source_variant.placement.open_positions


def test_transition_slots_reference_two_source_candidates():
    _, _, _, _, result = transition_context(2)
    build = result.primary_variant.build
    transition_slots = tuple(slot for slot in build.slots if slot.transition)
    assert transition_slots
    assert all(len(slot.source_candidate_ids) == 2 for slot in transition_slots)
    assert all(slot.generation_method.is_interpolation for slot in transition_slots)


def test_one_keyframe_uses_only_edge_holds_outside_anchor():
    _, _, _, v8d, result = transition_context(1)
    source_variant = next(
        item for item in v8d.variants if item.variant_id == result.primary_variant.v8d_variant_id
    )
    transition_map = result.primary_variant.transition_map
    assert transition_map.edge_hold_count == len(source_variant.placement.open_positions)
    assert transition_map.active_transition_count == 0
    assert transition_map.repeated_transition_count == 0
    assert all(item.kind is TransitionPositionKind.EDGE_HOLD for item in transition_map.records)


def test_low_density_creates_repeated_transition_stages():
    from w_mwxt_wavetable_tool.wavetable import TransitionDensityPolicy

    _, _, _, _, result = transition_context(
        2,
        density_policy=TransitionDensityPolicy(
            base_active_fraction=0.05,
            complexity_weight=0.0,
        ),
    )
    transition_map = result.primary_variant.transition_map
    assert transition_map.active_transition_count >= 1
    assert transition_map.repeated_transition_count >= 1


def test_build_set_contains_ranked_v8e_builds():
    _, _, _, _, result = transition_context(4, requested_variants=3)
    assert result.build_set is not None
    assert tuple(item.variant_id for item in result.build_set.builds) == tuple(
        item.variant_id for item in result.variants
    )
    assert result.build_set.primary_variant_id == result.primary_variant_id


def test_variants_are_ranked_by_v8e_objective():
    _, _, _, _, result = transition_context(4, requested_variants=4)
    scores = tuple(item.objective_score for item in result.variants)
    assert scores == tuple(sorted(scores, reverse=True))
    assert tuple(item.rank for item in result.variants) == tuple(
        range(1, len(result.variants) + 1)
    )


def test_each_complete_variant_has_continuity_and_transition_evidence():
    _, _, _, _, result = transition_context(4, requested_variants=3)
    for variant in result.variants:
        assert variant.build.status is WavetableBuildStatus.COMPLETE
        assert variant.continuity.build_sha256 == variant.build.analysis_sha256
        assert variant.transition_map.v8d_variant_id == variant.v8d_variant_id
        assert variant.continuity.status is not ContinuityStatus.FAIL


def test_v8e_analysis_is_deterministic():
    first = transition_context(4, requested_variants=2)[-1]
    second = transition_context(4, requested_variants=2)[-1]
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256


def test_v8e_models_are_frozen():
    result = transition_context(2)[-1]
    with pytest.raises(FrozenInstanceError):
        result.status = CodeV8EStatus.REJECTED
    with pytest.raises(FrozenInstanceError):
        result.primary_variant.rank = 99


def test_rejected_v8d_input_produces_no_partial_build():
    request, v8b, v8c, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    result = build_wavetable_transitions(
        request,
        v8b,
        v8c,
        rejected_v8d(v8d),
    )
    assert result.status is CodeV8EStatus.REJECTED
    assert not result.variants
    assert result.build_set is None
    assert result.blockers


def test_no_common_interpolation_method_rejects_without_partial_build():
    request, v8b, v8c, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    policy = InterpolationPolicy(
        method_priority=(type(request.policy.allowed_interpolation_methods[0]).AMPLITUDE_INTERPOLATION,)
    )
    result = build_wavetable_transitions(
        request,
        v8b,
        v8c,
        v8d,
        interpolation_policy=policy,
    )
    assert result.status is CodeV8EStatus.REJECTED
    assert result.blockers == (
        "request and V8-E policy have no common interpolation method",
    )


def test_link_mismatch_is_rejected_before_building():
    request, v8b, v8c, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    broken = replace(v8d, request_sha256="0" * 64)
    with pytest.raises(WavetableContractError):
        build_wavetable_transitions(request, v8b, v8c, broken)


def test_complete_v8e_boundaries_exclude_wctd_sysex_and_midi():
    result = transition_context(2)[-1]
    boundaries = result.to_dict()["boundaries"]
    assert boundaries["fills_all_61_positions"]
    assert boundaries["generates_transition_waves"]
    assert not boundaries["applies_factory_style"]
    assert not boundaries["materializes_wctd"]
    assert not boundaries["generates_sysex"]
    assert not boundaries["opens_midi_port"]
    assert not boundaries["transmits_midi"]
