from __future__ import annotations

import w_mwxt_wavetable_tool.xt as xt


def test_v7a2_public_api() -> None:
    assert xt.AUDIO_GATE_SCHEMA_VERSION == 1
    assert callable(xt.build_xt_audio_gate)
    assert callable(xt.analyze_xt_audio_gate)
    assert callable(xt.verify_xt_audio_gate_setup)
    assert callable(xt.verify_xt_audio_gate_restore)
    assert callable(xt.build_note_midi)
