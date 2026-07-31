from __future__ import annotations

import w_mwxt_wavetable_tool as tool


def test_code_v3a_public_api() -> None:
    assert tool.__version__ == "0.2.0"
    assert tool.AudioSource is not None
    assert tool.AudioMetadata is not None
    assert tool.MonoPolicy.AUTO.value == "auto"
    assert callable(tool.import_audio)
    assert callable(tool.convert_to_mono)
