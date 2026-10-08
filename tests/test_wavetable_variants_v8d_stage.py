from __future__ import annotations

import gc
import pytest

from v8d_placement_helpers import (
    clear_placement_context_cache,
    placement_context,
    required_chronology,
    required_lock,
    variants_context,
)

from w_mwxt_wavetable_tool.wavetable import (
    CodeV8DStatus,
    KeyframeSelectionPolicy,
    PlacementStatus,
    build_wavetable_placement_variants,
)


@pytest.fixture(scope="module", autouse=True)
def _reset_v8d_context_cache():
    clear_placement_context_cache()
    gc.collect()
    yield
    clear_placement_context_cache()
    gc.collect()


@pytest.mark.parametrize("requested", (1, 2, 4, 6))
def test_requested_number_of_unique_variants_is_bounded_and_ranked(requested):
    _, _, _, result = variants_context(5, requested_variants=requested)
    assert result.status is CodeV8DStatus.COMPLETE
    assert 1 <= result.produced_variant_count <= requested
    assert tuple(item.rank for item in result.variants) == tuple(
        range(1, result.produced_variant_count + 1)
    )
    assert tuple(item.objective_score for item in result.variants) == tuple(
        sorted((item.objective_score for item in result.variants), reverse=True)
    )
    assert result.primary_variant is result.variants[0]


def test_variant_generation_is_deterministic():
    req, v8b, v8c = placement_context(5, requested_variants=4)
    first = build_wavetable_placement_variants(req, v8b, v8c)
    second = build_wavetable_placement_variants(req, v8b, v8c)
    assert first.analysis_sha256 == second.analysis_sha256
    assert tuple(item.analysis_sha256 for item in first.variants) == tuple(
        item.analysis_sha256 for item in second.variants
    )


def test_variants_have_unique_placement_signatures():
    _, _, _, result = variants_context(5, requested_variants=6)
    signatures = {
        tuple((item.candidate_id, item.position) for item in variant.placement.assignments)
        for variant in result.variants
    }
    assert len(signatures) == result.produced_variant_count


def test_alternative_variants_report_moved_candidates_and_delta():
    _, _, _, result = variants_context(5, requested_variants=4)
    assert result.variants[0].moved_candidate_ids == ()
    assert result.variants[0].mean_position_delta_from_primary == 0.0
    assert any(
        variant.moved_candidate_ids or variant.mean_position_delta_from_primary > 0.0
        for variant in result.variants[1:]
    )


def test_primary_variant_is_complete_and_links_ordering_to_placement():
    _, _, _, result = variants_context(8, requested_variants=3)
    primary = result.primary_variant
    assert primary is not None
    assert primary.placement.status is PlacementStatus.COMPLETE
    assert primary.placement.ordering_sha256 == primary.ordering.analysis_sha256
    assert primary.placement.assigned_candidate_ids == primary.ordering.ordered_candidate_ids


def test_infeasible_constraints_reject_all_variants_without_partial_output():
    locks = (required_lock(0, "c-000"), required_lock(1, "c-002"))
    chronology = (
        required_chronology("c-000", "c-001"),
        required_chronology("c-001", "c-002"),
    )
    req, v8b, v8c = placement_context(
        3,
        locks=locks,
        chronology=chronology,
        requested_variants=4,
    )
    result = build_wavetable_placement_variants(req, v8b, v8c)
    assert result.status is CodeV8DStatus.REJECTED
    assert result.variants == ()
    assert result.primary_variant_id is None
    assert result.blockers


def test_rejected_v8c_selection_rejects_v8d_without_partial_variants():
    locks = (required_lock(0, "c-000"), required_lock(60, "c-001"))
    req, v8b, v8c = placement_context(
        2,
        locks=locks,
        requested_variants=2,
        selection_policy=KeyframeSelectionPolicy(maximum_keyframes=1),
    )
    result = build_wavetable_placement_variants(req, v8b, v8c)
    assert result.status is CodeV8DStatus.REJECTED
    assert result.variants == ()
    assert result.blockers


def test_single_candidate_warns_when_fewer_unique_variants_exist():
    _, _, _, result = variants_context(1, requested_variants=6)
    assert result.status is CodeV8DStatus.COMPLETE
    assert result.produced_variant_count < 6
    assert any("unique feasible" in warning for warning in result.warnings)


def test_variant_boundaries_defer_interpolation_and_wctd():
    _, _, _, result = variants_context(5, requested_variants=2)
    boundaries = result.to_dict()["boundaries"]
    assert boundaries["orders_final_keyframes"] is True
    assert boundaries["assigns_user_positions"] is True
    assert boundaries["generates_placement_variants"] is True
    assert boundaries["interpolates_transitions"] is False
    assert boundaries["materializes_wctd"] is False


def test_primary_variant_is_global_best_independent_of_requested_count():
    _, _, _, single = variants_context(5, requested_variants=1)
    _, _, _, multiple = variants_context(5, requested_variants=6)
    assert single.primary_variant is not None
    assert multiple.primary_variant is not None
    assert single.primary_variant.ordering_strategy is multiple.primary_variant.ordering_strategy
    assert single.primary_variant.placement_bias is multiple.primary_variant.placement_bias
    assert single.primary_variant.objective_score == multiple.primary_variant.objective_score
