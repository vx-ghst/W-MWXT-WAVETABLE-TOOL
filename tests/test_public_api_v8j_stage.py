from __future__ import annotations

import w_mwxt_wavetable_tool as package
from w_mwxt_wavetable_tool import wavetable


def test_v8j_inventory_api_is_exported_from_package_namespace() -> None:
    names = {
        "XT_MEMORY_INVENTORY_SCHEMA_VERSION",
        "InventoryState",
        "InventorySourceKind",
        "InventoryPresence",
        "InventoryDumpSource",
        "ValidatedEmptyWaveSignature",
        "InventoryEvidenceStatus",
        "UserWaveInventoryEntry",
        "UserWavetableInventoryEntry",
        "XtMemoryInventory",
        "analyze_xt_memory_inventory",
    }
    for name in names:
        assert hasattr(package, name), name
        assert name in package.__all__


def test_v8j_allocation_api_is_exported_from_package_and_wavetable_namespace() -> None:
    names = {
        "WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION",
        "AllocationProposalStatus",
        "SafeAllocationPolicy",
        "DEFAULT_SAFE_ALLOCATION_POLICY",
        "UserWaveDestinationAssignment",
        "AllocationProposal",
        "plan_safe_user_wave_allocation",
        "CODE_V8J_SCHEMA_VERSION",
        "CodeV8JStatus",
        "CodeV8JAnalysis",
        "build_code_v8j",
    }
    for name in names:
        assert hasattr(package, name), name
        assert hasattr(wavetable, name), name
        assert name in package.__all__
        assert name in wavetable.__all__
