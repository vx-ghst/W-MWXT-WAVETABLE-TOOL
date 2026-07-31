from __future__ import annotations

import w_mwxt_wavetable_tool as tool


def test_v5b_public_api_is_available() -> None:
    assert tool.HarmonicPeak is not None
    assert tool.HarmonicPerceptualAnalysis is not None
    assert callable(tool.analyze_harmonic_perceptual)
    assert callable(tool.analyze_audio_source_harmonic_perceptual)


def test_v5b_names_are_exported() -> None:
    assert {
        "HarmonicPeak",
        "HarmonicPerceptualAnalysis",
        "analyze_harmonic_perceptual",
        "analyze_audio_source_harmonic_perceptual",
    } <= set(tool.__all__)


def test_code_v5_release_or_newer_is_public() -> None:
    assert tuple(int(part) for part in tool.__version__.split(".")) >= (0, 5, 0)
