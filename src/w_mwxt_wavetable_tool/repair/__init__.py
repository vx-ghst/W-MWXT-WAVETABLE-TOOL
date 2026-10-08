"""Deterministic, policy-driven Auto Repair contracts introduced by CODE V8-0E."""

from .actions import RepairApplication, apply_repair_action
from .detectors import detect_wave_defects, measure_repair_wave
from .engine import auto_repair_wave, auto_repair_wave_sequence
from .models import (
    AutoRepairResult,
    AutoRepairSequenceEntry,
    AutoRepairSequenceResult,
    RepairActionKind,
    RepairActionRecord,
    RepairActionStatus,
    RepairComparison,
    RepairContext,
    RepairDefect,
    RepairFinding,
    RepairPolicy,
    RepairPolicyRule,
    RepairPolicySet,
    RepairSeverity,
    RepairThresholds,
    RepairWaveMetrics,
)
from .policy import (
    build_repair_policy_set,
    repair_policy_for_profile,
    replace_repair_policy,
)

__all__ = [
    "AutoRepairResult",
    "AutoRepairSequenceEntry",
    "AutoRepairSequenceResult",
    "RepairActionKind",
    "RepairActionRecord",
    "RepairActionStatus",
    "RepairApplication",
    "RepairComparison",
    "RepairContext",
    "RepairDefect",
    "RepairFinding",
    "RepairPolicy",
    "RepairPolicyRule",
    "RepairPolicySet",
    "RepairSeverity",
    "RepairThresholds",
    "RepairWaveMetrics",
    "apply_repair_action",
    "auto_repair_wave",
    "auto_repair_wave_sequence",
    "build_repair_policy_set",
    "detect_wave_defects",
    "measure_repair_wave",
    "repair_policy_for_profile",
    "replace_repair_policy",
]
