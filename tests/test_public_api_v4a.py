from __future__ import annotations

import w_mwxt_wavetable_tool as tool


def test_code_v4a_public_api_is_available() -> None:
    assert tool.LevelAnalysis is not None
    assert tool.EnvelopeAnalysis is not None
    assert tool.TimeDomainAnalysis is not None
    assert callable(tool.analyze_levels)
    assert callable(tool.analyze_envelope)
    assert callable(tool.analyze_time_domain)
    assert callable(tool.analyze_audio_source)
    assert tuple(int(part) for part in tool.__version__.split(".")) >= (0, 3, 0)
