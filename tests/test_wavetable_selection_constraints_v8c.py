from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    KeyframeSelectionPolicy,
    KeyframeSelectionStatus,
    SelectionEvidenceKind,
)
from v8c_selection_helpers import (
    candidate,
    corpus,
    request,
    required_chronology,
    required_lock,
    selection_for,
    sine,
)


def test_required_lock_candidate_is_forced_and_selected():
    items = corpus(10)
    _, _, result = selection_for(
        items,
        locks=(required_lock(10, "c-005"),),
        policy=KeyframeSelectionPolicy(requested_keyframe_count=3),
    )
    assert "c-005" in result.selected_candidate_ids
    assert "c-005" in result.selection.forced_candidate_ids
    decision = next(item for item in result.selection.decisions if item.candidate_id == "c-005")
    assert decision.forced
    assert SelectionEvidenceKind.REQUIRED_LOCK in decision.evidence_kinds


def test_required_chronology_participants_are_forced_without_solving_order():
    items = corpus(10)
    _, _, result = selection_for(
        items,
        chronology=(required_chronology("c-003", "c-007"),),
        policy=KeyframeSelectionPolicy(requested_keyframe_count=4),
    )
    assert {"c-003", "c-007"}.issubset(result.selected_candidate_ids)
    assert {"c-003", "c-007"}.issubset(result.selection.forced_candidate_ids)
    assert result.selection.to_dict()["boundaries"]["solves_chronology"] is False


def test_required_duplicate_is_preserved_even_when_not_representative():
    samples = sine(100, 2)
    items = (
        candidate("a", samples, source_index=0, usefulness=0.9),
        candidate("b", samples, source_index=1, usefulness=0.1),
        *corpus(4),
    )
    _, v8b, result = selection_for(
        items,
        chronology=(required_chronology("a", "b"),),
        policy=KeyframeSelectionPolicy(requested_keyframe_count=4),
    )
    assert v8b.deduplication.distinct_wave_count == 5
    assert {"a", "b"}.issubset(result.selected_candidate_ids)


def test_target_smaller_than_mandatory_set_is_rejected_without_partial_selection():
    items = corpus(6)
    chronology = (
        required_chronology("c-000", "c-001"),
        required_chronology("c-002", "c-003"),
    )
    _, _, result = selection_for(
        items,
        chronology=chronology,
        policy=KeyframeSelectionPolicy(requested_keyframe_count=3),
    )
    assert result.status is KeyframeSelectionStatus.REJECTED
    assert result.selected_candidate_ids == ()
    assert result.selection.essential_candidate_ids == ()
    assert result.selection.forced_candidate_ids == ()
    assert result.selection.blockers
    assert all(not decision.selected for decision in result.selection.decisions)


def test_more_than_61_required_candidates_is_rejected():
    items = corpus(62)
    locks = tuple(required_lock(index, f"c-{index:03d}") for index in range(61))
    chronology = (required_chronology("c-060", "c-061"),)
    _, _, result = selection_for(items, locks=locks, chronology=chronology)
    assert result.status is KeyframeSelectionStatus.REJECTED
    assert any("exceed" in blocker for blocker in result.selection.blockers)
    assert result.selected_candidate_ids == ()


def test_preference_constraints_do_not_force_selection():
    from w_mwxt_wavetable_tool.wavetable import (
        ChronologyConstraint,
        ConstraintStrength,
    )

    items = corpus(10)
    preference = ChronologyConstraint(
        before_candidate_id="c-004",
        after_candidate_id="c-005",
        strength=ConstraintStrength.PREFERENCE,
        reason="Preference only.",
    )
    _, _, result = selection_for(
        items,
        chronology=(preference,),
        policy=KeyframeSelectionPolicy(requested_keyframe_count=2),
    )
    assert result.status is KeyframeSelectionStatus.COMPLETE
    assert result.selection.forced_candidate_ids == ()


@pytest.mark.parametrize("position", [0, 1, 30, 60])
def test_required_lock_positions_remain_selection_only(position):
    items = corpus(8)
    _, _, result = selection_for(
        items,
        locks=(required_lock(position, "c-004"),),
        policy=KeyframeSelectionPolicy(requested_keyframe_count=3),
    )
    assert "c-004" in result.selected_candidate_ids
    assert "position" not in result.selection.to_dict()["decisions"][4]


def test_wrong_request_or_analysis_type_is_rejected():
    from w_mwxt_wavetable_tool.wavetable import (
        WavetableContractError,
        analyze_wavetable_candidates,
        select_wavetable_keyframes,
    )

    req = request(corpus(2))
    v8b = analyze_wavetable_candidates(req)
    with pytest.raises(WavetableContractError, match="request"):
        select_wavetable_keyframes(object(), v8b)  # type: ignore[arg-type]
    with pytest.raises(WavetableContractError, match="v8b"):
        select_wavetable_keyframes(req, object())  # type: ignore[arg-type]


def test_broken_v8b_request_link_is_rejected():
    from w_mwxt_wavetable_tool.wavetable import (
        WavetableContractError,
        analyze_wavetable_candidates,
        select_wavetable_keyframes,
    )

    first = request(corpus(2))
    second = request((candidate("other", sine(90, 3), source_index=0),))
    v8b = analyze_wavetable_candidates(first)
    with pytest.raises(WavetableContractError, match="does not link"):
        select_wavetable_keyframes(second, v8b)
