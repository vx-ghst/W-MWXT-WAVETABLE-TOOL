from __future__ import annotations

from dataclasses import replace

from v8j_helpers import complete_source, partial_source, validated_empty_signature
from w_mwxt_wavetable_tool import (
    InventoryDumpSource,
    InventoryPresence,
    InventorySourceKind,
    InventoryState,
    UserWave,
    analyze_xt_memory_inventory,
)


def test_partial_dump_keeps_unproven_entries_unknown_but_references_prove_used() -> None:
    result = analyze_xt_memory_inventory((partial_source(),))
    assert result.evidence_status.user_wave_coverage_complete is False
    assert result.evidence_status.user_wavetable_coverage_complete is False
    assert result.evidence_status.safe_free_enabled is False
    assert result.wave_entry(1000).state is InventoryState.USED
    assert result.wave_entry(1100).state is InventoryState.UNKNOWN
    assert result.wave_entry(1200).state is InventoryState.UNKNOWN


def test_complete_coverage_without_empty_signature_classifies_unreferenced_content_orphaned() -> None:
    result = analyze_xt_memory_inventory((complete_source(),))
    assert result.wave_entry(1000).state is InventoryState.USED
    assert result.wave_entry(1100).state is InventoryState.ORPHANED
    assert result.evidence_status.safe_free_enabled is False
    assert "validated empty" in " ".join(result.evidence_status.blockers).lower()


def test_conflicting_wave_payload_is_never_safe_free() -> None:
    base = complete_source()
    conflicting_message = UserWave(0, 1100, tuple([1] * 64)).to_message()
    conflict = InventoryDumpSource(
        source_id="conflicting-source",
        source_kind=InventorySourceKind.OTHER_EXTERNAL_DUMP,
        dump=replace(base.dump, messages=(conflicting_message,)),
    )
    result = analyze_xt_memory_inventory(
        (base, conflict),
        empty_wave_signature=validated_empty_signature(),
    )
    entry = result.wave_entry(1100)
    assert entry.presence is InventoryPresence.CONFLICTED
    assert entry.state is InventoryState.UNKNOWN
    assert result.evidence_status.safe_free_enabled is False
