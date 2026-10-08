from __future__ import annotations

from itertools import combinations

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    KeyframeSelectionPolicy,
    WavetableContractError,
    analyze_wavetable_candidates,
    evaluate_keyframe_subset,
    select_wavetable_keyframes,
)
from v8c_selection_helpers import corpus, request, selection_for


def test_exact_search_matches_exhaustive_public_objective():
    items = corpus(7)
    req = request(items)
    v8b = analyze_wavetable_candidates(req)
    policy = KeyframeSelectionPolicy(
        requested_keyframe_count=4,
        preserve_source_endpoints=True,
        exact_search_candidate_limit=16,
        exact_search_combination_limit=50000,
    )
    result = select_wavetable_keyframes(req, v8b, policy)
    assert result.selection.exact_search_used
    endpoints = {
        v8b.structure.source_order_candidate_ids[0],
        v8b.structure.source_order_candidate_ids[-1],
    }
    alternatives = []
    for subset in combinations(v8b.structure.source_order_candidate_ids, 4):
        if endpoints.issubset(subset):
            alternatives.append(evaluate_keyframe_subset(req, v8b, subset, policy))
    best_score = max(item.objective_score for item in alternatives)
    assert result.selection.objective_score == best_score


@pytest.mark.parametrize("count,target", [(5, 2), (6, 3), (8, 4), (10, 5)])
def test_exact_search_is_used_for_small_combinatorial_cases(count, target):
    _, _, result = selection_for(
        corpus(count),
        policy=KeyframeSelectionPolicy(requested_keyframe_count=target),
    )
    assert result.selection.exact_search_used


def test_greedy_search_is_used_above_exact_limit():
    _, _, result = selection_for(
        corpus(20),
        policy=KeyframeSelectionPolicy(
            requested_keyframe_count=8,
            exact_search_candidate_limit=10,
        ),
    )
    assert not result.selection.exact_search_used


def test_subset_evaluation_is_order_independent_and_canonical():
    req = request(corpus(6))
    v8b = analyze_wavetable_candidates(req)
    first = evaluate_keyframe_subset(req, v8b, ("c-005", "c-000", "c-003"))
    second = evaluate_keyframe_subset(req, v8b, ("c-003", "c-005", "c-000"))
    assert first == second
    assert first.selected_candidate_ids == ("c-000", "c-003", "c-005")


def test_subset_evaluation_rejects_unknown_duplicate_and_empty_ids():
    req = request(corpus(3))
    v8b = analyze_wavetable_candidates(req)
    with pytest.raises(WavetableContractError):
        evaluate_keyframe_subset(req, v8b, ())
    with pytest.raises(WavetableContractError):
        evaluate_keyframe_subset(req, v8b, ("c-000", "c-000"))
    with pytest.raises(WavetableContractError, match="unknown"):
        evaluate_keyframe_subset(req, v8b, ("missing",))


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 8])
def test_objective_components_are_finite_bounded_and_hashable(count):
    req = request(corpus(count))
    v8b = analyze_wavetable_candidates(req)
    score = evaluate_keyframe_subset(req, v8b, v8b.structure.source_order_candidate_ids)
    values = (
        score.objective_score,
        score.utility_score,
        score.diversity_score,
        score.temporal_coverage_score,
        score.structural_coverage_score,
        score.group_coverage_score,
    )
    assert all(0.0 <= value <= 1.0 for value in values)
    assert len(score.analysis_sha256) == 64


def test_capacity_limited_selection_keeps_endpoint_coverage():
    req = request(corpus(20))
    v8b = analyze_wavetable_candidates(req)
    result = select_wavetable_keyframes(
        req,
        v8b,
        KeyframeSelectionPolicy(requested_keyframe_count=5),
    )
    assert v8b.structure.source_order_candidate_ids[0] in result.selected_candidate_ids
    assert v8b.structure.source_order_candidate_ids[-1] in result.selected_candidate_ids
    assert result.selection.temporal_coverage_score > 0.8
