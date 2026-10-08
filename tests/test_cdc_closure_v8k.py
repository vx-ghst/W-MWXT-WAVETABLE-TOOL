from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path


def test_v8k_closure_overlay_preserves_registry_and_hardware_boundaries() -> None:
    root = Path(__file__).parents[1]
    path = root / "src/w_mwxt_wavetable_tool/compliance/data/v8_priority_closure_v6.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    previous = root / "src/w_mwxt_wavetable_tool/compliance/data/v8_priority_closure_v5.json"
    assert payload["schema_version"] == 6
    assert payload["closure_id"] == "code-v8-k-priority-closure-v6"
    assert payload["baseline"]["commit"] == "7d51e2a2f77afb682e2f3cace09fcca364b5dd17"
    assert payload["canonical_registry"]["requirement_count"] == 206
    assert payload["requirements"] == {}
    assert payload["predecessor"]["sha256"] == sha256(previous.read_bytes()).hexdigest()
    assert payload["boundaries"]["dense_wctd_materialization"] is True
    assert payload["boundaries"]["sparse_wctd_candidate"] is True
    assert payload["boundaries"]["sparse_wctd_hardware_activation"] is False
    assert payload["boundaries"]["offline_sysex_generation"] is True
    assert payload["boundaries"]["wavetable_package_n_plus_1"] is True
    assert payload["boundaries"]["complete_package_n_plus_2"] is False
    assert payload["boundaries"]["hardware_pass_claim"] is False
    assert payload["boundaries"]["midi_transport"] is False
    assert payload["boundaries"]["memory_write"] is False
    assert payload["boundaries"]["v8_l_started"] is False
