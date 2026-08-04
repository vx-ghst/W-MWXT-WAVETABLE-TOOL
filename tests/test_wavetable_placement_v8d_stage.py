from __future__ import annotations

import gc
import pytest

from v8d_placement_helpers import (
    clear_placement_context_cache,
    mixed_corpus,
    placement_context,
    preference_lock,
    required_chronology,
    required_lock,
)

from w_mwxt_wavetable_tool.wavetable import (
    ConstraintOutcomeStatus,
    OrderingStatus,
    PlacementBias,
    PlacementConstraintKind,
    PlacementPolicy,
    PlacementStatus,
    order_wavetable_keyframes,
    place_wavetable_ordering,
)
from w_mwxt_wavetable_tool.wavetable.placement import _assign_positions


@pytest.fixture(scope="module", autouse=True)
def _release_cached_contexts_after_module():
    clear_placement_context_cache()
    gc.collect()
    yield
    clear_placement_context_cache()
    gc.collect()


@pytest.mark.parametrize(
    "count, expected",
    (
        (1, (30,)),
        (2, (0, 60)),
    ),
)
def test_balanced_placement_has_canonical_edge_behavior(count, expected):
    req, v8b, v8c = placement_context(count)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    placement = place_wavetable_ordering(req, v8b, v8c, ordering)
    assert placement.status is PlacementStatus.COMPLETE
    assert placement.occupied_positions == expected


@pytest.mark.parametrize("bias", tuple(PlacementBias))
def test_every_placement_bias_is_deterministic_and_order_preserving(bias):
    req, v8b, v8c = placement_context(8)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    policy = PlacementPolicy(bias=bias)
    first = place_wavetable_ordering(req, v8b, v8c, ordering, policy)
    second = place_wavetable_ordering(req, v8b, v8c, ordering, policy)
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.assigned_candidate_ids == ordering.ordered_candidate_ids
    assert first.occupied_positions == tuple(sorted(first.occupied_positions))
    assert len(first.occupied_positions) == 8


def test_sparse_placement_leaves_open_positions_for_v8e():
    req, v8b, v8c = placement_context(8)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    placement = place_wavetable_ordering(req, v8b, v8c, ordering)
    assert len(placement.assignments) == 8
    assert len(placement.open_positions) == 53
    assert set(placement.occupied_positions) | set(placement.open_positions) == set(range(61))
    assert placement.to_dict()["boundaries"]["interpolates_transitions"] is False


def test_required_position_locks_are_exactly_honored():
    locks = (required_lock(0, "c-000"), required_lock(60, "c-007"))
    req, v8b, v8c = placement_context(8, locks=locks)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    placement = place_wavetable_ordering(req, v8b, v8c, ordering)
    positions = {item.candidate_id: item.position for item in placement.assignments}
    assert positions["c-000"] == 0
    assert positions["c-007"] == 60
    lock_outcomes = [
        item
        for item in placement.constraint_outcomes
        if item.kind is PlacementConstraintKind.POSITION_LOCK
    ]
    assert all(item.status is ConstraintOutcomeStatus.SATISFIED for item in lock_outcomes)


def test_required_chronology_is_preserved_by_assigned_positions():
    chronology = (
        required_chronology("c-005", "c-002"),
        required_chronology("c-002", "c-007"),
    )
    req, v8b, v8c = placement_context(8, chronology=chronology)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    placement = place_wavetable_ordering(req, v8b, v8c, ordering)
    positions = {item.candidate_id: item.position for item in placement.assignments}
    assert positions["c-005"] < positions["c-002"] < positions["c-007"]


def test_feasible_preference_lock_is_honored_and_reported():
    locks = (preference_lock(30, "c-003"),)
    req, v8b, v8c = placement_context(8, locks=locks)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    placement = place_wavetable_ordering(req, v8b, v8c, ordering)
    assignment = next(item for item in placement.assignments if item.candidate_id == "c-003")
    outcome = next(
        item
        for item in placement.constraint_outcomes
        if item.kind is PlacementConstraintKind.POSITION_LOCK
    )
    assert assignment.position == 30
    assert assignment.preference_locked is True
    assert outcome.status is ConstraintOutcomeStatus.SATISFIED


def test_unhonored_preference_lock_is_reported_without_rejection():
    locks = (
        required_lock(0, "c-000"),
        preference_lock(1, "c-004"),
    )
    req, v8b, v8c = placement_context(5, locks=locks)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    placement = place_wavetable_ordering(req, v8b, v8c, ordering)
    assert placement.status is PlacementStatus.COMPLETE
    preference = next(
        item
        for item in placement.constraint_outcomes
        if item.strength.value == "preference"
    )
    assert preference.status is ConstraintOutcomeStatus.VIOLATED
    assert placement.warnings


def test_preference_locks_can_be_disabled_by_policy():
    locks = (preference_lock(30, "c-003"),)
    req, v8b, v8c = placement_context(8, locks=locks)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    placement = place_wavetable_ordering(
        req,
        v8b,
        v8c,
        ordering,
        PlacementPolicy(honor_preference_locks=False),
    )
    outcome = next(
        item
        for item in placement.constraint_outcomes
        if item.kind is PlacementConstraintKind.POSITION_LOCK
    )
    assert outcome.status is ConstraintOutcomeStatus.NOT_APPLICABLE


def test_rejected_ordering_propagates_without_partial_placement():
    locks = (required_lock(0, "c-000"), required_lock(1, "c-002"))
    chronology = (
        required_chronology("c-000", "c-001"),
        required_chronology("c-001", "c-002"),
    )
    req, v8b, v8c = placement_context(3, locks=locks, chronology=chronology)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    assert ordering.status is OrderingStatus.REJECTED
    placement = place_wavetable_ordering(req, v8b, v8c, ordering)
    assert placement.status is PlacementStatus.REJECTED
    assert placement.assignments == ()
    assert placement.occupied_positions == ()
    assert placement.open_positions == tuple(range(61))
    assert placement.score is None
    assert placement.blockers


def test_mixed_provenance_assignments_preserve_candidate_identity():
    req, v8b, v8c = placement_context(8, candidates=mixed_corpus(8))
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    placement = place_wavetable_ordering(req, v8b, v8c, ordering)
    assert placement.assigned_candidate_ids == ordering.ordered_candidate_ids
    assert set(placement.assigned_candidate_ids) == set(v8c.selected_candidate_ids)


def test_placement_score_terms_are_bounded_and_spacing_is_visible():
    req, v8b, v8c = placement_context(8)
    ordering = order_wavetable_keyframes(req, v8b, v8c)
    placement = place_wavetable_ordering(req, v8b, v8c, ordering)
    assert placement.score is not None
    assert 0.0 <= placement.score.objective_score <= 1.0
    assert 0.0 <= placement.score.spacing_evenness_score <= 1.0
    assert placement.score.mean_gap > 0.0
    assert placement.score.maximum_gap > 0


def test_position_solver_fills_all_61_editable_positions_without_interpolation():
    order = tuple(f"c-{index:03d}" for index in range(61))
    positions = _assign_positions(order, {}, PlacementBias.BALANCED)
    assert positions == tuple(range(61))


def test_position_solver_rejects_more_than_61_selected_candidates():
    order = tuple(f"c-{index:03d}" for index in range(62))
    with pytest.raises(Exception, match="capacity"):
        _assign_positions(order, {}, PlacementBias.BALANCED)
