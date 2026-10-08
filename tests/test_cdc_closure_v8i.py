from __future__ import annotations

import json
from importlib.resources import files


def test_v8i_closure_overlay_targets_only_final_consolidation_requirements() -> None:
    path = files("w_mwxt_wavetable_tool.compliance.data").joinpath(
        "v8_priority_closure_v4.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["baseline"]["commit"] == "b6d445329bd49f412663f942f71feb20f477c0b0"
    assert set(payload["requirements"]) == {
        "CDC-W61-002",
        "CDC-W61-007",
        "CDC-USE-001",
        "CDC-USE-002",
        "CDC-USE-003",
        "CDC-USE-004",
    }
    assert payload["requirements"]["CDC-USE-004"] == "prepared_for_v9"
    assert payload["boundaries"]["physical_wave_consolidation"] is True
    assert payload["boundaries"]["logical_position_count"] == 61
    assert payload["boundaries"]["physical_wave_count_min"] == 1
    assert payload["boundaries"]["physical_wave_count_max"] == 61
    for later_stage in (
        "inventory_allocation",
        "safe_free_inference",
        "wctd_materialization",
        "sysex_generation",
        "midi_transport",
        "v9_user_report_generated",
        "hardware_pass_claim",
    ):
        assert payload["boundaries"][later_stage] is False
    assert payload["policy"]["polarity_equivalence"] == "diagnostic_only_by_default"
