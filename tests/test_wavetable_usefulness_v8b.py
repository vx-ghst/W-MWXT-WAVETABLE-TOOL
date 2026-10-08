from __future__ import annotations

import dataclasses
import json

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    BreakpointKind,
    CandidateStructureClass,
    IntervalClass,
    UsefulnessThresholds,
    WavetableContractError,
    analyze_candidate_structure,
)

from v8b_helpers import candidate, request, sine, square


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": 2},
        {"stable_distance": -0.1},
        {"transition_distance": 1.1},
        {"stable_distance": 0.2, "transition_distance": 0.1},
        {"transition_distance": 0.4, "breakpoint_distance": 0.3},
        {"extreme_edge_fraction": 0.6},
    ],
)
def test_usefulness_thresholds_reject_invalid_configuration(kwargs):
    with pytest.raises(WavetableContractError):
        UsefulnessThresholds(**kwargs)


def test_threshold_hash_is_deterministic():
    first = UsefulnessThresholds()
    second = UsefulnessThresholds()
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256


def test_source_order_uses_time_then_index_then_inventory():
    candidates = (
        candidate("late", sine(90, 4), source_index=9, source_time_seconds=0.9),
        candidate("early-b", sine(90, 2), source_index=2, source_time_seconds=0.1),
        candidate("early-a", sine(90, 1), source_index=1, source_time_seconds=0.1),
    )
    result = analyze_candidate_structure(request(candidates))
    assert result.source_order_candidate_ids == ("early-a", "early-b", "late")
    assert tuple(item.inventory_index for item in result.candidates) == (2, 1, 0)


def test_missing_time_is_ordered_after_timed_candidates():
    a = candidate("timed", sine(), source_index=1, source_time_seconds=0.1)
    b = dataclasses.replace(candidate("untimed", sine(90, 2), source_index=0), source_time_seconds=None)
    result = analyze_candidate_structure(request((b, a)))
    assert result.source_order_candidate_ids == ("timed", "untimed")


def test_single_candidate_has_no_interval_and_warning():
    result = analyze_candidate_structure(request((candidate("one", sine(), source_index=0),)))
    assert result.intervals == ()
    assert result.structural_candidate_ids == ("one",)
    assert any("Only one candidate" in warning for warning in result.warnings)


def test_identical_adjacent_candidates_form_stable_interval():
    samples = sine(100, 2)
    result = analyze_candidate_structure(request((
        candidate("a", samples, source_index=0),
        candidate("b", samples, source_index=1),
        candidate("c", samples, source_index=2),
    )))
    assert all(item.interval_class is IntervalClass.STABLE for item in result.intervals)
    assert result.candidates[1].structure_class is CandidateStructureClass.STABLE
    assert result.stable_candidate_ids == ("b",)


def test_distant_adjacent_candidates_form_breakpoint():
    thresholds = UsefulnessThresholds(stable_distance=0.01, transition_distance=0.02, breakpoint_distance=0.03)
    result = analyze_candidate_structure(request((
        candidate("sine", sine(110, 1), source_index=0),
        candidate("square", square(110, 11), source_index=1),
    )), thresholds)
    assert result.intervals[0].interval_class is IntervalClass.BREAKPOINT
    assert result.intervals[0].breakpoint_kinds
    assert set(result.breakpoint_candidate_ids) == {"sine", "square"}


def test_mid_distance_can_be_forced_to_transition():
    left = sine(100, 1)
    right = sine(100, 3)
    from w_mwxt_wavetable_tool.wavetable import compare_wave_shapes
    distance = compare_wave_shapes(left, right).perceptual_distance
    thresholds = UsefulnessThresholds(
        stable_distance=max(0.0, distance / 2.0),
        transition_distance=min(0.99, distance + 0.01),
        breakpoint_distance=min(1.0, distance + 0.10),
    )
    result = analyze_candidate_structure(request((
        candidate("a", left, source_index=0, structural_eligible=False),
        candidate("b", right, source_index=1, structural_eligible=False),
    )), thresholds)
    assert result.intervals[0].interval_class is IntervalClass.TRANSITION
    assert all(item.structure_class is CandidateStructureClass.INELIGIBLE for item in result.candidates)


def test_ineligible_candidate_never_becomes_structural():
    result = analyze_candidate_structure(request((
        candidate("a", sine(), source_index=0),
        candidate("x", square(), source_index=1, structural_eligible=False),
        candidate("b", sine(80, 8), source_index=2),
    )))
    x = next(item for item in result.candidates if item.candidate_id == "x")
    assert x.structure_class is CandidateStructureClass.INELIGIBLE
    assert x.structural_candidate is False
    assert "x" in result.ineligible_candidate_ids


def test_extreme_features_are_recorded_when_population_spans_metrics():
    candidates = (
        candidate("low", sine(50, 1), source_index=0, seed=0.0),
        candidate("middle", sine(80, 3), source_index=1, seed=0.25),
        candidate("high", square(120, 16), source_index=2, seed=0.55),
    )
    result = analyze_candidate_structure(request(candidates), UsefulnessThresholds(extreme_feature_span=0.05))
    extremes = {item.candidate_id: item.extreme_features for item in result.candidates}
    assert extremes["low"]
    assert extremes["high"]


def test_interval_hashes_are_linked_to_candidate_analyses():
    result = analyze_candidate_structure(request((
        candidate("a", sine(80, 1), source_index=0),
        candidate("b", sine(90, 3), source_index=1),
        candidate("c", square(100, 20), source_index=2),
    )))
    assert result.candidates[0].left_interval_sha256 is None
    assert result.candidates[0].right_interval_sha256 == result.intervals[0].analysis_sha256
    assert result.candidates[1].left_interval_sha256 == result.intervals[0].analysis_sha256
    assert result.candidates[1].right_interval_sha256 == result.intervals[1].analysis_sha256
    assert result.candidates[2].right_interval_sha256 is None


def test_structure_serialization_is_deterministic_and_explicitly_bounded():
    req = request((
        candidate("a", sine(80, 1), source_index=0),
        candidate("b", square(100, 20), source_index=1),
    ))
    first = analyze_candidate_structure(req)
    second = analyze_candidate_structure(req)
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256
    payload = first.to_dict()
    assert payload["analysis_sha256"] == first.analysis_sha256
    assert payload["boundaries"] == {
        "selects_keyframes": False,
        "assigns_user_positions": False,
        "orders_final_table": False,
        "interpolates_transitions": False,
        "materializes_wctd": False,
        "generates_sysex": False,
        "opens_midi_port": False,
        "transmits_midi": False,
    }
    assert json.loads(first.to_json())["analysis_sha256"] == first.analysis_sha256


def test_structure_models_are_frozen():
    result = analyze_candidate_structure(request((candidate("a", sine(), source_index=0),)))
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reason = "changed"  # type: ignore[misc]


def test_wrong_request_or_threshold_type_is_rejected():
    with pytest.raises(WavetableContractError, match="request"):
        analyze_candidate_structure(object())  # type: ignore[arg-type]
    with pytest.raises(WavetableContractError, match="thresholds"):
        analyze_candidate_structure(request((candidate("a", sine(), source_index=0),)), object())  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", list(BreakpointKind))
def test_breakpoint_kind_values_are_stable(kind):
    assert isinstance(kind.value, str)
    assert kind.value


@pytest.mark.parametrize("structure_class", list(CandidateStructureClass))
def test_structure_class_values_are_stable(structure_class):
    assert isinstance(structure_class.value, str)
    assert structure_class.value


def test_transition_threshold_distinguishes_moderate_and_strong_reasons():
    from w_mwxt_wavetable_tool.wavetable import compare_wave_shapes

    left = sine(100, 1)
    right = sine(100, 3)
    distance = compare_wave_shapes(left, right).perceptual_distance
    moderate = UsefulnessThresholds(
        stable_distance=max(0.0, distance / 3.0),
        transition_distance=min(0.99, distance + 0.01),
        breakpoint_distance=min(1.0, distance + 0.20),
    )
    strong = UsefulnessThresholds(
        stable_distance=max(0.0, distance / 3.0),
        transition_distance=max(0.0, distance - 0.01),
        breakpoint_distance=min(1.0, distance + 0.20),
    )
    req = request((candidate("a", left, source_index=0), candidate("b", right, source_index=1)))
    assert "moderate" in analyze_candidate_structure(req, moderate).intervals[0].reason
    assert "strong" in analyze_candidate_structure(req, strong).intervals[0].reason
