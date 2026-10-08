import json
from importlib.resources import files


def test_v8h_closure_overlay_targets_only_factory_placement_requirements():
    path = files("w_mwxt_wavetable_tool.compliance.data").joinpath(
        "v8_priority_closure_v3.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["baseline"]["commit"] == "159217a3a3a25b91e2b4a703d41de9253b14d3b3"
    assert set(payload["requirements"]) == {
        "CDC-PLC-001",
        "CDC-PLC-002",
        "CDC-PLC-003",
        "CDC-PLC-004",
        "CDC-PLC-005",
        "CDC-PLC-006",
        "CDC-PLC-007",
        "CDC-PROF-003",
    }
    assert payload["zones"] == {
        "stable_playable": [1, 20],
        "main_evolution": [21, 45],
        "extreme": [46, 61],
    }
    assert payload["migration"]["legacy_aliases_close_factory_style_requirement"] is False
    assert payload["boundaries"]["historical_waldorf_reconstruction_claim"] is False
    for later_stage in (
        "hardware_pass_claim",
        "inventory_allocation",
        "midi_transport",
        "physical_wave_consolidation",
        "sysex_generation",
        "wctd_materialization",
    ):
        assert payload["boundaries"][later_stage] is False
