from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path


def test_v8j_closure_overlay_preserves_registry_and_hardware_boundaries() -> None:
    root = Path(__file__).parents[1]
    path = root / "src/w_mwxt_wavetable_tool/compliance/data/v8_priority_closure_v5.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    previous = root / "src/w_mwxt_wavetable_tool/compliance/data/v8_priority_closure_v4.json"
    assert payload["schema_version"] == 5
    assert payload["closure_id"] == "code-v8-j-priority-closure-v5"
    assert payload["baseline"]["commit"] == "8bdee0b239277a9ca91a3f4057e3df2e40145cbe"
    assert payload["canonical_registry"]["requirement_count"] == 206
    assert payload["requirements"] == {}
    assert payload["predecessor"]["sha256"] == sha256(previous.read_bytes()).hexdigest()
    assert payload["boundaries"]["inventory_analysis"] is True
    assert payload["boundaries"]["allocation_proposal"] is True
    assert payload["boundaries"]["safe_free_hardware_activation"] is False
    assert payload["boundaries"]["wctd_materialization"] is False
    assert payload["boundaries"]["sysex_generation"] is False
    assert payload["boundaries"]["midi_transport"] is False
    assert payload["boundaries"]["v8_k_started"] is False
