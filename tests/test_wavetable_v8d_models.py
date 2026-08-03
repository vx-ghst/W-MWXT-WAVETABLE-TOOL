from __future__ import annotations

import gc
from dataclasses import FrozenInstanceError, replace
import json

import pytest

from v8d_placement_helpers import clear_placement_context_cache, ordered_context, variants_context

from w_mwxt_wavetable_tool.wavetable import (
    ConstraintOutcomeStatus,
    OrderingPolicy,
    OrderingStatus,
    OrderingStrategy,
    PlacementBias,
    PlacementPolicy,
    PlacementStatus,
    WAVETABLE_ORDERING_SCHEMA_VERSION,
    WAVETABLE_PLACEMENT_SCHEMA_VERSION,
    WAVETABLE_VARIANTS_SCHEMA_VERSION,
    WavetableContractError,
    ordering_policy_for_strategy,
)


@pytest.fixture(scope="module", autouse=True)
def _reset_v8d_context_cache():
    clear_placement_context_cache()
    gc.collect()
    yield
    clear_placement_context_cache()
    gc.collect()


@pytest.mark.parametrize(
    "value",
    (
        WAVETABLE_ORDERING_SCHEMA_VERSION,
        WAVETABLE_PLACEMENT_SCHEMA_VERSION,
        WAVETABLE_VARIANTS_SCHEMA_VERSION,
    ),
)
def test_v8d_schema_versions_are_one(value):
    assert value == 1


def test_ordering_policy_is_frozen_and_hashes_deterministically():
    policy = OrderingPolicy()
    assert policy.analysis_sha256 == OrderingPolicy().analysis_sha256
    with pytest.raises(FrozenInstanceError):
        policy.source_fidelity_weight = 0.5


@pytest.mark.parametrize(
    "kwargs",
    (
        {"schema_version": 2},
        {"source_fidelity_weight": -0.1},
        {"scan_smoothness_weight": 1.1},
        {"exact_search_candidate_limit": 0},
        {"exact_search_permutation_limit": 0},
        {"preserve_preference_chronology": 1},
    ),
)
def test_invalid_ordering_policy_values_are_rejected(kwargs):
    with pytest.raises(WavetableContractError):
        OrderingPolicy(**kwargs)


def test_ordering_policy_weights_must_sum_to_one():
    with pytest.raises(WavetableContractError, match="sum to one"):
        OrderingPolicy(source_fidelity_weight=0.25)


@pytest.mark.parametrize("strategy", tuple(OrderingStrategy))
def test_every_strategy_has_a_valid_distinct_policy(strategy):
    policy = ordering_policy_for_strategy(strategy)
    assert isinstance(policy, OrderingPolicy)
    weights = (
        policy.source_fidelity_weight,
        policy.scan_smoothness_weight,
        policy.harmonic_diversity_weight,
        policy.bass_strength_weight,
        policy.discontinuity_avoidance_weight,
    )
    assert sum(weights) == pytest.approx(1.0)


def test_strategy_factory_rejects_non_enum():
    with pytest.raises(WavetableContractError):
        ordering_policy_for_strategy("balanced")


def test_placement_policy_is_frozen_and_hashes_deterministically():
    policy = PlacementPolicy()
    assert policy.analysis_sha256 == PlacementPolicy().analysis_sha256
    with pytest.raises(FrozenInstanceError):
        policy.bias = PlacementBias.LATE


@pytest.mark.parametrize(
    "kwargs",
    (
        {"schema_version": 2},
        {"bias": "balanced"},
        {"ordering_weight": -0.1},
        {"spacing_weight": 1.1},
        {"honor_preference_locks": 1},
    ),
)
def test_invalid_placement_policy_values_are_rejected(kwargs):
    with pytest.raises(WavetableContractError):
        PlacementPolicy(**kwargs)


def test_placement_policy_weights_must_sum_to_one():
    with pytest.raises(WavetableContractError, match="sum to one"):
        PlacementPolicy(ordering_weight=0.5)


def test_complete_models_serialize_with_explicit_boundaries():
    _, _, _, ordering, placement = ordered_context(8)
    ordering_payload = json.loads(ordering.to_json())
    placement_payload = json.loads(placement.to_json())
    assert ordering_payload["boundaries"] == {
        "assigns_user_positions": False,
        "generates_sysex": False,
        "generates_variants": False,
        "interpolates_transitions": False,
        "materializes_wctd": False,
        "opens_midi_port": False,
        "orders_final_keyframes": True,
        "solves_required_chronology": True,
        "transmits_midi": False,
    }
    assert placement_payload["boundaries"]["assigns_selected_keyframes"] is True
    assert placement_payload["boundaries"]["interpolates_transitions"] is False
    assert placement_payload["boundaries"]["materializes_wctd"] is False


def test_variant_aggregate_serializes_and_links_primary():
    _, _, _, result = variants_context(5, requested_variants=4)
    payload = json.loads(result.to_json())
    assert payload["primary_variant_id"] == payload["variants"][0]["variant_id"]
    assert payload["produced_variant_count"] == 4
    assert payload["boundaries"]["generates_placement_variants"] is True
    assert payload["boundaries"]["interpolates_transitions"] is False


def test_ordering_and_placement_hashes_change_with_policy():
    req, v8b, v8c, ordering, placement = ordered_context(5)
    alternative_ordering = replace(
        ordering,
        strategy=OrderingStrategy.SOURCE_FIDELITY,
        policy=ordering_policy_for_strategy(OrderingStrategy.SOURCE_FIDELITY),
    )
    alternative_placement = replace(
        placement,
        policy=PlacementPolicy(bias=PlacementBias.LATE),
    )
    assert alternative_ordering.analysis_sha256 != ordering.analysis_sha256
    assert alternative_placement.analysis_sha256 != placement.analysis_sha256


def test_complete_statuses_and_constraint_outcomes_are_explicit():
    _, _, _, ordering, placement = ordered_context(2)
    assert ordering.status is OrderingStatus.COMPLETE
    assert placement.status is PlacementStatus.COMPLETE
    assert all(
        outcome.status in tuple(ConstraintOutcomeStatus)
        for outcome in placement.constraint_outcomes
    )
