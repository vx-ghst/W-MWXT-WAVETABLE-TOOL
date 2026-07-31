from __future__ import annotations

import w_mwxt_wavetable_tool as tool


def test_code_v4b_public_api_is_available() -> None:
    assert tool.PitchFrameAnalysis is not None
    assert tool.PitchPeriodicityAnalysis is not None
    assert tool.PeriodicityClass is not None
    assert callable(tool.analyze_pitch_periodicity)
    assert callable(tool.analyze_audio_source_pitch_periodicity)
    assert callable(tool.frequency_to_midi)
    assert callable(tool.midi_to_frequency)
    assert callable(tool.describe_frequency)
