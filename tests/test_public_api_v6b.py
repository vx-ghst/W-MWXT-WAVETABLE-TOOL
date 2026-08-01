from __future__ import annotations

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


def test_public_models_are_exported():
    for name in ("SegmentKind", "AttackPolicy", "AttackDecision", "SourceSegment", "SegmentationAnalysis"):
        assert getattr(tool, name) is getattr(analysis, name)


def test_public_functions_are_exported():
    assert tool.segment_source is analysis.segment_source
    assert tool.analyze_audio_source_segmentation is analysis.analyze_audio_source_segmentation


def test_analysis_all_contains_v6b_symbols():
    assert {"SegmentKind", "AttackPolicy", "AttackDecision", "SourceSegment", "SegmentationAnalysis", "segment_source", "analyze_audio_source_segmentation"} <= set(analysis.__all__)


def test_package_all_contains_v6b_symbols():
    assert {"SegmentKind", "AttackPolicy", "AttackDecision", "SourceSegment", "SegmentationAnalysis", "segment_source", "analyze_audio_source_segmentation"} <= set(tool.__all__)


def test_intermediate_gate_keeps_release_version():
    assert tool.__version__ == "0.6.0"
