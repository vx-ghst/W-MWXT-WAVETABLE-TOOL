from __future__ import annotations

import json
from dataclasses import replace

import pytest

from v8c_helpers import build_bundle, tone
from w_mwxt_wavetable_tool.perceptual.models import (
    PERCEPTUAL_FEATURE_NAMES,
    PerceptualDistance,
    PerceptualFeatureDelta,
    PerceptualFeatureVector,
    SweepContinuityAnalysis,
)


def test_feature_contract_has_exact_nine_canonical_features() -> None:
    assert PERCEPTUAL_FEATURE_NAMES == (
        "low_frequency_power",
        "fundamental_presence",
        "brightness",
        "hardness",
        "saturation",
        "density",
        "motion",
        "tonalness",
        "noisiness",
    )
    vector = build_bundle(tone()).perceptual
    assert tuple(vector.feature_map) == PERCEPTUAL_FEATURE_NAMES


def test_feature_model_is_json_safe_and_hash_stable() -> None:
    vector = build_bundle(tone()).perceptual
    rendered = json.dumps(vector.to_dict(), allow_nan=False, sort_keys=True)
    assert vector.analysis_sha256 in rendered
    assert len(vector.analysis_sha256) == 64


@pytest.mark.parametrize("name", PERCEPTUAL_FEATURE_NAMES)
def test_each_feature_rejects_out_of_range_values(name: str) -> None:
    vector = build_bundle(tone()).perceptual
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(vector, **{name: 1.1})


def test_feature_model_rejects_invalid_hash_and_empty_evidence() -> None:
    vector = build_bundle(tone()).perceptual
    with pytest.raises(ValueError, match="SHA-256"):
        replace(vector, sample_sha256="bad")
    with pytest.raises(ValueError, match="evidence"):
        replace(vector, evidence=())


def test_delta_model_requires_canonical_feature_name() -> None:
    with pytest.raises(ValueError, match="unknown"):
        PerceptualFeatureDelta(
            name="unknown",
            absolute_delta=0.1,
            weight=1.0,
            weighted_contribution=0.01,
        )


def test_distance_model_requires_redundancy_flag_consistency() -> None:
    vector = build_bundle(tone()).perceptual
    deltas = tuple(
        PerceptualFeatureDelta(
            name=name,
            absolute_delta=0.0,
            weight=1.0,
            weighted_contribution=0.0,
        )
        for name in PERCEPTUAL_FEATURE_NAMES
    )
    with pytest.raises(ValueError, match="inconsistent"):
        PerceptualDistance(
            schema_version=1,
            left_feature_sha256=vector.analysis_sha256,
            right_feature_sha256=vector.analysis_sha256,
            deltas=deltas,
            distance=0.0,
            redundancy_threshold=0.1,
            audibly_redundant=False,
            reason="Invalid flag on purpose.",
        )


def test_sweep_model_rejects_invalid_transition_count() -> None:
    vector = build_bundle(tone()).perceptual
    with pytest.raises(ValueError, match="transition count"):
        SweepContinuityAnalysis(
            schema_version=1,
            feature_sha256=(vector.analysis_sha256, vector.analysis_sha256),
            discontinuity_threshold=0.2,
            transitions=(),
            mean_distance=0.0,
            maximum_distance=0.0,
            continuity_score=1.0,
            discontinuity_count=0,
            reason="Invalid transition count on purpose.",
        )


def test_feature_vector_is_immutable() -> None:
    vector = build_bundle(tone()).perceptual
    with pytest.raises(Exception):
        vector.motion = 0.5  # type: ignore[misc]
