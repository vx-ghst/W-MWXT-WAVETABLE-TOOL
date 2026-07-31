from __future__ import annotations

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


EXPECTED = (
    "ClassificationFeature",
    "SourceClass",
    "SourceClassScore",
    "SourceClassification",
    "classify_source",
)


def test_analysis_api_exports_v5c_contract():
    for name in EXPECTED:
        assert hasattr(analysis, name)
        assert name in analysis.__all__


def test_top_level_api_exports_v5c_contract():
    for name in EXPECTED:
        assert hasattr(tool, name)
        assert name in tool.__all__
