from __future__ import annotations

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


def test_public_models_are_exported() -> None:
    for name in (
        "CycleSelectionDecision",
        "CycleSelectionPolicy",
        "RankedCycleCandidate",
        "SelectedCycleSet",
    ):
        assert getattr(tool, name) is getattr(analysis, name)


def test_public_functions_are_exported() -> None:
    assert tool.select_representative_cycles is analysis.select_representative_cycles
    assert (
        tool.analyze_audio_source_cycle_selection
        is analysis.analyze_audio_source_cycle_selection
    )


def test_analysis_all_contains_v6d_symbols() -> None:
    expected = {
        "CycleSelectionDecision",
        "CycleSelectionPolicy",
        "RankedCycleCandidate",
        "SelectedCycleSet",
        "select_representative_cycles",
        "analyze_audio_source_cycle_selection",
    }
    assert expected <= set(analysis.__all__)


def test_package_all_contains_v6d_symbols() -> None:
    expected = {
        "CycleSelectionDecision",
        "CycleSelectionPolicy",
        "RankedCycleCandidate",
        "SelectedCycleSet",
        "select_representative_cycles",
        "analyze_audio_source_cycle_selection",
    }
    assert expected <= set(tool.__all__)


def test_intermediate_gate_keeps_release_version() -> None:
    assert tool.__version__ == "0.5.0"
