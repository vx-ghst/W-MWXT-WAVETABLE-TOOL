"""Factory Style public surface and V8-F migration aliases.

The canonical V8-H Factory Style operation is profile-driven keyframe placement
in the three non-overlapping XT zones exposed by :mod:`factory_placement`.

The original V8-F module used the name ``FactoryStyle`` for bounded sample-domain
transition smoothing.  Those names remain as deprecated aliases so existing
callers and historical tests keep working, but they map to
:mod:`transition_shaping` and do not close the Factory Style requirement.
"""
from __future__ import annotations

from .factory_placement import (
    FACTORY_PLACEMENT_SCHEMA_VERSION,
    CandidateTrajectoryFeatures,
    FactoryPlacementAnalysis,
    FactoryPlacementStatus,
    FactoryPlacementVariant,
    FactoryZone,
    FactoryZoneAssignment,
    FactoryZoneTarget,
    PlacementProfilePolicy,
    build_factory_placement,
    placement_profile_policy,
)
from .transition_shaping import (
    DEFAULT_TRANSITION_SHAPING_POLICY,
    DISABLED_TRANSITION_SHAPING_POLICY,
    TRANSITION_SHAPING_SCHEMA_VERSION,
    TransitionShapingAction,
    TransitionShapingAnalysis,
    TransitionShapingPolicy,
    TransitionShapingSlotDecision,
    TransitionShapingStatus,
    TransitionShapingVariant,
    apply_transition_shaping,
)

# Deprecated V8-F compatibility aliases.  They intentionally preserve the old
# runtime identity so isinstance/enum comparisons in downstream V8-F code remain
# valid while canonical V8-H code uses TransitionShaping* terminology.
FACTORY_STYLE_SCHEMA_VERSION = TRANSITION_SHAPING_SCHEMA_VERSION
FactoryStyleAction = TransitionShapingAction
FactoryStyleAnalysis = TransitionShapingAnalysis
class FactoryStylePolicy(TransitionShapingPolicy):
    """Deprecated V8-F policy name with its historical serialization shape."""

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "enabled": self.enabled,
            "smoothing_passes": self.smoothing_passes,
            "smoothing_strength": self.smoothing_strength,
            "neighbor_blend": self.neighbor_blend,
            "maximum_sample_delta": self.maximum_sample_delta,
            "require_non_worsening_continuity": self.require_non_worsening_continuity,
            "continuity_tolerance": self.continuity_tolerance,
        }

FactoryStyleSlotDecision = TransitionShapingSlotDecision
FactoryStyleStatus = TransitionShapingStatus
FactoryStyleVariant = TransitionShapingVariant
DEFAULT_FACTORY_STYLE_POLICY = FactoryStylePolicy()
DISABLED_FACTORY_STYLE_POLICY = FactoryStylePolicy(enabled=False)


# Explicit migration vocabulary used by the V8-H arbitration contract.
LegacyTransitionShapingAction = TransitionShapingAction
LegacyTransitionShapingAnalysis = TransitionShapingAnalysis
LegacyTransitionShapingPolicy = TransitionShapingPolicy
LegacyTransitionShapingSlotDecision = TransitionShapingSlotDecision
LegacyTransitionShapingStatus = TransitionShapingStatus
LegacyTransitionShapingVariant = TransitionShapingVariant
apply_legacy_transition_shaping = apply_transition_shaping


def apply_factory_style(request, v8e_analysis, policy=DEFAULT_FACTORY_STYLE_POLICY):
    """Deprecated V8-F wrapper for optional transition shaping."""
    return apply_transition_shaping(request, v8e_analysis, policy)

__all__ = [
    # Canonical V8-H Factory placement.
    "FACTORY_PLACEMENT_SCHEMA_VERSION",
    "CandidateTrajectoryFeatures",
    "FactoryPlacementAnalysis",
    "FactoryPlacementStatus",
    "FactoryPlacementVariant",
    "FactoryZone",
    "FactoryZoneAssignment",
    "FactoryZoneTarget",
    "PlacementProfilePolicy",
    "build_factory_placement",
    "placement_profile_policy",
    # Canonical optional transition shaping.
    "DEFAULT_TRANSITION_SHAPING_POLICY",
    "DISABLED_TRANSITION_SHAPING_POLICY",
    "TRANSITION_SHAPING_SCHEMA_VERSION",
    "TransitionShapingAction",
    "TransitionShapingAnalysis",
    "TransitionShapingPolicy",
    "TransitionShapingSlotDecision",
    "TransitionShapingStatus",
    "TransitionShapingVariant",
    "apply_transition_shaping",
    "apply_legacy_transition_shaping",
    "LegacyTransitionShapingVariant",
    "LegacyTransitionShapingStatus",
    "LegacyTransitionShapingSlotDecision",
    "LegacyTransitionShapingPolicy",
    "LegacyTransitionShapingAnalysis",
    "LegacyTransitionShapingAction",
    # Deprecated compatibility surface.
    "DEFAULT_FACTORY_STYLE_POLICY",
    "DISABLED_FACTORY_STYLE_POLICY",
    "FACTORY_STYLE_SCHEMA_VERSION",
    "FactoryStyleAction",
    "FactoryStyleAnalysis",
    "FactoryStylePolicy",
    "FactoryStyleSlotDecision",
    "FactoryStyleStatus",
    "FactoryStyleVariant",
    "apply_factory_style",
]
