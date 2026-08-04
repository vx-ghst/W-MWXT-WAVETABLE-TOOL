"""Effective optimization profiles introduced by CODE V8-0D."""

from .bass import (
    BassPitchComparison,
    BassPitchEvaluation,
    BassSequenceConsistency,
    analyze_bass_sequence_consistency,
    evaluate_bass_working_pitches,
)
from .factory import all_profile_definitions, profile_definition
from .models import (
    PROFILE_METRIC_NAMES,
    OptimizationProfile,
    ProfileDefinition,
    ProfileScore,
    ProfileSelection,
    ProfileWeights,
)
from .weights import canonical_profile_weights, weights_for_profile

__all__ = [
    "BassPitchComparison",
    "BassPitchEvaluation",
    "BassSequenceConsistency",
    "PROFILE_METRIC_NAMES",
    "OptimizationProfile",
    "ProfileDefinition",
    "ProfileScore",
    "ProfileSelection",
    "ProfileWeights",
    "all_profile_definitions",
    "analyze_bass_sequence_consistency",
    "evaluate_bass_working_pitches",
    "canonical_profile_weights",
    "profile_definition",
    "weights_for_profile",
]
