from __future__ import annotations

import inspect

import w_mwxt_wavetable_tool as root
import w_mwxt_wavetable_tool.wavetable as wavetable

EXPECTED = (
    "DEFAULT_ORDERING_POLICY",
    "DEFAULT_PLACEMENT_POLICY",
    "WAVETABLE_ORDERING_SCHEMA_VERSION",
    "WAVETABLE_PLACEMENT_SCHEMA_VERSION",
    "WAVETABLE_VARIANTS_SCHEMA_VERSION",
    "ConstraintOutcome",
    "ConstraintOutcomeStatus",
    "OrderedCandidate",
    "OrderingPolicy",
    "OrderingScore",
    "OrderingStatus",
    "OrderingStrategy",
    "PlacementBias",
    "PlacementConstraintKind",
    "PlacementPolicy",
    "PlacementScore",
    "PlacementStatus",
    "PositionAssignment",
    "WavetableOrdering",
    "WavetablePlacement",
    "WavetablePlacementVariant",
    "CodeV8DAnalysis",
    "CodeV8DStatus",
    "evaluate_wavetable_order",
    "order_wavetable_keyframes",
    "ordering_policy_for_strategy",
    "place_wavetable_ordering",
    "build_wavetable_placement_variants",
)


def test_v8d_stage_symbols_are_exported_from_wavetable_package():
    for name in EXPECTED:
        assert hasattr(wavetable, name), name
        assert name in wavetable.__all__


def test_v8d_stage_symbols_are_exported_from_package_root():
    for name in EXPECTED:
        assert hasattr(root, name), name
        assert name in root.__all__


def test_ordering_functions_have_explicit_signatures():
    assert tuple(inspect.signature(wavetable.evaluate_wavetable_order).parameters) == (
        "request",
        "v8b_analysis",
        "v8c_analysis",
        "ordered_candidate_ids",
        "policy",
    )
    assert tuple(inspect.signature(wavetable.order_wavetable_keyframes).parameters) == (
        "request",
        "v8b_analysis",
        "v8c_analysis",
        "strategy",
        "policy",
    )


def test_placement_and_variant_functions_have_explicit_signatures():
    assert tuple(inspect.signature(wavetable.place_wavetable_ordering).parameters) == (
        "request",
        "v8b_analysis",
        "v8c_analysis",
        "ordering",
        "policy",
    )
    assert tuple(
        inspect.signature(wavetable.build_wavetable_placement_variants).parameters
    ) == ("request", "v8b_analysis", "v8c_analysis")


def test_v8d_stage_api_does_not_expose_midi_sysex_or_wctd_actions():
    names = {name.lower() for name in EXPECTED}
    assert not any(
        "midi" in name or "sysex" in name or "materialize" in name
        for name in names
    )


def test_v8d_stage_schema_versions_are_one():
    assert wavetable.WAVETABLE_ORDERING_SCHEMA_VERSION == 1
    assert wavetable.WAVETABLE_PLACEMENT_SCHEMA_VERSION == 1
    assert wavetable.WAVETABLE_VARIANTS_SCHEMA_VERSION == 1
