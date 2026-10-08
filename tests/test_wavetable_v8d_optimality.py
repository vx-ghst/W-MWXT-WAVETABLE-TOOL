from __future__ import annotations

import gc
from itertools import permutations

import pytest

from v8d_placement_helpers import (
    clear_placement_context_cache,
    placement_context,
    required_chronology,
    required_lock,
)

from w_mwxt_wavetable_tool.wavetable import (
    OrderingStrategy,
    WavetableContractError,
    evaluate_wavetable_order,
    order_wavetable_keyframes,
    ordering_policy_for_strategy,
)


def test_exact_small_case_matches_exhaustive_public_score():
    req, v8b, v8c = placement_context(5)
    policy = ordering_policy_for_strategy(OrderingStrategy.BALANCED)
    result = order_wavetable_keyframes(
        req, v8b, v8c, OrderingStrategy.BALANCED, policy=policy
    )
    scored = []
    for order in permutations(v8c.selected_candidate_ids):
        score = evaluate_wavetable_order(req, v8b, v8c, order, policy)
        scored.append((score.objective_score, order))
    best_score = max(item[0] for item in scored)
    assert result.exact_search_used is True
    assert result.score is not None
    assert result.score.objective_score == best_score


@pytest.fixture(scope="module", autouse=True)
def _reset_v8d_context_cache():
    clear_placement_context_cache()
    gc.collect()
    yield
    clear_placement_context_cache()
    gc.collect()


@pytest.mark.parametrize("strategy", tuple(OrderingStrategy))
def test_public_evaluator_reproduces_solver_score(strategy):
    req, v8b, v8c = placement_context(6)
    policy = ordering_policy_for_strategy(strategy)
    result = order_wavetable_keyframes(req, v8b, v8c, strategy, policy=policy)
    score = evaluate_wavetable_order(
        req, v8b, v8c, result.ordered_candidate_ids, policy
    )
    assert result.score == score
    assert result.score.analysis_sha256 == score.analysis_sha256


def test_required_lock_capacity_filters_infeasible_permutations():
    locks = (required_lock(0, "c-000"), required_lock(60, "c-004"))
    req, v8b, v8c = placement_context(5, locks=locks)
    with pytest.raises(WavetableContractError, match="locks"):
        evaluate_wavetable_order(
            req,
            v8b,
            v8c,
            tuple(reversed(v8c.selected_candidate_ids)),
        )


def test_required_chronology_filters_infeasible_permutations():
    chronology = (required_chronology("c-003", "c-001"),)
    req, v8b, v8c = placement_context(5, chronology=chronology)
    bad = tuple(
        sorted(
            v8c.selected_candidate_ids,
            key=lambda item: (item != "c-001", item != "c-003", item),
        )
    )
    assert bad.index("c-001") < bad.index("c-003")
    with pytest.raises(WavetableContractError, match="chronology"):
        evaluate_wavetable_order(req, v8b, v8c, bad)


def test_all_score_components_are_finite_and_bounded():
    req, v8b, v8c = placement_context(8)
    result = order_wavetable_keyframes(req, v8b, v8c)
    assert result.score is not None
    for value in (
        result.score.objective_score,
        result.score.source_fidelity_score,
        result.score.scan_smoothness_score,
        result.score.harmonic_diversity_score,
        result.score.bass_strength_score,
        result.score.discontinuity_avoidance_score,
        result.score.preference_chronology_score,
    ):
        assert 0.0 <= value <= 1.0
