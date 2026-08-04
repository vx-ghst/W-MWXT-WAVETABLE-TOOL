from w_mwxt_wavetable_tool import (
    FactoryPlacementStatus,
    FactoryZone,
    build_factory_placement,
    plan_adaptive_slot_budget,
)

from v8h_helpers import v8h_context


def test_factory_placement_uses_three_non_overlapping_display_zones():
    request, v8b, v8c, v8d, regions = v8h_context()
    placement = build_factory_placement(request, v8b, v8c, v8d, plan_adaptive_slot_budget(regions))
    assert placement.status is FactoryPlacementStatus.COMPLETE
    assert placement.applied is True
    assert placement.primary_variant is not None
    for assignment in placement.primary_variant.assignments:
        if assignment.zone is FactoryZone.STABLE:
            assert 1 <= assignment.display_position <= 20
        elif assignment.zone is FactoryZone.EVOLUTION:
            assert 21 <= assignment.display_position <= 45
        else:
            assert 46 <= assignment.display_position <= 61
    assert tuple(item.position for item in placement.primary_variant.assignments) == tuple(
        sorted(item.position for item in placement.primary_variant.assignments)
    )


def test_factory_placement_exposes_zone_budget_scores_and_variant_deltas():
    request, v8b, v8c, v8d, regions = v8h_context(requested_variants=3)
    placement = build_factory_placement(request, v8b, v8c, v8d, plan_adaptive_slot_budget(regions))
    variants = placement.variants
    assert len(variants) >= 2
    assert tuple(item.rank for item in variants) == tuple(range(1, len(variants) + 1))
    assert tuple(item.objective_score for item in variants) == tuple(
        sorted((item.objective_score for item in variants), reverse=True)
    )
    for item in variants:
        assert sum(item.zone_counts) == len(item.assignments)
        assert 0.0 <= item.trajectory_score <= 1.0
        assert 0.0 <= item.adjacency_score <= 1.0
        assert 0.0 <= item.source_fidelity_score <= 1.0
        assert 0.0 <= item.zone_count_score <= 1.0
        assert item.profiled_variant.mean_position_delta_from_primary >= 0.0
