from __future__ import annotations

import w_mwxt_wavetable_tool as tool


def test_v5a_public_api_is_available() -> None:
    assert tool.SpectralAnalysis is not None
    assert tool.SpectralFrameAnalysis is not None
    assert callable(tool.analyze_spectral)
    assert callable(tool.analyze_audio_source_spectral)


def test_v5a_names_are_exported() -> None:
    assert {"SpectralAnalysis", "SpectralFrameAnalysis", "analyze_spectral", "analyze_audio_source_spectral"} <= set(tool.__all__)


def test_code_v5_release_or_newer_is_public() -> None:
    assert tuple(int(part) for part in tool.__version__.split(".")) >= (0, 5, 0)
