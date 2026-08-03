from __future__ import annotations

import inspect

import w_mwxt_wavetable_tool as root
import w_mwxt_wavetable_tool.wavetable as wavetable

EXPECTED = (
    "DEFAULT_CONTINUITY_THRESHOLDS",
    "DEFAULT_INTERPOLATION_POLICY",
    "DEFAULT_TRANSITION_DENSITY_POLICY",
    "WAVETABLE_BUILDER_SCHEMA_VERSION",
    "WAVETABLE_CONTINUITY_SCHEMA_VERSION",
    "WAVETABLE_INTERPOLATION_SCHEMA_VERSION",
    "CodeV8EAnalysis",
    "CodeV8EStatus",
    "CodeV8EVariant",
    "ContinuityStatus",
    "ContinuityThresholds",
    "InterpolatedWave",
    "InterpolationPolicy",
    "SlotContinuityAnalysis",
    "TransitionDensityPolicy",
    "TransitionIntervalPlan",
    "TransitionPositionKind",
    "TransitionPositionRecord",
    "WavetableContinuityReport",
    "WavetableTransitionMap",
    "analyze_slot_continuity",
    "analyze_wavetable_continuity",
    "build_wavetable_transitions",
    "interpolate_xt_wave",
    "plan_transition_density",
    "progression_value",
    "select_interpolation_method",
)


def test_v8e_symbols_are_exported_from_wavetable_package():
    for name in EXPECTED:
        assert hasattr(wavetable, name), name
        assert name in wavetable.__all__


def test_v8e_symbols_are_exported_from_package_root():
    for name in EXPECTED:
        assert hasattr(root, name), name
        assert name in root.__all__


def test_v8e_function_signatures_are_explicit():
    assert tuple(inspect.signature(wavetable.interpolate_xt_wave).parameters) == (
        "left",
        "right",
        "progress",
        "method",
        "policy",
    )
    assert tuple(inspect.signature(wavetable.select_interpolation_method).parameters) == (
        "left",
        "right",
        "progress",
        "allowed_methods",
        "policy",
    )
    assert tuple(inspect.signature(wavetable.build_wavetable_transitions).parameters) == (
        "request",
        "v8b_analysis",
        "v8c_analysis",
        "v8d_analysis",
        "interpolation_policy",
        "density_policy",
        "continuity_thresholds",
    )


def test_v8e_schema_versions_are_one():
    assert wavetable.WAVETABLE_INTERPOLATION_SCHEMA_VERSION == 1
    assert wavetable.WAVETABLE_CONTINUITY_SCHEMA_VERSION == 1
    assert wavetable.WAVETABLE_BUILDER_SCHEMA_VERSION == 1


def test_v8e_api_does_not_expose_wctd_midi_or_sysex_execution_names():
    names = {name.lower() for name in EXPECTED}
    assert not any("midi" in name or "sysex" in name or "wctd" in name for name in names)
