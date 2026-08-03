from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

import numpy as np

from .metrics import analyze_wave_shape, compare_wave_shapes
from .models import (
    WavetableBuild,
    WavetableBuildStatus,
    WavetableContractError,
    WavetableSlot,
    reconstruct_xt_cycle,
)

WAVETABLE_CONTINUITY_SCHEMA_VERSION = 1
_CONTINUITY_PRECISION = 12


def _q(value: float) -> float:
    return round(float(value), _CONTINUITY_PRECISION)


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _normalized(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise WavetableContractError(f"{name} must be a normalized non-empty string")
    return value


def _entries(values: Sequence[str], *, name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence")
    result = tuple(_normalized(value, name=f"{name} entry") for value in values)
    if not allow_empty and not result:
        raise WavetableContractError(f"{name} must not be empty")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


def _ratio(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked) or not 0.0 <= checked <= 1.0:
        raise WavetableContractError(f"{name} must be finite and between 0 and 1")
    return checked


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _fundamental(stored_samples: Sequence[int]) -> float:
    cycle = np.asarray(reconstruct_xt_cycle(stored_samples), dtype=np.float64) / 127.0
    spectrum = np.fft.rfft(cycle)
    if spectrum.size <= 1:
        return 0.0
    return float(min(1.0, abs(spectrum[1]) / (cycle.size / 2.0)))


class ContinuityStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ContinuityThresholds:
    schema_version: int = WAVETABLE_CONTINUITY_SCHEMA_VERSION
    warning_perceptual_distance: float = 0.34
    failure_perceptual_distance: float = 0.60
    warning_spectral_distance: float = 0.30
    failure_spectral_distance: float = 0.55
    warning_level_delta: float = 0.18
    failure_level_delta: float = 0.36
    warning_fundamental_delta: float = 0.22
    failure_fundamental_delta: float = 0.44
    warning_maximum_sample_distance: float = 0.52
    failure_maximum_sample_distance: float = 0.82
    failure_correlation_floor: float = -0.45

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONTINUITY_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported continuity-threshold schema version")
        pairs = (
            ("warning_perceptual_distance", "failure_perceptual_distance"),
            ("warning_spectral_distance", "failure_spectral_distance"),
            ("warning_level_delta", "failure_level_delta"),
            ("warning_fundamental_delta", "failure_fundamental_delta"),
            ("warning_maximum_sample_distance", "failure_maximum_sample_distance"),
        )
        for warning_name, failure_name in pairs:
            warning = _ratio(getattr(self, warning_name), name=warning_name)
            failure = _ratio(getattr(self, failure_name), name=failure_name)
            if warning >= failure:
                raise WavetableContractError(
                    f"{warning_name} must be smaller than {failure_name}"
                )
        floor = float(self.failure_correlation_floor)
        if not math.isfinite(floor) or not -1.0 <= floor <= 1.0:
            raise WavetableContractError("failure_correlation_floor must be in -1..1")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "warning_perceptual_distance": self.warning_perceptual_distance,
            "failure_perceptual_distance": self.failure_perceptual_distance,
            "warning_spectral_distance": self.warning_spectral_distance,
            "failure_spectral_distance": self.failure_spectral_distance,
            "warning_level_delta": self.warning_level_delta,
            "failure_level_delta": self.failure_level_delta,
            "warning_fundamental_delta": self.warning_fundamental_delta,
            "failure_fundamental_delta": self.failure_fundamental_delta,
            "warning_maximum_sample_distance": self.warning_maximum_sample_distance,
            "failure_maximum_sample_distance": self.failure_maximum_sample_distance,
            "failure_correlation_floor": self.failure_correlation_floor,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_CONTINUITY_THRESHOLDS = ContinuityThresholds()


@dataclass(frozen=True, slots=True)
class SlotContinuityAnalysis:
    schema_version: int
    left_position: int
    right_position: int
    left_slot_sha256: str
    right_slot_sha256: str
    waveform_distance: float
    spectral_distance: float
    perceptual_distance: float
    maximum_sample_distance: float
    correlation: float
    level_delta: float
    fundamental_delta: float
    continuity_score: float
    status: ContinuityStatus
    intentional_break: bool
    issues: tuple[str, ...]
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONTINUITY_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported slot-continuity schema version")
        if (
            isinstance(self.left_position, bool)
            or not isinstance(self.left_position, int)
            or isinstance(self.right_position, bool)
            or not isinstance(self.right_position, int)
            or self.right_position != self.left_position + 1
            or not 0 <= self.left_position < 60
        ):
            raise WavetableContractError("continuity positions must be adjacent within 0..60")
        _sha256(self.left_slot_sha256, name="left_slot_sha256")
        _sha256(self.right_slot_sha256, name="right_slot_sha256")
        for name in (
            "waveform_distance",
            "spectral_distance",
            "perceptual_distance",
            "maximum_sample_distance",
            "level_delta",
            "fundamental_delta",
            "continuity_score",
        ):
            _ratio(getattr(self, name), name=name)
        correlation = float(self.correlation)
        if not math.isfinite(correlation) or not -1.0 <= correlation <= 1.0:
            raise WavetableContractError("correlation must be finite and in -1..1")
        if not isinstance(self.status, ContinuityStatus):
            raise WavetableContractError("status must be ContinuityStatus")
        if not isinstance(self.intentional_break, bool):
            raise WavetableContractError("intentional_break must be boolean")
        object.__setattr__(self, "issues", _entries(self.issues, name="issues"))
        object.__setattr__(self, "evidence", _entries(self.evidence, name="evidence", allow_empty=False))
        _normalized(self.reason, name="reason")
        if self.status is ContinuityStatus.PASS and self.issues:
            raise WavetableContractError("passing continuity cannot contain issues")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "left_position": self.left_position,
            "left_display_position": self.left_position + 1,
            "right_position": self.right_position,
            "right_display_position": self.right_position + 1,
            "left_slot_sha256": self.left_slot_sha256,
            "right_slot_sha256": self.right_slot_sha256,
            "waveform_distance": self.waveform_distance,
            "spectral_distance": self.spectral_distance,
            "perceptual_distance": self.perceptual_distance,
            "maximum_sample_distance": self.maximum_sample_distance,
            "correlation": self.correlation,
            "level_delta": self.level_delta,
            "fundamental_delta": self.fundamental_delta,
            "continuity_score": self.continuity_score,
            "status": self.status.value,
            "intentional_break": self.intentional_break,
            "issues": list(self.issues),
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class WavetableContinuityReport:
    schema_version: int
    build_sha256: str
    thresholds: ContinuityThresholds
    transitions: tuple[SlotContinuityAnalysis, ...]
    status: ContinuityStatus
    pass_count: int
    warning_count: int
    failure_count: int
    mean_continuity_score: float
    minimum_continuity_score: float
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_CONTINUITY_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported continuity-report schema version")
        _sha256(self.build_sha256, name="build_sha256")
        if not isinstance(self.thresholds, ContinuityThresholds):
            raise WavetableContractError("thresholds must be ContinuityThresholds")
        transitions = tuple(self.transitions)
        object.__setattr__(self, "transitions", transitions)
        if len(transitions) != 60:
            raise WavetableContractError("complete continuity report requires 60 adjacent transitions")
        if any(not isinstance(item, SlotContinuityAnalysis) for item in transitions):
            raise WavetableContractError("transitions contain invalid values")
        if tuple(item.left_position for item in transitions) != tuple(range(60)):
            raise WavetableContractError("transitions must use canonical adjacent position order")
        if not isinstance(self.status, ContinuityStatus):
            raise WavetableContractError("status must be ContinuityStatus")
        counts = (self.pass_count, self.warning_count, self.failure_count)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
            raise WavetableContractError("continuity counts must be non-negative integers")
        if sum(counts) != len(transitions):
            raise WavetableContractError("continuity counts disagree with transitions")
        if self.pass_count != sum(item.status is ContinuityStatus.PASS for item in transitions):
            raise WavetableContractError("pass_count disagrees with transitions")
        if self.warning_count != sum(item.status is ContinuityStatus.WARNING for item in transitions):
            raise WavetableContractError("warning_count disagrees with transitions")
        if self.failure_count != sum(item.status is ContinuityStatus.FAIL for item in transitions):
            raise WavetableContractError("failure_count disagrees with transitions")
        _ratio(self.mean_continuity_score, name="mean_continuity_score")
        _ratio(self.minimum_continuity_score, name="minimum_continuity_score")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        object.__setattr__(self, "blockers", _entries(self.blockers, name="blockers"))
        _normalized(self.reason, name="reason")
        expected_status = (
            ContinuityStatus.FAIL
            if self.failure_count
            else ContinuityStatus.WARNING
            if self.warning_count
            else ContinuityStatus.PASS
        )
        if self.status is not expected_status:
            raise WavetableContractError("report status disagrees with transition counts")
        if self.status is ContinuityStatus.FAIL and not self.blockers:
            raise WavetableContractError("failed continuity report requires blockers")
        if self.status is not ContinuityStatus.FAIL and self.blockers:
            raise WavetableContractError("non-failed continuity report cannot contain blockers")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "build_sha256": self.build_sha256,
            "thresholds": self.thresholds.to_dict(),
            "transitions": [item.to_dict() for item in self.transitions],
            "status": self.status.value,
            "pass_count": self.pass_count,
            "warning_count": self.warning_count,
            "failure_count": self.failure_count,
            "mean_continuity_score": self.mean_continuity_score,
            "minimum_continuity_score": self.minimum_continuity_score,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def analyze_slot_continuity(
    left: WavetableSlot,
    right: WavetableSlot,
    thresholds: ContinuityThresholds = DEFAULT_CONTINUITY_THRESHOLDS,
    *,
    intentional_break: bool = False,
) -> SlotContinuityAnalysis:
    """Measure one adjacent slot transition with explicit warning/failure evidence."""

    if not isinstance(left, WavetableSlot) or not isinstance(right, WavetableSlot):
        raise WavetableContractError("left and right must be WavetableSlot values")
    if right.position != left.position + 1:
        raise WavetableContractError("slot continuity requires adjacent positions")
    if not isinstance(thresholds, ContinuityThresholds):
        raise WavetableContractError("thresholds must be ContinuityThresholds")
    if not isinstance(intentional_break, bool):
        raise WavetableContractError("intentional_break must be boolean")
    distance = compare_wave_shapes(left.stored_samples, right.stored_samples)
    left_shape = analyze_wave_shape(left.stored_samples)
    right_shape = analyze_wave_shape(right.stored_samples)
    level_delta = _q(min(1.0, abs(left_shape.rms - right_shape.rms)))
    fundamental_delta = _q(min(1.0, abs(_fundamental(left.stored_samples) - _fundamental(right.stored_samples))))
    failures: list[str] = []
    warnings: list[str] = []

    def classify(value: float, warning_limit: float, failure_limit: float, label: str) -> None:
        if value > failure_limit:
            failures.append(label)
        elif value > warning_limit:
            warnings.append(label)

    classify(
        distance.perceptual_distance,
        thresholds.warning_perceptual_distance,
        thresholds.failure_perceptual_distance,
        "perceptual distance",
    )
    classify(
        distance.spectral_distance,
        thresholds.warning_spectral_distance,
        thresholds.failure_spectral_distance,
        "spectral distance",
    )
    classify(
        level_delta,
        thresholds.warning_level_delta,
        thresholds.failure_level_delta,
        "level delta",
    )
    classify(
        fundamental_delta,
        thresholds.warning_fundamental_delta,
        thresholds.failure_fundamental_delta,
        "fundamental delta",
    )
    classify(
        distance.maximum_sample_distance,
        thresholds.warning_maximum_sample_distance,
        thresholds.failure_maximum_sample_distance,
        "maximum sample distance",
    )
    if distance.correlation < thresholds.failure_correlation_floor:
        failures.append("polarity correlation")
    failures = list(dict.fromkeys(failures))
    warnings = list(dict.fromkeys(warnings))
    if failures and intentional_break:
        warnings.extend(f"intentional {item}" for item in failures)
        failures = []
    issues = tuple(failures + warnings)
    status = (
        ContinuityStatus.FAIL
        if failures
        else ContinuityStatus.WARNING
        if warnings
        else ContinuityStatus.PASS
    )
    risk = (
        0.30 * distance.perceptual_distance
        + 0.20 * distance.spectral_distance
        + 0.15 * distance.maximum_sample_distance
        + 0.15 * level_delta
        + 0.10 * fundamental_delta
        + 0.10 * max(0.0, -distance.correlation)
    )
    score = _q(max(0.0, min(1.0, 1.0 - risk)))
    evidence = (
        f"left slot {left.slot_sha256}",
        f"right slot {right.slot_sha256}",
        f"perceptual distance {distance.perceptual_distance:.12f}",
        f"spectral distance {distance.spectral_distance:.12f}",
    )
    return SlotContinuityAnalysis(
        schema_version=WAVETABLE_CONTINUITY_SCHEMA_VERSION,
        left_position=left.position,
        right_position=right.position,
        left_slot_sha256=left.slot_sha256,
        right_slot_sha256=right.slot_sha256,
        waveform_distance=distance.waveform_distance,
        spectral_distance=distance.spectral_distance,
        perceptual_distance=distance.perceptual_distance,
        maximum_sample_distance=distance.maximum_sample_distance,
        correlation=distance.correlation,
        level_delta=level_delta,
        fundamental_delta=fundamental_delta,
        continuity_score=score,
        status=status,
        intentional_break=intentional_break,
        issues=issues,
        evidence=evidence,
        reason=(
            "Adjacent slot transition meets continuity thresholds."
            if status is ContinuityStatus.PASS
            else "Adjacent slot transition requires explicit continuity review."
            if status is ContinuityStatus.WARNING
            else "Adjacent slot transition exceeds mandatory continuity thresholds."
        ),
    )


def analyze_wavetable_continuity(
    build: WavetableBuild,
    thresholds: ContinuityThresholds = DEFAULT_CONTINUITY_THRESHOLDS,
    *,
    intentional_break_positions: Sequence[int] = (),
) -> WavetableContinuityReport:
    """Analyze all 60 adjacent transitions of one complete 61-slot V8-E build."""

    if not isinstance(build, WavetableBuild):
        raise WavetableContractError("build must be WavetableBuild")
    if build.status is not WavetableBuildStatus.COMPLETE:
        raise WavetableContractError("continuity requires a complete 61-slot build")
    if not isinstance(thresholds, ContinuityThresholds):
        raise WavetableContractError("thresholds must be ContinuityThresholds")
    intentional = tuple(intentional_break_positions)
    if any(
        isinstance(position, bool)
        or not isinstance(position, int)
        or not 0 <= position < 60
        for position in intentional
    ):
        raise WavetableContractError("intentional break positions must be integers 0..59")
    if len(set(intentional)) != len(intentional):
        raise WavetableContractError("intentional break positions must be unique")
    intentional_set = frozenset(intentional)
    transitions = tuple(
        analyze_slot_continuity(
            build.slots[position],
            build.slots[position + 1],
            thresholds,
            intentional_break=position in intentional_set,
        )
        for position in range(60)
    )
    pass_count = sum(item.status is ContinuityStatus.PASS for item in transitions)
    warning_count = sum(item.status is ContinuityStatus.WARNING for item in transitions)
    failure_count = sum(item.status is ContinuityStatus.FAIL for item in transitions)
    status = (
        ContinuityStatus.FAIL
        if failure_count
        else ContinuityStatus.WARNING
        if warning_count
        else ContinuityStatus.PASS
    )
    scores = tuple(item.continuity_score for item in transitions)
    warnings = tuple(
        f"positions {item.left_position + 1}-{item.right_position + 1}: {', '.join(item.issues)}"
        for item in transitions
        if item.status is ContinuityStatus.WARNING
    )
    blockers = tuple(
        f"positions {item.left_position + 1}-{item.right_position + 1}: {', '.join(item.issues)}"
        for item in transitions
        if item.status is ContinuityStatus.FAIL
    )
    return WavetableContinuityReport(
        schema_version=WAVETABLE_CONTINUITY_SCHEMA_VERSION,
        build_sha256=build.analysis_sha256,
        thresholds=thresholds,
        transitions=transitions,
        status=status,
        pass_count=pass_count,
        warning_count=warning_count,
        failure_count=failure_count,
        mean_continuity_score=_q(sum(scores) / len(scores)),
        minimum_continuity_score=_q(min(scores)),
        warnings=warnings,
        blockers=blockers,
        reason=(
            "Complete V8-E continuity report across all 61 editable positions."
        ),
    )


__all__ = [
    "DEFAULT_CONTINUITY_THRESHOLDS",
    "WAVETABLE_CONTINUITY_SCHEMA_VERSION",
    "ContinuityStatus",
    "ContinuityThresholds",
    "SlotContinuityAnalysis",
    "WavetableContinuityReport",
    "analyze_slot_continuity",
    "analyze_wavetable_continuity",
]
