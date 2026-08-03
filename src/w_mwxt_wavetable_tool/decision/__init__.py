"""Deterministic explainable decisions introduced by CODE V8."""

from .behavior_classifier import classify_behavior
from .explanations import (
    MODE_EXECUTION_PATHS,
    confidence_from_ranked_scores,
    execution_path_for_mode,
    validate_mode_execution_paths,
)
from .mode_selector import select_conversion_mode
from .models import (
    BehaviorClass,
    BehaviorClassification,
    BehaviorScore,
    ConversionMode,
    ModeDecision,
    ModeDecisionStatus,
    ModeExecutionPath,
    ModeScore,
    MusicalClass,
    MusicalClassification,
    MusicalClassScore,
)
from .musical_classifier import classify_musical_source

__all__ = [
    "MODE_EXECUTION_PATHS",
    "BehaviorClass",
    "BehaviorClassification",
    "BehaviorScore",
    "ConversionMode",
    "ModeDecision",
    "ModeDecisionStatus",
    "ModeExecutionPath",
    "ModeScore",
    "MusicalClass",
    "MusicalClassification",
    "MusicalClassScore",
    "classify_behavior",
    "classify_musical_source",
    "confidence_from_ranked_scores",
    "execution_path_for_mode",
    "select_conversion_mode",
    "validate_mode_execution_paths",
]
