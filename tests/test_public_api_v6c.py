from __future__ import annotations

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


def test_public_models_are_exported() -> None:
    for name in (
        "CycleCandidateStatus",
        "CycleCandidate",
        "CycleDiscoveryAnalysis",
    ):
        assert getattr(tool, name) is getattr(analysis, name)


def test_public_functions_are_exported() -> None:
    assert tool.discover_cycles is analysis.discover_cycles
    assert tool.analyze_audio_source_cycles is analysis.analyze_audio_source_cycles


def test_analysis_all_contains_v6c_symbols() -> None:
    expected = {
        "CycleCandidateStatus",
        "CycleCandidate",
        "CycleDiscoveryAnalysis",
        "discover_cycles",
        "analyze_audio_source_cycles",
    }
    assert expected <= set(analysis.__all__)


def test_package_all_contains_v6c_symbols() -> None:
    expected = {
        "CycleCandidateStatus",
        "CycleCandidate",
        "CycleDiscoveryAnalysis",
        "discover_cycles",
        "analyze_audio_source_cycles",
    }
    assert expected <= set(tool.__all__)


def test_intermediate_gate_keeps_release_version() -> None:
    assert tool.__version__ == "0.6.0"
