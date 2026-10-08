import inspect

import w_mwxt_wavetable_tool as public
import w_mwxt_wavetable_tool.wavetable as wavetable


PUBLIC_NAMES = (
    "FACTORY_PLACEMENT_SCHEMA_VERSION",
    "FactoryPlacementAnalysis",
    "FactoryPlacementStatus",
    "FactoryPlacementVariant",
    "FactoryZone",
    "FactoryZoneAssignment",
    "FactoryZoneTarget",
    "PlacementProfilePolicy",
    "build_factory_placement",
    "placement_profile_policy",
    "TRANSITION_SHAPING_SCHEMA_VERSION",
    "TransitionShapingAnalysis",
    "TransitionShapingPolicy",
    "apply_transition_shaping",
    "CODE_V8H_SCHEMA_VERSION",
    "CodeV8HAnalysis",
    "CodeV8HStatus",
    "CodeV8HVariant",
    "build_code_v8h",
)


def test_v8h_public_names_are_exported_at_both_levels():
    for name in PUBLIC_NAMES:
        assert hasattr(wavetable, name)
        assert hasattr(public, name)
        assert name in wavetable.__all__
        assert name in public.__all__


def test_v8h_entrypoint_signature_is_explicit():
    assert tuple(inspect.signature(wavetable.build_code_v8h).parameters) == (
        "request",
        "v8b_analysis",
        "v8c_analysis",
        "v8d_analysis",
        "region_interest_analysis",
        "placement_policy",
        "transition_shaping_policy",
        "transition_shaping_requested",
        "interpolation_policy",
        "density_policy",
        "continuity_thresholds",
        "slot_budget_policy",
        "oracle_thresholds",
    )
