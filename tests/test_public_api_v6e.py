from __future__ import annotations

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


def test_top_level_models_are_public():
    assert tool.ReconstructionStrategy is analysis.ReconstructionStrategy
    assert tool.ReconstructionDecision is analysis.ReconstructionDecision
    assert tool.ReconstructedWave is analysis.ReconstructedWave
    assert tool.ReconstructedWaveSet is analysis.ReconstructedWaveSet


def test_top_level_functions_are_public():
    assert tool.reconstruct_selected_cycles is analysis.reconstruct_selected_cycles
    assert tool.analyze_audio_source_reconstruction is analysis.analyze_audio_source_reconstruction


def test_reconstruction_enum_values_are_canonical():
    assert [value.value for value in tool.ReconstructionStrategy] == [
        "auto",
        "spectral",
        "partial",
        "hybrid",
    ]
    assert [value.value for value in tool.ReconstructionDecision] == [
        "reconstructed",
        "no_selected_cycles",
    ]


def test_reconstruction_names_are_in_all_exports():
    names = {
        "ReconstructionStrategy",
        "ReconstructionDecision",
        "ReconstructedWave",
        "ReconstructedWaveSet",
        "reconstruct_selected_cycles",
        "analyze_audio_source_reconstruction",
    }
    assert names <= set(tool.__all__)
    assert names <= set(analysis.__all__)


def test_version_remains_0_5_0_until_v6_f():
    assert tool.__version__ == "0.5.0"
