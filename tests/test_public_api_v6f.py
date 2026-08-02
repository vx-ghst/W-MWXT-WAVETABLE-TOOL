from __future__ import annotations

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


def test_code_v6_model_is_public():
    assert tool.CodeV6Analysis is analysis.CodeV6Analysis


def test_code_v6_analyzer_is_public():
    assert tool.analyze_audio_source_code_v6 is analysis.analyze_audio_source_code_v6


def test_code_v6_assembler_is_public():
    assert tool.assemble_code_v6_analysis is analysis.assemble_code_v6_analysis


def test_code_v6_names_are_in_all_exports():
    names = {"CodeV6Analysis", "analyze_audio_source_code_v6", "assemble_code_v6_analysis"}
    assert names <= set(tool.__all__)
    assert names <= set(analysis.__all__)


def test_code_v6_release_contract_survives_code_v7_release():
    assert tool.__version__ == "0.7.0"
