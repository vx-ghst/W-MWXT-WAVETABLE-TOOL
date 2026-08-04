from __future__ import annotations

import math
from typing import Iterable, Mapping

from .distances import perceptual_distance
from .models import PerceptualFeatureVector, SweepContinuityAnalysis, SweepTransition


def analyze_sweep_continuity(
    vectors: Iterable[PerceptualFeatureVector],
    *,
    weights: Mapping[str, float] | None = None,
    discontinuity_threshold: float = 0.25,
) -> SweepContinuityAnalysis:
    items = tuple(vectors)
    if not items:
        raise ValueError("at least one perceptual vector is required")
    threshold = float(discontinuity_threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("discontinuity_threshold must be between 0 and 1")

    transitions: list[SweepTransition] = []
    distances: list[float] = []
    for index, (left, right) in enumerate(zip(items, items[1:])):
        result = perceptual_distance(
            left,
            right,
            weights=weights,
            redundancy_threshold=0.0,
        )
        distances.append(result.distance)
        transitions.append(
            SweepTransition(
                index=index,
                left_feature_sha256=left.analysis_sha256,
                right_feature_sha256=right.analysis_sha256,
                distance=result.distance,
                discontinuity=result.distance > threshold,
            )
        )

    if distances:
        mean_distance = float(sum(distances) / len(distances))
        maximum_distance = max(distances)
        continuity = float(
            min(1.0, max(0.0, 1.0 - (0.65 * mean_distance + 0.35 * maximum_distance)))
        )
        discontinuity_count = sum(distance > threshold for distance in distances)
        reason = (
            "Adjacent perceptual distances were measured across the complete ordered sweep."
        )
    else:
        mean_distance = 0.0
        maximum_distance = 0.0
        continuity = 1.0
        discontinuity_count = 0
        reason = "A single-state sweep is continuous by definition."

    return SweepContinuityAnalysis(
        schema_version=1,
        feature_sha256=tuple(item.analysis_sha256 for item in items),
        discontinuity_threshold=threshold,
        transitions=tuple(transitions),
        mean_distance=mean_distance,
        maximum_distance=maximum_distance,
        continuity_score=continuity,
        discontinuity_count=discontinuity_count,
        reason=reason,
    )
