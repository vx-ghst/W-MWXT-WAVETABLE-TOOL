from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from v8e_transition_helpers import (
    candidate,
    corpus,
    smooth_candidates,
    transition_context,
)
from v8d_placement_helpers import variants_context

from w_mwxt_wavetable_tool.wavetable import (
    TransitionDensityPolicy,
    WavetableContractError,
    plan_transition_density,
)


def test_one_keyframe_has_no_interior_transition_interval():
    request, _, _, v8d = variants_context(
        1,
        candidates=smooth_candidates(1),
        requested_variants=1,
    )
    assert v8d.primary_variant is not None
    assert plan_transition_density(request, v8d.primary_variant) == ()


def test_two_keyframes_have_one_density_interval_when_spaced():
    request, _, _, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    assert v8d.primary_variant is not None
    plans = plan_transition_density(request, v8d.primary_variant)
    assert len(plans) == 1
    assert plans[0].capacity > 0
    assert plans[0].active_step_count >= 1


def test_density_progress_count_matches_open_positions():
    request, _, _, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    plan = plan_transition_density(request, v8d.primary_variant)[0]
    assert len(plan.progress_values) == len(plan.open_positions)
    assert len(set(plan.progress_values)) == plan.active_step_count


def test_density_progress_is_non_decreasing_and_interior():
    request, _, _, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    plan = plan_transition_density(request, v8d.primary_variant)[0]
    assert plan.progress_values == tuple(sorted(plan.progress_values))
    assert all(0.0 < value < 1.0 for value in plan.progress_values)


@pytest.mark.parametrize("count", (2, 3, 8, 16))
def test_density_plans_partition_all_interior_open_positions(count):
    request, _, _, v8d = variants_context(
        count,
        candidates=corpus(count),
        requested_variants=1,
    )
    placement = v8d.primary_variant.placement
    plans = plan_transition_density(request, v8d.primary_variant)
    planned = {
        position for plan in plans for position in plan.open_positions
    }
    first = min(placement.occupied_positions)
    last = max(placement.occupied_positions)
    interior_open = {
        position
        for position in placement.open_positions
        if first < position < last
    }
    assert planned == interior_open


def test_higher_complexity_never_receives_lower_target_fraction():
    smooth = smooth_candidates(2)
    rough = (
        candidate(
            "rough-left",
            tuple(100 if index % 2 == 0 else -100 for index in range(64)),
            source_index=0,
            seed=0.0,
        ),
        candidate(
            "rough-right",
            tuple(((index * 67) % 255) - 127 for index in range(64)),
            source_index=1,
            seed=0.2,
        ),
    )
    smooth_request, _, _, smooth_v8d = variants_context(
        2, candidates=smooth, requested_variants=1
    )
    rough_request, _, _, rough_v8d = variants_context(
        2, candidates=rough, requested_variants=1
    )
    smooth_plan = plan_transition_density(
        smooth_request, smooth_v8d.primary_variant
    )[0]
    rough_plan = plan_transition_density(
        rough_request, rough_v8d.primary_variant
    )[0]
    assert rough_plan.complexity_score >= smooth_plan.complexity_score
    assert rough_plan.target_active_fraction >= smooth_plan.target_active_fraction


def test_full_density_policy_uses_every_interval_position_as_active():
    policy = TransitionDensityPolicy(
        base_active_fraction=1.0,
        complexity_weight=0.0,
    )
    request, _, _, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    plan = plan_transition_density(request, v8d.primary_variant, policy)[0]
    assert plan.active_step_count == plan.capacity
    assert len(set(plan.progress_values)) == plan.capacity


def test_low_density_policy_repeats_stages_when_capacity_is_large():
    policy = TransitionDensityPolicy(
        minimum_active_steps_per_interval=1,
        base_active_fraction=0.05,
        complexity_weight=0.0,
    )
    request, _, _, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    plan = plan_transition_density(request, v8d.primary_variant, policy)[0]
    assert plan.active_step_count < plan.capacity
    assert len(set(plan.progress_values)) < len(plan.progress_values)



def test_density_rejects_placement_linked_to_a_different_request():
    request, _, _, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    altered_request = replace(request, selected_profile=request.selected_profile + "-other")
    with pytest.raises(WavetableContractError):
        plan_transition_density(altered_request, v8d.primary_variant)

def test_density_plan_hash_is_deterministic():
    request, _, _, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    first = plan_transition_density(request, v8d.primary_variant)
    second = plan_transition_density(request, v8d.primary_variant)
    assert first == second
    assert tuple(item.analysis_sha256 for item in first) == tuple(
        item.analysis_sha256 for item in second
    )


def test_density_models_are_frozen():
    request, _, _, v8d = variants_context(
        2,
        candidates=smooth_candidates(2),
        requested_variants=1,
    )
    plan = plan_transition_density(request, v8d.primary_variant)[0]
    with pytest.raises(FrozenInstanceError):
        plan.active_step_count = 99


@pytest.mark.parametrize(
    "kwargs",
    (
        {"minimum_active_steps_per_interval": 0},
        {"base_active_fraction": -0.1},
        {"complexity_weight": 1.1},
        {"base_active_fraction": 0.7, "complexity_weight": 0.5},
        {"complexity_exponent": 0.0},
    ),
)
def test_density_policy_rejects_invalid_values(kwargs):
    with pytest.raises(WavetableContractError):
        TransitionDensityPolicy(**kwargs)


def test_transition_map_counts_match_records():
    _, _, _, _, result = transition_context(
        2,
        density_policy=TransitionDensityPolicy(
            base_active_fraction=0.10,
            complexity_weight=0.0,
        ),
    )
    transition_map = result.primary_variant.transition_map
    assert transition_map.open_position_count == len(transition_map.records)
    assert (
        transition_map.active_transition_count
        + transition_map.repeated_transition_count
        + transition_map.edge_hold_count
        == transition_map.open_position_count
    )
