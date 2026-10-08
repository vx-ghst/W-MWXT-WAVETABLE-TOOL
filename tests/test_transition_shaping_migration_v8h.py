import inspect

from w_mwxt_wavetable_tool import (
    DEFAULT_TRANSITION_SHAPING_POLICY,
    FactoryStylePolicy,
    TransitionShapingAnalysis,
    TransitionShapingPolicy,
    apply_factory_style,
    apply_transition_shaping,
)
from w_mwxt_wavetable_tool.wavetable.factory_style import (
    LegacyTransitionShapingAnalysis,
    LegacyTransitionShapingPolicy,
)


def test_transition_shaping_is_canonical_and_does_not_claim_factory_closure():
    data = DEFAULT_TRANSITION_SHAPING_POLICY.to_dict()
    assert data["semantic_role"] == "optional_post_transition_shaping"
    assert data["closes_factory_style_requirement"] is False
    assert tuple(inspect.signature(apply_transition_shaping).parameters) == (
        "request",
        "source_analysis",
        "policy",
        "requested",
    )


def test_v8f_factory_names_remain_deprecated_compatible_aliases():
    assert issubclass(FactoryStylePolicy, TransitionShapingPolicy)
    assert LegacyTransitionShapingPolicy is TransitionShapingPolicy
    assert LegacyTransitionShapingAnalysis is TransitionShapingAnalysis
    assert tuple(inspect.signature(apply_factory_style).parameters) == (
        "request",
        "v8e_analysis",
        "policy",
    )
    assert "semantic_role" not in FactoryStylePolicy().to_dict()
