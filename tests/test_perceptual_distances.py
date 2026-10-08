from __future__ import annotations

from dataclasses import replace

import pytest

from v8c_helpers import build_bundle, deterministic_noise, tone
from w_mwxt_wavetable_tool.perceptual.distances import (
    DEFAULT_WEIGHTS,
    perceptual_distance,
    perceptual_distance_matrix,
)
from w_mwxt_wavetable_tool.perceptual.models import PERCEPTUAL_FEATURE_NAMES


def test_identical_vector_has_zero_distance_and_is_redundant() -> None:
    vector = build_bundle(tone()).perceptual
    result = perceptual_distance(vector, vector)
    assert result.distance == 0.0
    assert result.audibly_redundant
    assert all(delta.absolute_delta == 0.0 for delta in result.deltas)


def test_distance_is_symmetric() -> None:
    left = build_bundle(tone()).perceptual
    right = build_bundle(deterministic_noise()).perceptual
    forward = perceptual_distance(left, right)
    reverse = perceptual_distance(right, left)
    assert forward.distance == pytest.approx(reverse.distance)


def test_different_sources_exceed_default_redundancy_threshold() -> None:
    tonal = build_bundle(tone()).perceptual
    noise = build_bundle(deterministic_noise()).perceptual
    result = perceptual_distance(tonal, noise)
    assert result.distance > result.redundancy_threshold
    assert not result.audibly_redundant


def test_custom_weight_changes_distance_predictably() -> None:
    base = build_bundle(tone()).perceptual
    changed = replace(base, low_frequency_power=0.0 if base.low_frequency_power > 0.5 else 1.0)
    default = perceptual_distance(base, changed)
    weights = dict(DEFAULT_WEIGHTS)
    weights["low_frequency_power"] = 100.0
    weighted = perceptual_distance(base, changed, weights=weights)
    assert weighted.distance > default.distance


@pytest.mark.parametrize(
    "weights,match",
    [
        ({"brightness": 1.0}, "every feature"),
        ({**DEFAULT_WEIGHTS, "brightness": 0.0}, "positive"),
        ({**DEFAULT_WEIGHTS, "brightness": float("nan")}, "finite"),
    ],
)
def test_invalid_weight_maps_are_rejected(weights, match) -> None:
    vector = build_bundle(tone()).perceptual
    with pytest.raises(ValueError, match=match):
        perceptual_distance(vector, vector, weights=weights)


def test_matrix_contains_every_pair_in_canonical_order() -> None:
    first = build_bundle(tone()).perceptual
    second = replace(first, brightness=min(1.0, first.brightness + 0.01))
    third = build_bundle(deterministic_noise()).perceptual
    matrix = perceptual_distance_matrix((first, second, third))
    assert tuple((pair.left_index, pair.right_index) for pair in matrix.pairs) == (
        (0, 1),
        (0, 2),
        (1, 2),
    )
    assert matrix.redundant_groups == ((0, 1),)


def test_redundancy_groups_are_transitive() -> None:
    base = build_bundle(tone()).perceptual
    middle = replace(base, brightness=min(1.0, base.brightness + 0.03))
    end = replace(base, brightness=min(1.0, base.brightness + 0.06))
    matrix = perceptual_distance_matrix(
        (base, middle, end),
        redundancy_threshold=0.03,
    )
    assert matrix.redundant_groups == ((0, 1, 2),)


def test_distance_delta_order_is_canonical() -> None:
    vector = build_bundle(tone()).perceptual
    result = perceptual_distance(vector, vector)
    assert tuple(delta.name for delta in result.deltas) == PERCEPTUAL_FEATURE_NAMES


def test_matrix_requires_at_least_two_vectors() -> None:
    vector = build_bundle(tone()).perceptual
    with pytest.raises(ValueError, match="at least two"):
        perceptual_distance_matrix((vector,))
