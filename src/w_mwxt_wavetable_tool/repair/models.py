from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any, Sequence

import numpy as np

from ..errors import AnalysisError


_EPSILON = 1.0e-12


class RepairDefect(str, Enum):
    DC_OFFSET = "dc_offset"
    CLIPPING = "clipping"
    ZERO_CROSSING = "zero_crossing"
    LOOP_DISCONTINUITY = "loop_discontinuity"
    DERIVATIVE_DISCONTINUITY = "derivative_discontinuity"
    PHASE_INVERSION = "phase_inversion"
    POLARITY_INVERSION = "polarity_inversion"
    START_END_MISMATCH = "start_end_mismatch"
    AMPLITUDE_INCONSISTENCY = "amplitude_inconsistency"
    CYCLE_LENGTH = "cycle_length"
    PITCH_ESTIMATE = "pitch_estimate"
    PARASITIC_NOISE = "parasitic_noise"
    FUNDAMENTAL_LOSS = "fundamental_loss"
    SPECTRAL_JUMP = "spectral_jump"
    INTER_WAVE_LEVEL_MISMATCH = "inter_wave_level_mismatch"
    REDUNDANT_WAVE = "redundant_wave"
    EXCESSIVE_ALIASING = "excessive_aliasing"


class RepairPolicy(str, Enum):
    AUTO = "auto"
    COMPARE = "compare"
    IGNORE = "ignore"
    PRESERVE = "preserve"


class RepairSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    BLOCKING = "blocking"


class RepairActionKind(str, Enum):
    REMOVE_DC = "remove_dc"
    RECONSTRUCT_CLIPPED_PEAKS = "reconstruct_clipped_peaks"
    ROTATE_TO_ZERO_CROSSING = "rotate_to_zero_crossing"
    SMOOTH_LOOP_SEAM = "smooth_loop_seam"
    SMOOTH_SEAM_DERIVATIVE = "smooth_seam_derivative"
    ALIGN_PHASE_TO_REFERENCE = "align_phase_to_reference"
    INVERT_POLARITY = "invert_polarity"
    REDUCE_START_END_MISMATCH = "reduce_start_end_mismatch"
    MATCH_REFERENCE_AMPLITUDE = "match_reference_amplitude"
    RESAMPLE_CYCLE_LENGTH = "resample_cycle_length"
    UPDATE_PITCH_ESTIMATE = "update_pitch_estimate"
    REDUCE_PARASITIC_NOISE = "reduce_parasitic_noise"
    RESTORE_FUNDAMENTAL = "restore_fundamental"
    SMOOTH_SPECTRAL_TRANSITION = "smooth_spectral_transition"
    MATCH_INTER_WAVE_LEVEL = "match_inter_wave_level"
    INTERPOLATE_REDUNDANT_WAVE = "interpolate_redundant_wave"
    REDUCE_ALIASING = "reduce_aliasing"


class RepairActionStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    APPLIED = "applied"
    PREVIEWED = "previewed"
    IGNORED = "ignored"
    PRESERVED = "preserved"
    REVIEW_REQUIRED = "review_required"


def _canonical_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


def _sample_hash(samples: Sequence[float]) -> str:
    array = np.asarray(tuple(float(value) for value in samples), dtype="<f8")
    return sha256(array.tobytes(order="C")).hexdigest()


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _finite(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked):
        raise AnalysisError(f"{name} must be finite")
    return checked


def _ratio(value: float, *, name: str) -> float:
    checked = _finite(value, name=name)
    if not 0.0 <= checked <= 1.0:
        raise AnalysisError(f"{name} must be between 0 and 1")
    return checked


def _normalized_text(value: str, *, name: str) -> str:
    if not value or value.strip() != value:
        raise AnalysisError(f"{name} must be a normalized non-empty string")
    return value


def _samples(
    values: Sequence[float] | None,
    *,
    name: str,
    allow_none: bool = False,
) -> tuple[float, ...] | None:
    if values is None:
        if allow_none:
            return None
        raise AnalysisError(f"{name} is required")
    result = tuple(float(value) for value in values)
    if len(result) < 2:
        raise AnalysisError(f"{name} must contain at least two samples")
    array = np.asarray(result, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise AnalysisError(f"{name} contains NaN or infinite values")
    if float(np.max(np.abs(array))) > 1.0 + _EPSILON:
        raise AnalysisError(f"{name} exceeds normalized range [-1, 1]")
    return result


@dataclass(frozen=True, slots=True)
class RepairThresholds:
    dc_ratio: float = 0.02
    clipping_ratio: float = 0.001
    zero_crossing_score: float = 0.05
    seam_value_score: float = 0.08
    seam_slope_score: float = 0.12
    phase_shift_ratio: float = 0.125
    polarity_correlation: float = -0.50
    start_end_score: float = 0.25
    amplitude_delta_db: float = 2.0
    pitch_error_cents: float = 50.0
    parasitic_noise_ratio: float = 0.15
    fundamental_ratio: float = 0.08
    spectral_jump: float = 0.10
    inter_wave_level_db: float = 2.0
    redundancy_correlation: float = 0.995
    redundancy_spectral_distance: float = 0.02
    aliasing_risk: float = 0.30

    def __post_init__(self) -> None:
        for name in (
            "dc_ratio",
            "clipping_ratio",
            "zero_crossing_score",
            "seam_value_score",
            "seam_slope_score",
            "phase_shift_ratio",
            "start_end_score",
            "parasitic_noise_ratio",
            "fundamental_ratio",
            "spectral_jump",
            "redundancy_correlation",
            "redundancy_spectral_distance",
            "aliasing_risk",
        ):
            _ratio(getattr(self, name), name=name)
        polarity = _finite(self.polarity_correlation, name="polarity_correlation")
        if not -1.0 <= polarity <= 0.0:
            raise AnalysisError("polarity_correlation must be between -1 and 0")
        for name in (
            "amplitude_delta_db",
            "pitch_error_cents",
            "inter_wave_level_db",
        ):
            if _finite(getattr(self, name), name=name) <= 0.0:
                raise AnalysisError(f"{name} must be positive")

    def to_dict(self) -> dict[str, float]:
        return {
            name: float(getattr(self, name))
            for name in self.__dataclass_fields__
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class RepairContext:
    expected_sample_count: int = 128
    detected_pitch_hz: float | None = None
    expected_pitch_hz: float | None = None
    reference_samples: tuple[float, ...] | None = None
    previous_samples: tuple[float, ...] | None = None
    next_samples: tuple[float, ...] | None = None
    target_rms: float | None = None
    aliasing_risk: float | None = None
    safe_harmonic_limit: int | None = None
    tonal_expected: bool = True
    source_label: str = "wave"

    def __post_init__(self) -> None:
        if self.expected_sample_count < 2:
            raise AnalysisError("expected_sample_count must be at least two")
        for name in ("detected_pitch_hz", "expected_pitch_hz"):
            value = getattr(self, name)
            if value is not None and _finite(value, name=name) <= 0.0:
                raise AnalysisError(f"{name} must be positive")
        for name in ("reference_samples", "previous_samples", "next_samples"):
            value = getattr(self, name)
            checked = _samples(value, name=name, allow_none=True)
            if checked is not None and len(checked) != self.expected_sample_count:
                raise AnalysisError(
                    f"{name} must contain expected_sample_count samples"
                )
        if self.target_rms is not None:
            target = _finite(self.target_rms, name="target_rms")
            if not 0.0 < target <= 1.0:
                raise AnalysisError("target_rms must be in (0, 1]")
        if self.aliasing_risk is not None:
            _ratio(self.aliasing_risk, name="aliasing_risk")
        if self.safe_harmonic_limit is not None and self.safe_harmonic_limit < 1:
            raise AnalysisError("safe_harmonic_limit must be positive")
        _normalized_text(self.source_label, name="source_label")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "expected_sample_count": self.expected_sample_count,
            "detected_pitch_hz": self.detected_pitch_hz,
            "expected_pitch_hz": self.expected_pitch_hz,
            "reference_samples_sha256": (
                None
                if self.reference_samples is None
                else _sample_hash(self.reference_samples)
            ),
            "previous_samples_sha256": (
                None
                if self.previous_samples is None
                else _sample_hash(self.previous_samples)
            ),
            "next_samples_sha256": (
                None if self.next_samples is None else _sample_hash(self.next_samples)
            ),
            "target_rms": self.target_rms,
            "aliasing_risk": self.aliasing_risk,
            "safe_harmonic_limit": self.safe_harmonic_limit,
            "tonal_expected": self.tonal_expected,
            "source_label": self.source_label,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class RepairFinding:
    defect: RepairDefect
    evaluated: bool
    detected: bool
    severity: RepairSeverity
    score: float
    threshold: float
    metrics: tuple[tuple[str, float], ...]
    recommended_action: RepairActionKind
    auto_safe: bool
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        _ratio(self.score, name="score")
        _ratio(self.threshold, name="threshold")
        if self.detected and not self.evaluated:
            raise AnalysisError("unevaluated findings cannot be detected")
        metric_names = tuple(name for name, _ in self.metrics)
        if len(set(metric_names)) != len(metric_names):
            raise AnalysisError("finding metric names must be unique")
        if any(not name or name.strip() != name for name in metric_names):
            raise AnalysisError("finding metric names must be normalized")
        for name, value in self.metrics:
            _finite(value, name=f"metric {name}")
        if not self.evidence or any(
            not item or item.strip() != item for item in self.evidence
        ):
            raise AnalysisError("finding evidence must contain normalized entries")
        _normalized_text(self.reason, name="reason")

    @property
    def metric_map(self) -> dict[str, float]:
        return dict(self.metrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "defect": self.defect.value,
            "evaluated": self.evaluated,
            "detected": self.detected,
            "severity": self.severity.value,
            "score": self.score,
            "threshold": self.threshold,
            "metrics": {name: value for name, value in self.metrics},
            "recommended_action": self.recommended_action.value,
            "auto_safe": self.auto_safe,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RepairPolicyRule:
    defect: RepairDefect
    policy: RepairPolicy

    def to_dict(self) -> dict[str, str]:
        return {"defect": self.defect.value, "policy": self.policy.value}


@dataclass(frozen=True, slots=True)
class RepairPolicySet:
    schema_version: int = 1
    default_policy: RepairPolicy = RepairPolicy.AUTO
    overrides: tuple[RepairPolicyRule, ...] = ()
    reason: str = "Default deterministic Auto Repair policy."

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported repair-policy schema version")
        defects = tuple(rule.defect for rule in self.overrides)
        if len(set(defects)) != len(defects):
            raise AnalysisError("repair policy overrides must be unique by defect")
        canonical = tuple(defect for defect in RepairDefect if defect in defects)
        if defects != canonical:
            raise AnalysisError("repair policy overrides must use canonical defect order")
        _normalized_text(self.reason, name="reason")

    def policy_for(self, defect: RepairDefect) -> RepairPolicy:
        for rule in self.overrides:
            if rule.defect is defect:
                return rule.policy
        return self.default_policy

    @property
    def policy_map(self) -> dict[str, str]:
        return {
            defect.value: self.policy_for(defect).value for defect in RepairDefect
        }

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default_policy": self.default_policy.value,
            "overrides": [rule.to_dict() for rule in self.overrides],
            "policy_map": self.policy_map,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class RepairWaveMetrics:
    sample_count: int
    sample_sha256: str
    mean: float
    rms: float
    peak: float
    clipping_ratio: float
    nearest_zero_ratio: float
    seam_value_ratio: float
    seam_slope_ratio: float
    fundamental_ratio: float
    high_band_ratio: float
    spectral_flatness: float

    def __post_init__(self) -> None:
        if self.sample_count < 2:
            raise AnalysisError("repair wave metrics require at least two samples")
        if not _hash_is_valid(self.sample_sha256):
            raise AnalysisError("sample_sha256 must be a SHA-256 digest")
        for name in ("mean", "rms", "peak"):
            value = _finite(getattr(self, name), name=name)
            if name != "mean" and value < 0.0:
                raise AnalysisError(f"{name} must not be negative")
        for name in (
            "clipping_ratio",
            "nearest_zero_ratio",
            "seam_value_ratio",
            "seam_slope_ratio",
            "fundamental_ratio",
            "high_band_ratio",
            "spectral_flatness",
        ):
            _ratio(getattr(self, name), name=name)

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "mean": self.mean,
            "rms": self.rms,
            "peak": self.peak,
            "clipping_ratio": self.clipping_ratio,
            "nearest_zero_ratio": self.nearest_zero_ratio,
            "seam_value_ratio": self.seam_value_ratio,
            "seam_slope_ratio": self.seam_slope_ratio,
            "fundamental_ratio": self.fundamental_ratio,
            "high_band_ratio": self.high_band_ratio,
            "spectral_flatness": self.spectral_flatness,
        }


@dataclass(frozen=True, slots=True)
class RepairActionRecord:
    defect: RepairDefect
    policy: RepairPolicy
    action: RepairActionKind
    status: RepairActionStatus
    before_samples_sha256: str
    candidate_samples_sha256: str
    changed: bool
    metadata_changed: bool
    parameters: tuple[tuple[str, float | int | str | bool | None], ...]
    improvement: float
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        for name in ("before_samples_sha256", "candidate_samples_sha256"):
            if not _hash_is_valid(getattr(self, name)):
                raise AnalysisError(f"{name} must be a SHA-256 digest")
        _ratio(self.improvement, name="improvement")
        parameter_names = tuple(name for name, _ in self.parameters)
        if len(set(parameter_names)) != len(parameter_names):
            raise AnalysisError("repair action parameters must be unique")
        if any(not name or name.strip() != name for name in parameter_names):
            raise AnalysisError("repair action parameter names must be normalized")
        for _, value in self.parameters:
            if isinstance(value, float) and not math.isfinite(value):
                raise AnalysisError("repair action parameter floats must be finite")
        if any(not item or item.strip() != item for item in self.warnings):
            raise AnalysisError("repair action warnings must be normalized")
        _normalized_text(self.reason, name="reason")
        if self.status is RepairActionStatus.APPLIED and self.policy is not RepairPolicy.AUTO:
            raise AnalysisError("only AUTO actions may be applied")
        if self.status is RepairActionStatus.PREVIEWED and self.policy is not RepairPolicy.COMPARE:
            raise AnalysisError("only COMPARE actions may be previewed")
        if self.status is RepairActionStatus.IGNORED and self.policy is not RepairPolicy.IGNORE:
            raise AnalysisError("ignored actions require IGNORE policy")
        if self.status is RepairActionStatus.PRESERVED and self.policy is not RepairPolicy.PRESERVE:
            raise AnalysisError("preserved actions require PRESERVE policy")
        if self.changed and self.before_samples_sha256 == self.candidate_samples_sha256:
            raise AnalysisError("changed action must change the sample hash")

    def to_dict(self) -> dict[str, Any]:
        return {
            "defect": self.defect.value,
            "policy": self.policy.value,
            "action": self.action.value,
            "status": self.status.value,
            "before_samples_sha256": self.before_samples_sha256,
            "candidate_samples_sha256": self.candidate_samples_sha256,
            "changed": self.changed,
            "metadata_changed": self.metadata_changed,
            "parameters": {name: value for name, value in self.parameters},
            "improvement": self.improvement,
            "warnings": list(self.warnings),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RepairComparison:
    schema_version: int
    before_samples: tuple[float, ...]
    candidate_samples: tuple[float, ...]
    selected_samples: tuple[float, ...]
    selected_is_candidate: bool
    before_metrics: RepairWaveMetrics
    candidate_metrics: RepairWaveMetrics
    selected_metrics: RepairWaveMetrics
    before_detected_count: int
    candidate_detected_count: int
    selected_detected_count: int
    improvement_score: float
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported repair-comparison schema version")
        before = _samples(self.before_samples, name="before_samples")
        candidate = _samples(self.candidate_samples, name="candidate_samples")
        selected = _samples(self.selected_samples, name="selected_samples")
        assert before is not None and candidate is not None and selected is not None
        if self.before_metrics.sample_sha256 != _sample_hash(before):
            raise AnalysisError("before metrics do not match before samples")
        if self.candidate_metrics.sample_sha256 != _sample_hash(candidate):
            raise AnalysisError("candidate metrics do not match candidate samples")
        if self.selected_metrics.sample_sha256 != _sample_hash(selected):
            raise AnalysisError("selected metrics do not match selected samples")
        if self.selected_is_candidate and selected != candidate:
            raise AnalysisError("selected candidate flag requires selected samples to equal candidate samples")
        for name in (
            "before_detected_count",
            "candidate_detected_count",
            "selected_detected_count",
        ):
            if int(getattr(self, name)) < 0:
                raise AnalysisError(f"{name} must not be negative")
        _ratio(self.improvement_score, name="improvement_score")
        _normalized_text(self.reason, name="reason")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "before_samples": list(self.before_samples),
            "candidate_samples": list(self.candidate_samples),
            "selected_samples": list(self.selected_samples),
            "selected_is_candidate": self.selected_is_candidate,
            "before_metrics": self.before_metrics.to_dict(),
            "candidate_metrics": self.candidate_metrics.to_dict(),
            "selected_metrics": self.selected_metrics.to_dict(),
            "before_detected_count": self.before_detected_count,
            "candidate_detected_count": self.candidate_detected_count,
            "selected_detected_count": self.selected_detected_count,
            "improvement_score": self.improvement_score,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class AutoRepairResult:
    schema_version: int
    source_samples_sha256: str
    context_sha256: str
    thresholds_sha256: str
    policy_set_sha256: str
    findings: tuple[RepairFinding, ...]
    actions: tuple[RepairActionRecord, ...]
    comparison: RepairComparison
    final_samples: tuple[float, ...]
    corrected_pitch_hz: float | None
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported Auto Repair result schema version")
        for name in (
            "source_samples_sha256",
            "context_sha256",
            "thresholds_sha256",
            "policy_set_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise AnalysisError(f"{name} must be a SHA-256 digest")
        if tuple(item.defect for item in self.findings) != tuple(RepairDefect):
            raise AnalysisError("findings must contain all defects in canonical order")
        if tuple(item.defect for item in self.actions) != tuple(RepairDefect):
            raise AnalysisError("actions must contain all defects in canonical order")
        final = _samples(self.final_samples, name="final_samples")
        assert final is not None
        if _sample_hash(final) != self.comparison.selected_metrics.sample_sha256:
            raise AnalysisError("final samples do not match selected comparison samples")
        if self.corrected_pitch_hz is not None:
            if _finite(self.corrected_pitch_hz, name="corrected_pitch_hz") <= 0.0:
                raise AnalysisError("corrected_pitch_hz must be positive")
        if any(not item or item.strip() != item for item in self.warnings):
            raise AnalysisError("Auto Repair warnings must be normalized")
        _normalized_text(self.reason, name="reason")

    @property
    def detected_defects(self) -> tuple[str, ...]:
        return tuple(item.defect.value for item in self.findings if item.detected)

    @property
    def applied_actions(self) -> tuple[str, ...]:
        return tuple(
            item.action.value
            for item in self.actions
            if item.status is RepairActionStatus.APPLIED
        )

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_samples_sha256": self.source_samples_sha256,
            "context_sha256": self.context_sha256,
            "thresholds_sha256": self.thresholds_sha256,
            "policy_set_sha256": self.policy_set_sha256,
            "findings": [item.to_dict() for item in self.findings],
            "actions": [item.to_dict() for item in self.actions],
            "comparison": self.comparison.to_dict(),
            "final_samples": list(self.final_samples),
            "corrected_pitch_hz": self.corrected_pitch_hz,
            "detected_defects": list(self.detected_defects),
            "applied_actions": list(self.applied_actions),
            "warnings": list(self.warnings),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class AutoRepairSequenceEntry:
    index: int
    result: AutoRepairResult

    def __post_init__(self) -> None:
        if self.index < 0:
            raise AnalysisError("sequence entry index must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "result": self.result.to_dict()}


@dataclass(frozen=True, slots=True)
class AutoRepairSequenceResult:
    schema_version: int
    entries: tuple[AutoRepairSequenceEntry, ...]
    policy_set_sha256: str
    thresholds_sha256: str
    before_sequence_sha256: str
    after_sequence_sha256: str
    detected_defect_count: int
    applied_action_count: int
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AnalysisError("Unsupported Auto Repair sequence schema version")
        if not self.entries:
            raise AnalysisError("Auto Repair sequence requires at least one entry")
        if tuple(entry.index for entry in self.entries) != tuple(range(len(self.entries))):
            raise AnalysisError("sequence entry indexes must be contiguous")
        for name in (
            "policy_set_sha256",
            "thresholds_sha256",
            "before_sequence_sha256",
            "after_sequence_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise AnalysisError(f"{name} must be a SHA-256 digest")
        expected_detected = sum(len(entry.result.detected_defects) for entry in self.entries)
        expected_applied = sum(len(entry.result.applied_actions) for entry in self.entries)
        if self.detected_defect_count != expected_detected:
            raise AnalysisError("detected_defect_count is inconsistent")
        if self.applied_action_count != expected_applied:
            raise AnalysisError("applied_action_count is inconsistent")
        _normalized_text(self.reason, name="reason")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entries": [entry.to_dict() for entry in self.entries],
            "policy_set_sha256": self.policy_set_sha256,
            "thresholds_sha256": self.thresholds_sha256,
            "before_sequence_sha256": self.before_sequence_sha256,
            "after_sequence_sha256": self.after_sequence_sha256,
            "detected_defect_count": self.detected_defect_count,
            "applied_action_count": self.applied_action_count,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


__all__ = [
    "AutoRepairResult",
    "AutoRepairSequenceEntry",
    "AutoRepairSequenceResult",
    "RepairActionKind",
    "RepairActionRecord",
    "RepairActionStatus",
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
]
