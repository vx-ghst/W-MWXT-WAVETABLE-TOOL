"""Deterministic perceptual proxy contracts introduced by CODE V8-0C."""

from .distances import DEFAULT_WEIGHTS, perceptual_distance, perceptual_distance_matrix
from .features import analyze_perceptual_features
from .models import (
    PERCEPTUAL_FEATURE_NAMES,
    PerceptualDistance,
    PerceptualDistanceMatrix,
    PerceptualDistancePair,
    PerceptualFeatureDelta,
    PerceptualFeatureVector,
    SweepContinuityAnalysis,
    SweepTransition,
)
from .sweep import analyze_sweep_continuity

__all__ = [
    "DEFAULT_WEIGHTS",
    "PERCEPTUAL_FEATURE_NAMES",
    "PerceptualDistance",
    "PerceptualDistanceMatrix",
    "PerceptualDistancePair",
    "PerceptualFeatureDelta",
    "PerceptualFeatureVector",
    "SweepContinuityAnalysis",
    "SweepTransition",
    "analyze_perceptual_features",
    "analyze_sweep_continuity",
    "perceptual_distance",
    "perceptual_distance_matrix",
]
