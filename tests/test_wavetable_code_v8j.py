from __future__ import annotations

from dataclasses import replace

from v8j_helpers import complete_source, complete_v8i_analysis, validated_empty_signature
from w_mwxt_wavetable_tool import (
    AllocationProposalStatus,
    CodeV8IStatus,
    CodeV8JStatus,
    UserWavetableDestination,
    analyze_xt_memory_inventory,
    build_code_v8j,
)


def test_code_v8j_links_v8i_inventory_manual_destination_and_allocation() -> None:
    v8i = complete_v8i_analysis()
    inventory = analyze_xt_memory_inventory(
        (complete_source(empty_numbers=tuple(range(1100, 1161))),),
        empty_wave_signature=validated_empty_signature(),
    )
    result = build_code_v8j(v8i, inventory, UserWavetableDestination(128))
    assert result.status is CodeV8JStatus.COMPLETE
    assert result.selected_variant_id == v8i.primary_variant_id
    assert result.allocation is not None
    assert result.allocation.status is AllocationProposalStatus.READY
    assert result.allocation.user_wavetable_destination.display_number == 128
    payload = result.to_dict()
    assert payload["boundaries"]["wctd_materialized"] is False
    assert payload["boundaries"]["midi_opened"] is False
    assert payload["software_gate"]["safe_free_activation_gate"] == "v8_k_hardware_evidence"


def test_code_v8j_treats_blocked_allocation_as_valid_conservative_software_result() -> None:
    v8i = complete_v8i_analysis()
    inventory = analyze_xt_memory_inventory((complete_source(),))
    result = build_code_v8j(v8i, inventory, UserWavetableDestination(128))
    assert result.status is CodeV8JStatus.COMPLETE
    assert result.allocation is not None
    assert result.allocation.status is AllocationProposalStatus.BLOCKED
    assert result.blockers == ()
    assert result.warnings


def test_code_v8j_rejects_incomplete_v8i_without_partial_outputs() -> None:
    v8i = complete_v8i_analysis()
    rejected = replace(
        v8i,
        status=CodeV8IStatus.REJECTED,
        variants=(),
        primary_variant_id=None,
        blockers=("synthetic blocker",),
        reason="Synthetic rejected V8-I.",
    )
    inventory = analyze_xt_memory_inventory((complete_source(),))
    result = build_code_v8j(rejected, inventory, UserWavetableDestination(128))
    assert result.status is CodeV8JStatus.REJECTED
    assert result.inventory is None
    assert result.allocation is None
    assert result.blockers
