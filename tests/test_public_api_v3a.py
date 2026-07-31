from __future__ import annotations

import w_mwxt_wavetable_tool as tool


def test_code_v3a_public_api() -> None:
    assert isinstance(tool.__version__, str) and tool.__version__
    assert tool.AudioSource is not None
    assert tool.AudioMetadata is not None
    assert tool.MonoPolicy.AUTO.value == "auto"
    assert callable(tool.import_audio)
    assert callable(tool.convert_to_mono)
