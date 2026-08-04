from v8g_helpers import region_analysis

from w_mwxt_wavetable_tool import RegionKind, plan_adaptive_slot_budget


def test_budget_partitions_exactly_61_positions():
    plan = plan_adaptive_slot_budget(region_analysis())
    assert plan.total_slots == 61
    assert sum(item.slot_count for item in plan.budgets) == 61


def test_evolution_receives_more_than_stable_and_redundant():
    plan = plan_adaptive_slot_budget(region_analysis())
    by_kind = {item.kind: item for item in plan.budgets}
    assert by_kind[RegionKind.EVOLUTION].slot_count > by_kind[RegionKind.SUSTAIN].slot_count
    assert by_kind[RegionKind.EVOLUTION].slot_count > by_kind[RegionKind.REDUNDANCY].slot_count


def test_redundancy_is_never_also_strong_change():
    plan = plan_adaptive_slot_budget(region_analysis())
    redundant = next(item for item in plan.budgets if item.kind is RegionKind.REDUNDANCY)
    assert redundant.redundant_region
    assert not redundant.strong_change_region


def test_budget_moves_with_the_evolving_source_region_and_is_deterministic():
    first = plan_adaptive_slot_budget(region_analysis(evolving_index=1))
    repeated = plan_adaptive_slot_budget(region_analysis(evolving_index=1))
    moved = plan_adaptive_slot_budget(region_analysis(evolving_index=3))
    assert first.to_dict() == repeated.to_dict()
    assert [item.slot_count for item in first.budgets] != [item.slot_count for item in moved.budgets]
