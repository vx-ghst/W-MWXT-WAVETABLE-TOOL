from __future__ import annotations

from v8j_helpers import complete_source, physical_set, validated_empty_signature
from w_mwxt_wavetable_tool import (
    AllocationProposalStatus,
    InventoryState,
    SafeAllocationPolicy,
    UserWavetableDestination,
    analyze_xt_memory_inventory,
    plan_safe_user_wave_allocation,
)


def test_contiguous_safe_free_block_is_preferred_deterministically() -> None:
    inventory = analyze_xt_memory_inventory(
        (complete_source(empty_numbers=(1100, 1101, 1102, 1103)),),
        empty_wave_signature=validated_empty_signature(),
    )
    proposal = plan_safe_user_wave_allocation(
        physical_set(3),
        inventory,
        UserWavetableDestination(128),
    )
    assert proposal.status is AllocationProposalStatus.READY
    assert proposal.selected_user_wave_numbers == (1100, 1101, 1102)
    assert proposal.contiguous is True
    assert proposal.overwrite_wave_numbers == ()
    assert all(item.previous_state is InventoryState.SAFE_FREE for item in proposal.assignments)


def test_insufficient_safe_free_capacity_blocks_without_unknown_fallback() -> None:
    inventory = analyze_xt_memory_inventory((complete_source(),))
    proposal = plan_safe_user_wave_allocation(
        physical_set(2),
        inventory,
        UserWavetableDestination(128),
    )
    assert proposal.status is AllocationProposalStatus.BLOCKED
    assert proposal.assignments == ()
    assert proposal.blockers
    assert "SAFE_FREE" in " ".join(proposal.blockers)


def test_explicit_orphan_overwrite_authorization_is_audited() -> None:
    inventory = analyze_xt_memory_inventory((complete_source(),))
    policy = SafeAllocationPolicy(authorized_overwrite_numbers=(1100, 1101))
    proposal = plan_safe_user_wave_allocation(
        physical_set(2),
        inventory,
        UserWavetableDestination(127),
        policy,
    )
    assert proposal.status is AllocationProposalStatus.READY
    assert proposal.selected_user_wave_numbers == (1100, 1101)
    assert proposal.overwrite_wave_numbers == (1100, 1101)
    assert all(item.previous_state is InventoryState.ORPHANED for item in proposal.assignments)


def test_non_contiguous_requires_explicit_policy() -> None:
    inventory = analyze_xt_memory_inventory(
        (complete_source(empty_numbers=(1100, 1102, 1104)),),
        empty_wave_signature=validated_empty_signature(),
    )
    blocked = plan_safe_user_wave_allocation(
        physical_set(3), inventory, UserWavetableDestination(126)
    )
    ready = plan_safe_user_wave_allocation(
        physical_set(3),
        inventory,
        UserWavetableDestination(126),
        SafeAllocationPolicy(allow_non_contiguous=True),
    )
    assert blocked.status is AllocationProposalStatus.BLOCKED
    assert ready.status is AllocationProposalStatus.READY
    assert ready.selected_user_wave_numbers == (1100, 1102, 1104)
    assert ready.contiguous is False
