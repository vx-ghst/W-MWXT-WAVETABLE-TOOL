from __future__ import annotations

import gc
from dataclasses import replace

import pytest

from v8d_placement_helpers import (
    clear_placement_context_cache,
    mixed_corpus,
    placement_context,
    preference_chronology,
    required_chronology,
    required_lock,
)

from w_mwxt_wavetable_tool.wavetable import (
    ConstraintOutcomeStatus,
    KeyframeSelectionPolicy,
    OrderingPolicy,
    OrderingStatus,
    OrderingStrategy,
    PlacementConstraintKind,
    WavetableContractError,
    evaluate_wavetable_order,
    order_wavetable_keyframes,
)


@pytest.fixture(scope="module", autouse=True)
def _reset_v8d_context_cache():
    clear_placement_context_cache()
    gc.collect()
    yield
    clear_placement_context_cache()
    gc.collect()


@pytest.mark.parametrize("count", (1, 2, 8))
def test_ordering_preserves_exact_v8c_selection_identity(count):
    req, v8b, v8c = placement_context(count)
    result = order_wavetable_keyframes(req, v8b, v8c)
    assert result.status is OrderingStatus.COMPLETE
    assert len(result.ordered_candidate_ids) == count
    assert set(result.ordered_candidate_ids) == set(v8c.selected_candidate_ids)
    assert tuple(item.candidate_id for item in result.entries) == result.ordered_candidate_ids


@pytest.mark.parametrize("count, exact", ((1, True), (2, True), (8, False)))
def test_ordering_reports_exact_or_greedy_search(count, exact):
    req, v8b, v8c = placement_context(count)
    result = order_wavetable_keyframes(req, v8b, v8c)
    assert result.exact_search_used is exact


@pytest.mark.parametrize("strategy", tuple(OrderingStrategy))
def test_all_ordering_strategies_produce_complete_deterministic_orders(strategy):
    req, v8b, v8c = placement_context(6)
    first = order_wavetable_keyframes(req, v8b, v8c, strategy)
    second = order_wavetable_keyframes(req, v8b, v8c, strategy)
    assert first.status is OrderingStatus.COMPLETE
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.ordered_candidate_ids == second.ordered_candidate_ids
    assert first.score is not None
    assert 0.0 <= first.score.objective_score <= 1.0


def test_required_chronology_is_satisfied_and_reported():
    chronology = (
        required_chronology("c-005", "c-002"),
        required_chronology("c-002", "c-007"),
    )
    req, v8b, v8c = placement_context(8, chronology=chronology)
    result = order_wavetable_keyframes(req, v8b, v8c)
    rank = {candidate_id: index for index, candidate_id in enumerate(result.ordered_candidate_ids)}
    assert rank["c-005"] < rank["c-002"] < rank["c-007"]
    required = [
        item
        for item in result.constraint_outcomes
        if item.kind is PlacementConstraintKind.CHRONOLOGY
    ]
    assert len(required) == 2
    assert all(item.status is ConstraintOutcomeStatus.SATISFIED for item in required)


def test_required_locks_constrain_relative_order_before_placement():
    locks = (
        required_lock(50, "c-000"),
        required_lock(10, "c-007"),
    )
    req, v8b, v8c = placement_context(8, locks=locks)
    result = order_wavetable_keyframes(req, v8b, v8c)
    rank = {candidate_id: index for index, candidate_id in enumerate(result.ordered_candidate_ids)}
    assert rank["c-007"] < rank["c-000"]


def test_preference_chronology_is_scored_but_not_a_hard_gate():
    chronology = (preference_chronology("c-004", "c-001"),)
    req, v8b, v8c = placement_context(6, chronology=chronology)
    result = order_wavetable_keyframes(req, v8b, v8c)
    preference = next(
        item for item in result.constraint_outcomes if item.kind is PlacementConstraintKind.CHRONOLOGY
    )
    assert preference.status in {
        ConstraintOutcomeStatus.SATISFIED,
        ConstraintOutcomeStatus.VIOLATED,
    }
    assert result.score is not None
    assert 0.0 <= result.score.preference_chronology_score <= 1.0


def test_mixed_real_and_reconstructed_candidates_are_preserved():
    candidates = mixed_corpus(8)
    req, v8b, v8c = placement_context(8, candidates=candidates)
    result = order_wavetable_keyframes(req, v8b, v8c)
    by_id = {candidate.candidate_id: candidate for candidate in req.candidates}
    origins = {by_id[candidate_id].origin for candidate_id in result.ordered_candidate_ids}
    assert len(origins) == 2
    assert set(result.ordered_candidate_ids) == set(v8c.selected_candidate_ids)


def test_evaluate_order_requires_an_exact_selection_permutation():
    req, v8b, v8c = placement_context(5)
    with pytest.raises(WavetableContractError, match="permutation"):
        evaluate_wavetable_order(req, v8b, v8c, v8c.selected_candidate_ids[:-1])


def test_evaluate_order_rejects_required_chronology_violation():
    chronology = (required_chronology("c-000", "c-004"),)
    req, v8b, v8c = placement_context(5, chronology=chronology)
    reversed_ids = tuple(reversed(v8c.selected_candidate_ids))
    with pytest.raises(WavetableContractError, match="chronology"):
        evaluate_wavetable_order(req, v8b, v8c, reversed_ids)


def test_rejected_v8c_selection_propagates_without_partial_order():
    locks = (required_lock(0, "c-000"), required_lock(60, "c-001"))
    req, v8b, v8c = placement_context(
        2,
        locks=locks,
        selection_policy=KeyframeSelectionPolicy(maximum_keyframes=1),
    )
    assert v8c.status.value == "rejected"
    result = order_wavetable_keyframes(req, v8b, v8c)
    assert result.status is OrderingStatus.REJECTED
    assert result.ordered_candidate_ids == ()
    assert result.entries == ()
    assert result.score is None
    assert result.blockers


def test_infeasible_lock_and_chronology_capacity_rejects_exact_order():
    locks = (required_lock(0, "c-000"), required_lock(1, "c-002"))
    chronology = (
        required_chronology("c-000", "c-001"),
        required_chronology("c-001", "c-002"),
    )
    req, v8b, v8c = placement_context(3, locks=locks, chronology=chronology)
    result = order_wavetable_keyframes(req, v8b, v8c)
    assert result.status is OrderingStatus.REJECTED
    assert result.ordered_candidate_ids == ()
    assert any("capacity" in blocker for blocker in result.blockers)


def test_ordering_policy_can_disable_preference_chronology_scoring():
    chronology = (preference_chronology("c-004", "c-001"),)
    req, v8b, v8c = placement_context(5, chronology=chronology)
    policy = replace(OrderingPolicy(), preserve_preference_chronology=False)
    result = order_wavetable_keyframes(
        req, v8b, v8c, OrderingStrategy.BALANCED, policy=policy
    )
    assert result.score is not None
    assert result.score.preference_chronology_score == 1.0
