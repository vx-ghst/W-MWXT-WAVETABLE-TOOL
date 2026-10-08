from __future__ import annotations

import inspect

import w_mwxt_wavetable_tool as root
import w_mwxt_wavetable_tool.wavetable as wavetable

EXPECTED = (
    "DEFAULT_KEYFRAME_SELECTION_POLICY",
    "WAVETABLE_SELECTION_SCHEMA_VERSION",
    "CandidateSelectionDecision",
    "CodeV8CAnalysis",
    "KeyframeSelectionPolicy",
    "KeyframeSelectionScore",
    "KeyframeSelectionStatus",
    "SelectionEvidenceKind",
    "WavetableKeyframeSelection",
    "evaluate_keyframe_subset",
    "select_wavetable_keyframes",
)


def test_v8c_symbols_are_exported_from_wavetable_package():
    for name in EXPECTED:
        assert hasattr(wavetable, name), name
        assert name in wavetable.__all__


def test_v8c_symbols_are_exported_from_package_root():
    for name in EXPECTED:
        assert hasattr(root, name), name
        assert name in root.__all__


def test_selection_functions_have_explicit_signatures():
    select_signature = inspect.signature(wavetable.select_wavetable_keyframes)
    score_signature = inspect.signature(wavetable.evaluate_keyframe_subset)
    assert tuple(select_signature.parameters) == ("request", "v8b_analysis", "policy")
    assert tuple(score_signature.parameters) == (
        "request",
        "v8b_analysis",
        "candidate_ids",
        "policy",
    )


def test_selection_api_does_not_expose_midi_or_sysex_names():
    names = {name.lower() for name in EXPECTED}
    assert not any("midi" in name or "sysex" in name for name in names)


def test_selection_schema_version_is_one():
    assert wavetable.WAVETABLE_SELECTION_SCHEMA_VERSION == 1
