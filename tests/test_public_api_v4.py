from __future__ import annotations

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


def test_top_level_public_api_exports_signal_analysis_contract() -> None:
    assert tool.SignalAnalysis is analysis.SignalAnalysis
    assert tool.analyze_signal is analysis.analyze_signal
    assert tool.analyze_audio_source_signal is analysis.analyze_audio_source_signal


def test_signal_analysis_exports_are_declared() -> None:
    assert "SignalAnalysis" in tool.__all__
    assert "analyze_signal" in tool.__all__
    assert "analyze_audio_source_signal" in tool.__all__


def test_code_v4_release_version_is_public() -> None:
    assert tool.__version__ == "0.4.0"
