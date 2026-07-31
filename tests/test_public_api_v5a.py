from __future__ import annotations

import w_mwxt_wavetable_tool as tool


def test_v5a_public_api_is_available() -> None:
    assert tool.SpectralAnalysis is not None
    assert tool.SpectralFrameAnalysis is not None
    assert callable(tool.analyze_spectral)
    assert callable(tool.analyze_audio_source_spectral)


def test_v5a_names_are_exported() -> None:
    assert {"SpectralAnalysis", "SpectralFrameAnalysis", "analyze_spectral", "analyze_audio_source_spectral"} <= set(tool.__all__)


def test_intermediate_gate_keeps_release_version() -> None:
    assert tool.__version__ == "0.4.0"
