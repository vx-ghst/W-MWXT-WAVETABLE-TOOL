from __future__ import annotations

import math
from typing import Iterable, Mapping

from .models import (
    PERCEPTUAL_FEATURE_NAMES,
    PerceptualDistance,
    PerceptualDistanceMatrix,
    PerceptualDistancePair,
    PerceptualFeatureDelta,
    PerceptualFeatureVector,
)


DEFAULT_WEIGHTS: dict[str, float] = {
    "low_frequency_power": 1.25,
    "fundamental_presence": 1.35,
    "brightness": 1.00,
    "hardness": 0.85,
    "saturation": 0.90,
    "density": 1.00,
    "motion": 1.10,
    "tonalness": 1.20,
    "noisiness": 1.00,
}


def _validated_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    selected = dict(DEFAULT_WEIGHTS if weights is None else weights)
    if tuple(selected) != PERCEPTUAL_FEATURE_NAMES:
        raise ValueError("weights must contain every feature in canonical order")
    for name, value in selected.items():
        checked = float(value)
        if not math.isfinite(checked) or checked <= 0.0:
            raise ValueError(f"weight {name} must be finite and positive")
    return selected


def perceptual_distance(
    left: PerceptualFeatureVector,
    right: PerceptualFeatureVector,
    *,
    weights: Mapping[str, float] | None = None,
    redundancy_threshold: float = 0.08,
) -> PerceptualDistance:
    if not isinstance(left, PerceptualFeatureVector) or not isinstance(
        right, PerceptualFeatureVector
    ):
        raise TypeError("left and right must be PerceptualFeatureVector instances")
    threshold = float(redundancy_threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("redundancy_threshold must be between 0 and 1")
    selected_weights = _validated_weights(weights)
    weighted_square_sum = 0.0
    weight_sum = 0.0
    deltas: list[PerceptualFeatureDelta] = []
    for name in PERCEPTUAL_FEATURE_NAMES:
        delta = abs(float(getattr(left, name)) - float(getattr(right, name)))
        weight = selected_weights[name]
        contribution = weight * delta * delta
        weighted_square_sum += contribution
        weight_sum += weight
        deltas.append(
            PerceptualFeatureDelta(
                name=name,
                absolute_delta=delta,
                weight=weight,
                weighted_contribution=contribution,
            )
        )
    distance = float(math.sqrt(weighted_square_sum / weight_sum))
    redundant = distance <= threshold
    reason = (
        "Weighted perceptual distance is below the audible-redundancy threshold."
        if redundant
        else "Weighted perceptual distance exceeds the audible-redundancy threshold."
    )
    return PerceptualDistance(
        schema_version=1,
        left_feature_sha256=left.analysis_sha256,
        right_feature_sha256=right.analysis_sha256,
        deltas=tuple(deltas),
        distance=distance,
        redundancy_threshold=threshold,
        audibly_redundant=redundant,
        reason=reason,
    )


def perceptual_distance_matrix(
    vectors: Iterable[PerceptualFeatureVector],
    *,
    weights: Mapping[str, float] | None = None,
    redundancy_threshold: float = 0.08,
) -> PerceptualDistanceMatrix:
    items = tuple(vectors)
    if len(items) < 2:
        raise ValueError("at least two perceptual vectors are required")
    pairs: list[PerceptualDistancePair] = []
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left_index: int, right_index: int) -> None:
        left_root = find(left_index)
        right_root = find(right_index)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    for left_index in range(len(items)):
        for right_index in range(left_index + 1, len(items)):
            distance = perceptual_distance(
                items[left_index],
                items[right_index],
                weights=weights,
                redundancy_threshold=redundancy_threshold,
            )
            pairs.append(
                PerceptualDistancePair(
                    left_index=left_index,
                    right_index=right_index,
                    distance=distance,
                )
            )
            if distance.audibly_redundant:
                union(left_index, right_index)

    grouped: dict[int, list[int]] = {}
    for index in range(len(items)):
        grouped.setdefault(find(index), []).append(index)
    redundant_groups = tuple(
        tuple(indexes)
        for _, indexes in sorted(grouped.items())
        if len(indexes) >= 2
    )
    return PerceptualDistanceMatrix(
        schema_version=1,
        feature_sha256=tuple(item.analysis_sha256 for item in items),
        pairs=tuple(pairs),
        redundant_groups=redundant_groups,
    )
