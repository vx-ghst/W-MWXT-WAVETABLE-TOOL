from __future__ import annotations

import w_mwxt_wavetable_tool as public
from w_mwxt_wavetable_tool import analysis


def test_analysis_api_exports_v5d_symbols():
    for name in (
        "DecisionStatus",
        "EngineeringDecision",
        "EngineeringRecommendation",
        "RecommendationCode",
        "RecommendationPriority",
        "decide_wavetable_readiness",
    ):
        assert hasattr(analysis, name)


def test_package_api_exports_v5d_symbols():
    for name in (
        "DecisionStatus",
        "EngineeringDecision",
        "EngineeringRecommendation",
        "RecommendationCode",
        "RecommendationPriority",
        "decide_wavetable_readiness",
    ):
        assert hasattr(public, name)


def test_all_contains_v5d_symbols():
    required = {
        "DecisionStatus",
        "EngineeringDecision",
        "EngineeringRecommendation",
        "RecommendationCode",
        "RecommendationPriority",
        "decide_wavetable_readiness",
    }
    assert required.issubset(set(public.__all__))
    assert required.issubset(set(analysis.__all__))
