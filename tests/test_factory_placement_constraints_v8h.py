from w_mwxt_wavetable_tool import (
    CodeV8HStatus,
    ConstraintOutcomeStatus,
    ConstraintStrength,
    PositionLock,
    build_code_v8h,
    build_factory_placement,
    plan_adaptive_slot_budget,
)
from v8b_helpers import required_lock
from v8d_placement_helpers import preference_lock

from v8h_helpers import v8h_context


def test_required_locks_at_factory_boundaries_override_profile_preferences():
    locks = (
        required_lock(20, "smooth-002"),
        required_lock(45, "smooth-004"),
    )
    request, v8b, v8c, v8d, regions = v8h_context(6, locks=locks)
    placement = build_factory_placement(
        request, v8b, v8c, v8d, plan_adaptive_slot_budget(regions)
    )
    positions = {
        item.candidate_id: item.position
        for item in placement.primary_variant.assignments
    }
    assert positions["smooth-002"] == 20
    assert positions["smooth-004"] == 45
    required = [
        item
        for item in placement.primary_variant.profiled_variant.placement.constraint_outcomes
        if item.strength is ConstraintStrength.REQUIRED
    ]
    assert required
    assert all(item.status is ConstraintOutcomeStatus.SATISFIED for item in required)


def test_unmet_preference_lock_is_reported_not_hidden():
    request, v8b, v8c, v8d, regions = v8h_context(
        6,
        locks=(preference_lock(60, "smooth-002"),),
    )
    placement = build_factory_placement(
        request, v8b, v8c, v8d, plan_adaptive_slot_budget(regions)
    )
    outcomes = placement.primary_variant.profiled_variant.placement.constraint_outcomes
    preference = next(item for item in outcomes if item.strength is ConstraintStrength.PREFERENCE)
    assert preference.status in {
        ConstraintOutcomeStatus.SATISFIED,
        ConstraintOutcomeStatus.VIOLATED,
    }
    if preference.status is ConstraintOutcomeStatus.VIOLATED:
        assert placement.primary_variant.warnings


def test_impossible_factory_zone_capacity_conflict_rejects_without_partial_output():
    locks = [required_lock(0, "smooth-000")]
    locks.extend(required_lock(position, f"smooth-{index:03d}") for index, position in enumerate(range(45, 61), 1))
    request, v8b, v8c, v8d, regions = v8h_context(
        17,
        locks=tuple(locks),
        requested_variants=1,
    )
    result = build_code_v8h(request, v8b, v8c, v8d, regions)
    assert result.status is CodeV8HStatus.REJECTED
    assert result.factory_placement is None
    assert result.variants == ()
    assert result.blockers
