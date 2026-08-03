from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    KeyframeSelectionPolicy,
    KeyframeSelectionStatus,
    WaveOrigin,
)
from v8c_selection_helpers import candidate, corpus, mixed_corpus, selection_for, sine


@pytest.mark.parametrize("count", [1, 2, 8, 61])
def test_below_or_equal_capacity_selects_every_distinct_candidate(count):
    _, _, result = selection_for(corpus(count))
    assert result.status is KeyframeSelectionStatus.COMPLETE
    assert len(result.selected_candidate_ids) == count
    assert result.selection.target_keyframe_count == count
    assert result.selection.omitted_candidate_ids == ()


def test_above_capacity_selects_exactly_61_without_positions():
    _, _, result = selection_for(corpus(62))
    assert result.status is KeyframeSelectionStatus.COMPLETE
    assert len(result.selected_candidate_ids) == 61
    assert len(result.selection.omitted_candidate_ids) == 1
    assert any("61-keyframe capacity" in warning for warning in result.warnings)
    assert result.selection.to_dict()["boundaries"]["assigns_user_positions"] is False


@pytest.mark.parametrize("requested", [1, 2, 3, 5, 8])
def test_explicit_requested_count_is_respected(requested):
    policy = KeyframeSelectionPolicy(
        requested_keyframe_count=requested,
        preserve_source_endpoints=requested != 1,
    )
    _, _, result = selection_for(corpus(10), policy=policy)
    assert result.status is KeyframeSelectionStatus.COMPLETE
    assert len(result.selected_candidate_ids) == requested


def test_request_larger_than_pool_selects_all_and_warns():
    policy = KeyframeSelectionPolicy(requested_keyframe_count=8)
    _, _, result = selection_for(corpus(3), policy=policy)
    assert len(result.selected_candidate_ids) == 3
    assert any("all available candidates" in warning for warning in result.warnings)


def test_exact_duplicates_collapse_to_one_group_representative():
    samples = sine(100, 2)
    items = (
        candidate("a", samples, source_index=0, usefulness=0.2),
        candidate("b", samples, source_index=1, usefulness=0.9),
    )
    _, _, result = selection_for(items)
    assert len(result.selected_candidate_ids) == 1
    assert result.selected_candidate_ids == ("b",)
    assert result.selection.omitted_candidate_ids == ("a",)


def test_mixed_real_and_reconstructed_inventory_is_preserved():
    _, _, result = selection_for(mixed_corpus(8))
    selected = {
        decision.candidate_id: decision
        for decision in result.selection.decisions
        if decision.selected
    }
    assert len(selected) == 8
    origins = {item.origin for item in mixed_corpus(8)}
    assert WaveOrigin.REPAIRED_REAL in origins
    assert WaveOrigin.REPAIRED_RECONSTRUCTED in origins


def test_selection_is_deterministic_across_runs():
    items = corpus(20)
    _, _, first = selection_for(items)
    _, _, second = selection_for(items)
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.selected_candidate_ids == second.selected_candidate_ids


def test_selected_ids_are_canonical_source_order_not_final_positions():
    items = tuple(reversed(corpus(8)))
    _, v8b, result = selection_for(items, policy=KeyframeSelectionPolicy(requested_keyframe_count=4))
    source_index = {
        candidate_id: index
        for index, candidate_id in enumerate(v8b.structure.source_order_candidate_ids)
    }
    assert list(result.selected_candidate_ids) == sorted(
        result.selected_candidate_ids, key=source_index.__getitem__
    )


def test_every_candidate_has_one_explicit_decision():
    _, _, result = selection_for(corpus(12), policy=KeyframeSelectionPolicy(requested_keyframe_count=5))
    assert len(result.selection.decisions) == 12
    assert {item.candidate_id for item in result.selection.decisions} == {
        f"c-{index:03d}" for index in range(12)
    }
    assert all(item.evidence and item.reason for item in result.selection.decisions)


def test_essential_set_is_non_empty_and_subset_of_selection():
    _, _, result = selection_for(corpus(8), policy=KeyframeSelectionPolicy(requested_keyframe_count=3))
    assert result.essential_candidate_ids
    assert set(result.essential_candidate_ids).issubset(result.selected_candidate_ids)


@pytest.mark.parametrize("preserve_endpoints", [True, False])
def test_endpoint_policy_is_explicit(preserve_endpoints):
    policy = KeyframeSelectionPolicy(
        requested_keyframe_count=3,
        preserve_source_endpoints=preserve_endpoints,
    )
    _, v8b, result = selection_for(corpus(8), policy=policy)
    first = v8b.structure.source_order_candidate_ids[0]
    last = v8b.structure.source_order_candidate_ids[-1]
    if preserve_endpoints:
        assert first in result.selected_candidate_ids
        assert last in result.selected_candidate_ids
