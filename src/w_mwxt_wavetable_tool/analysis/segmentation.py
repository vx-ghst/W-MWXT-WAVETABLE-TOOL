from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any

from ..version import __version__
from .repitch import WorkingPitchPlan, WorkingPitchPolicy, plan_working_pitch
from .signal import analyze_audio_source_signal


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _require_non_negative(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if result < 0.0:
        raise ValueError(f"{name} must not be negative")
    return result


def _require_ratio(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def _canonical_sha256(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


class SegmentKind(str, Enum):
    SILENCE = "silence"
    ATTACK = "attack"
    STEADY = "steady"
    TRANSITION = "transition"
    RELEASE = "release"


class AttackPolicy(str, Enum):
    AUTO = "auto"
    KEEP = "keep"
    REJECT = "reject"


class AttackDecision(str, Enum):
    KEEP = "keep"
    REJECT = "reject"
    NOT_PRESENT = "not_present"


@dataclass(frozen=True, slots=True)
class SourceSegment:
    index: int
    start_sample: int
    end_sample: int
    sample_rate: int
    kind: SegmentKind
    frame_start_index: int | None
    frame_end_index: int | None
    mean_rms: float
    peak_rms: float
    active_frame_ratio: float
    voiced_frame_ratio: float
    mean_spectral_flux: float
    maximum_onset_strength: float
    transient_count: int
    change_point_count: int
    start_boundary_reason: str
    end_boundary_reason: str
    classification_reason: str

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("index must not be negative")
        if self.start_sample < 0 or self.end_sample <= self.start_sample:
            raise ValueError("segment sample bounds are invalid")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if not isinstance(self.kind, SegmentKind):
            raise ValueError("kind must be a SegmentKind")
        if (self.frame_start_index is None) != (self.frame_end_index is None):
            raise ValueError("frame indexes must both be defined or both be absent")
        if self.frame_start_index is not None:
            if self.frame_start_index < 0 or self.frame_end_index < self.frame_start_index:
                raise ValueError("frame index range is invalid")
        for name in (
            "mean_rms",
            "peak_rms",
            "mean_spectral_flux",
            "maximum_onset_strength",
        ):
            _require_non_negative(getattr(self, name), name=name)
        _require_ratio(self.active_frame_ratio, name="active_frame_ratio")
        _require_ratio(self.voiced_frame_ratio, name="voiced_frame_ratio")
        if self.transient_count < 0 or self.change_point_count < 0:
            raise ValueError("event counts must not be negative")
        if not self.start_boundary_reason or not self.end_boundary_reason:
            raise ValueError("boundary reasons must not be empty")
        if not self.classification_reason:
            raise ValueError("classification_reason must not be empty")

    @property
    def duration_samples(self) -> int:
        return self.end_sample - self.start_sample

    @property
    def start_seconds(self) -> float:
        return float(self.start_sample / self.sample_rate)

    @property
    def end_seconds(self) -> float:
        return float(self.end_sample / self.sample_rate)

    @property
    def duration_seconds(self) -> float:
        return float(self.duration_samples / self.sample_rate)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "sample_rate": self.sample_rate,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration_samples": self.duration_samples,
            "duration_seconds": self.duration_seconds,
            "kind": self.kind.value,
            "frame_start_index": self.frame_start_index,
            "frame_end_index": self.frame_end_index,
            "mean_rms": self.mean_rms,
            "peak_rms": self.peak_rms,
            "active_frame_ratio": self.active_frame_ratio,
            "voiced_frame_ratio": self.voiced_frame_ratio,
            "mean_spectral_flux": self.mean_spectral_flux,
            "maximum_onset_strength": self.maximum_onset_strength,
            "transient_count": self.transient_count,
            "change_point_count": self.change_point_count,
            "start_boundary_reason": self.start_boundary_reason,
            "end_boundary_reason": self.end_boundary_reason,
            "classification_reason": self.classification_reason,
        }

    @property
    def segment_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["segment_sha256"] = self.segment_sha256
        return result


@dataclass(frozen=True, slots=True)
class SegmentationAnalysis:
    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    signal_analysis_sha256: str
    working_pitch_plan_sha256: str
    working_frequency_hz: float | None
    working_period_samples: float | None
    repitch_required: bool
    attack_policy: AttackPolicy
    attack_decision: AttackDecision
    minimum_segment_duration_ms: float
    boundary_merge_window_ms: float
    attack_window_ms: float
    maximum_attack_duration_ms: float
    minimum_attack_strength: float
    minimum_steady_duration_ms: float
    silence_rms_threshold: float
    transition_flux_threshold: float
    segments: tuple[SourceSegment, ...]
    attack_segment_index: int | None
    usable_segment_indices: tuple[int, ...]
    primary_sustain_segment_index: int | None
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported segmentation schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise ValueError("tool_version must be a non-empty normalized string")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in ("sample_sha256", "signal_analysis_sha256", "working_pitch_plan_sha256"):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        for name in (
            "minimum_segment_duration_ms",
            "boundary_merge_window_ms",
            "attack_window_ms",
            "maximum_attack_duration_ms",
            "minimum_attack_strength",
            "minimum_steady_duration_ms",
            "silence_rms_threshold",
            "transition_flux_threshold",
        ):
            _require_non_negative(getattr(self, name), name=name)
        if self.minimum_segment_duration_ms <= 0.0:
            raise ValueError("minimum_segment_duration_ms must be positive")
        if self.attack_window_ms <= 0.0 or self.maximum_attack_duration_ms <= 0.0:
            raise ValueError("attack durations must be positive")
        if self.minimum_steady_duration_ms <= 0.0:
            raise ValueError("minimum_steady_duration_ms must be positive")
        if not 0.0 <= self.transition_flux_threshold <= 1.0:
            raise ValueError("transition_flux_threshold must be between 0 and 1")
        if not self.segments:
            raise ValueError("segments must not be empty")
        if tuple(segment.index for segment in self.segments) != tuple(range(len(self.segments))):
            raise ValueError("segment indexes must be contiguous from zero")
        if self.segments[0].start_sample != 0 or self.segments[-1].end_sample != self.sample_count:
            raise ValueError("segments must cover the complete source")
        for left, right in zip(self.segments, self.segments[1:]):
            if left.end_sample != right.start_sample:
                raise ValueError("segments must be contiguous and non-overlapping")
        for segment in self.segments:
            if segment.sample_rate != self.sample_rate or segment.end_sample > self.sample_count:
                raise ValueError("segment identity is inconsistent")
        valid_indexes = set(range(len(self.segments)))
        if tuple(sorted(set(self.usable_segment_indices))) != self.usable_segment_indices:
            raise ValueError("usable_segment_indices must be sorted and unique")
        if any(index not in valid_indexes for index in self.usable_segment_indices):
            raise ValueError("usable segment index is outside the segment range")
        if self.attack_segment_index is None:
            if self.attack_decision is not AttackDecision.NOT_PRESENT:
                raise ValueError("missing attack segment requires NOT_PRESENT decision")
        else:
            if self.attack_segment_index not in valid_indexes:
                raise ValueError("attack_segment_index is outside the segment range")
            if self.segments[self.attack_segment_index].kind is not SegmentKind.ATTACK:
                raise ValueError("attack_segment_index must point to an attack segment")
            if self.attack_decision is AttackDecision.NOT_PRESENT:
                raise ValueError("present attack cannot use NOT_PRESENT decision")
        if self.attack_decision is AttackDecision.REJECT and self.attack_segment_index in self.usable_segment_indices:
            raise ValueError("rejected attack cannot be usable")
        if self.attack_decision is AttackDecision.KEEP and self.attack_segment_index not in self.usable_segment_indices:
            raise ValueError("kept attack must be usable")
        if self.primary_sustain_segment_index is not None:
            if self.primary_sustain_segment_index not in valid_indexes:
                raise ValueError("primary sustain index is outside the segment range")
            if self.primary_sustain_segment_index not in self.usable_segment_indices:
                raise ValueError("primary sustain segment must be usable")
        for name in ("working_frequency_hz", "working_period_samples"):
            value = getattr(self, name)
            if value is not None and _require_finite(value, name=name) <= 0.0:
                raise ValueError(f"{name} must be positive when defined")
        if not self.decision_reason:
            raise ValueError("decision_reason must not be empty")

    @property
    def segment_sha256(self) -> tuple[str, ...]:
        return tuple(segment.segment_sha256 for segment in self.segments)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "signal_analysis_sha256": self.signal_analysis_sha256,
            "working_pitch_plan_sha256": self.working_pitch_plan_sha256,
            "working_frequency_hz": self.working_frequency_hz,
            "working_period_samples": self.working_period_samples,
            "repitch_required": self.repitch_required,
            "attack_policy": self.attack_policy.value,
            "attack_decision": self.attack_decision.value,
            "minimum_segment_duration_ms": self.minimum_segment_duration_ms,
            "boundary_merge_window_ms": self.boundary_merge_window_ms,
            "attack_window_ms": self.attack_window_ms,
            "maximum_attack_duration_ms": self.maximum_attack_duration_ms,
            "minimum_attack_strength": self.minimum_attack_strength,
            "minimum_steady_duration_ms": self.minimum_steady_duration_ms,
            "silence_rms_threshold": self.silence_rms_threshold,
            "transition_flux_threshold": self.transition_flux_threshold,
            "segment_count": len(self.segments),
            "segment_sha256": list(self.segment_sha256),
            "segments": [segment.to_dict() for segment in self.segments],
            "attack_segment_index": self.attack_segment_index,
            "usable_segment_indices": list(self.usable_segment_indices),
            "primary_sustain_segment_index": self.primary_sustain_segment_index,
            "decision_reason": self.decision_reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _event_boundaries(transient: Any) -> list[tuple[int, str, float, bool]]:
    result: list[tuple[int, str, float, bool]] = []
    for event in transient.transients:
        result.append((int(event.sample_index), "transient", float(event.strength), False))
    for event in transient.change_points:
        result.append((int(event.sample_index), f"change:{event.kind}", float(event.score), False))
    return result


def _coalesce_boundaries(
    candidates: list[tuple[int, str, float, bool]],
    *,
    sample_count: int,
    merge_samples: int,
) -> list[tuple[int, str, float, bool]]:
    normalized = [
        (max(0, min(sample_count, int(sample))), reason, float(score), bool(protected))
        for sample, reason, score, protected in candidates
    ]
    normalized.extend(((0, "source_start", math.inf, True), (sample_count, "source_end", math.inf, True)))
    ranked = sorted(normalized, key=lambda item: (item[0], -int(item[3]), -item[2], item[1]))
    groups: list[list[tuple[int, str, float, bool]]] = []
    for candidate in ranked:
        if not groups or candidate[0] - groups[-1][-1][0] > merge_samples:
            groups.append([candidate])
        else:
            groups[-1].append(candidate)
    selected: list[tuple[int, str, float, bool]] = []
    for group in groups:
        protected = [item for item in group if item[3]]
        pool = protected or group
        chosen = sorted(pool, key=lambda item: (-item[2], item[0], item[1]))[0]
        selected.append(chosen)
    selected.sort(key=lambda item: item[0])
    return selected


def _enforce_minimum_duration(
    boundaries: list[tuple[int, str, float, bool]],
    *,
    minimum_samples: int,
) -> list[tuple[int, str, float, bool]]:
    result = [boundaries[0]]
    for boundary in boundaries[1:-1]:
        if boundary[0] - result[-1][0] < minimum_samples and not boundary[3]:
            continue
        result.append(boundary)
    result.append(boundaries[-1])
    while len(result) > 2 and result[-1][0] - result[-2][0] < minimum_samples and not result[-2][3]:
        result.pop(-2)
    return result


def _frame_center_sample(frame: Any, sample_rate: int) -> int:
    return int(round(float(frame.center_seconds) * sample_rate))


def _segment_frames(transient: Any, start: int, end: int, sample_rate: int) -> list[Any]:
    return [
        frame
        for frame in transient.frames
        if start <= _frame_center_sample(frame, sample_rate) < end
    ]


def _pitch_frames(signal_analysis: Any, start: int, end: int) -> list[Any]:
    pitch = signal_analysis.pitch_periodicity_analysis
    return [
        frame
        for frame in pitch.frames
        if start <= _frame_center_sample(frame, signal_analysis.sample_rate) < end
    ]


def segment_source(
    signal_analysis: Any,
    working_pitch_plan: WorkingPitchPlan,
    *,
    attack_policy: AttackPolicy | str = AttackPolicy.AUTO,
    minimum_segment_duration_ms: float = 40.0,
    boundary_merge_window_ms: float = 20.0,
    attack_window_ms: float = 120.0,
    maximum_attack_duration_ms: float = 250.0,
    minimum_attack_strength: float = 1.0,
    minimum_steady_duration_ms: float = 80.0,
    silence_rms_threshold: float = 1.0e-6,
    transition_flux_threshold: float = 0.20,
    tool_version: str = __version__,
) -> SegmentationAnalysis:
    """Create an explainable non-destructive segment and attack plan."""

    selected_policy = AttackPolicy(attack_policy)
    numeric = {
        "minimum_segment_duration_ms": minimum_segment_duration_ms,
        "boundary_merge_window_ms": boundary_merge_window_ms,
        "attack_window_ms": attack_window_ms,
        "maximum_attack_duration_ms": maximum_attack_duration_ms,
        "minimum_attack_strength": minimum_attack_strength,
        "minimum_steady_duration_ms": minimum_steady_duration_ms,
        "silence_rms_threshold": silence_rms_threshold,
        "transition_flux_threshold": transition_flux_threshold,
    }
    for name, value in numeric.items():
        _require_non_negative(value, name=name)
    if minimum_segment_duration_ms <= 0.0:
        raise ValueError("minimum_segment_duration_ms must be positive")
    if attack_window_ms <= 0.0 or maximum_attack_duration_ms <= 0.0:
        raise ValueError("attack durations must be positive")
    if minimum_steady_duration_ms <= 0.0:
        raise ValueError("minimum_steady_duration_ms must be positive")
    if not 0.0 <= transition_flux_threshold <= 1.0:
        raise ValueError("transition_flux_threshold must be between 0 and 1")
    if not tool_version or tool_version.strip() != tool_version:
        raise ValueError("tool_version must be a non-empty normalized string")

    for name in ("sample_rate", "sample_count", "sample_sha256", "analysis_sha256"):
        if not hasattr(signal_analysis, name):
            raise ValueError(f"signal_analysis is missing {name}")
    if signal_analysis.sample_rate != working_pitch_plan.sample_rate:
        raise ValueError("working-pitch plan has an inconsistent sample rate")
    if signal_analysis.sample_count != working_pitch_plan.sample_count:
        raise ValueError("working-pitch plan has an inconsistent sample count")
    if signal_analysis.sample_sha256 != working_pitch_plan.sample_sha256:
        raise ValueError("working-pitch plan has an inconsistent sample hash")
    pitch_hash = signal_analysis.pitch_periodicity_analysis.analysis_sha256
    if working_pitch_plan.pitch_periodicity_analysis_sha256 != pitch_hash:
        raise ValueError("working-pitch plan does not link to signal pitch analysis")

    sample_rate = int(signal_analysis.sample_rate)
    sample_count = int(signal_analysis.sample_count)
    transient = signal_analysis.transient_change_analysis
    if transient.sample_sha256 != signal_analysis.sample_sha256:
        raise ValueError("transient analysis has an inconsistent sample hash")

    minimum_samples = max(1, int(round(minimum_segment_duration_ms * sample_rate / 1000.0)))
    merge_samples = max(0, int(round(boundary_merge_window_ms * sample_rate / 1000.0)))
    attack_window_samples = max(1, int(round(attack_window_ms * sample_rate / 1000.0)))
    maximum_attack_samples = max(1, int(round(maximum_attack_duration_ms * sample_rate / 1000.0)))

    active_frames = [frame for frame in transient.frames if float(frame.rms) > silence_rms_threshold]
    active_start = None if not active_frames else int(active_frames[0].start_sample)
    active_end = None if not active_frames else min(sample_count, int(active_frames[-1].start_sample + active_frames[-1].sample_count))

    candidates = _event_boundaries(transient)
    attack_present = False
    attack_end = None
    if active_start is not None:
        nearby = [
            event
            for event in transient.transients
            if active_start <= int(event.sample_index) <= active_start + attack_window_samples
            and float(event.strength) >= minimum_attack_strength
        ]
        if nearby:
            attack_present = True
            limit = min(sample_count, active_start + maximum_attack_samples)
            post_events = sorted(
                int(event.sample_index)
                for event in transient.change_points
                if active_start + minimum_samples <= int(event.sample_index) <= limit
            )
            attack_end = post_events[0] if post_events else min(limit, active_start + attack_window_samples)
            if attack_end <= active_start:
                attack_end = min(sample_count, active_start + minimum_samples)
            candidates = [
                candidate
                for candidate in candidates
                if not active_start < candidate[0] < attack_end
            ]
            candidates.append((active_start, "active_start", math.inf, True))
            candidates.append((attack_end, "attack_end", math.inf, True))
    if active_start is not None and active_start > 0:
        candidates.append((active_start, "active_start", math.inf, True))
    if active_end is not None and active_end < sample_count:
        candidates.append((active_end, "active_end", math.inf, True))

    boundaries = _coalesce_boundaries(candidates, sample_count=sample_count, merge_samples=merge_samples)
    boundaries = _enforce_minimum_duration(boundaries, minimum_samples=minimum_samples)

    segments: list[SourceSegment] = []
    attack_segment_index: int | None = None
    for index, (left, right) in enumerate(zip(boundaries, boundaries[1:])):
        start, end = left[0], right[0]
        frames = _segment_frames(transient, start, end, sample_rate)
        pitch_frames = _pitch_frames(signal_analysis, start, end)
        rms_values = [float(frame.rms) for frame in frames]
        mean_rms = 0.0 if not rms_values else float(sum(rms_values) / len(rms_values))
        peak_rms = 0.0 if not rms_values else float(max(rms_values))
        active_ratio = 0.0 if not frames else float(sum(float(frame.rms) > silence_rms_threshold for frame in frames) / len(frames))
        voiced_ratio = 0.0 if not pitch_frames else float(sum(bool(frame.voiced) for frame in pitch_frames) / len(pitch_frames))
        mean_flux = 0.0 if not frames else float(sum(float(frame.spectral_flux) for frame in frames) / len(frames))
        maximum_onset = 0.0 if not frames else float(max(float(frame.onset_strength) for frame in frames))
        transient_count = sum(start <= int(event.sample_index) < end for event in transient.transients)
        change_count = sum(start <= int(event.sample_index) < end for event in transient.change_points)

        is_attack = attack_present and active_start is not None and attack_end is not None and start == active_start and end == attack_end
        if mean_rms <= silence_rms_threshold or active_ratio == 0.0:
            kind = SegmentKind.SILENCE
            reason = "The segment contains no frame above the configured active RMS threshold."
        elif is_attack:
            kind = SegmentKind.ATTACK
            reason = "A qualified onset near the first active frame defines a bounded attack segment."
            attack_segment_index = index
        elif active_end is not None and end == active_end and frames and float(frames[-1].energy_change_db) < -0.75 and maximum_onset < minimum_attack_strength:
            kind = SegmentKind.RELEASE
            reason = "The final active segment ends with a sustained negative energy change and no strong onset."
        elif change_count > 0 or mean_flux >= transition_flux_threshold or maximum_onset >= minimum_attack_strength:
            kind = SegmentKind.TRANSITION
            reason = "Change-point, spectral-flux, or onset evidence marks the segment as transitional."
        else:
            kind = SegmentKind.STEADY
            reason = "The segment is active without sufficient change evidence to mark a transition."

        segments.append(
            SourceSegment(
                index=index,
                start_sample=start,
                end_sample=end,
                sample_rate=sample_rate,
                kind=kind,
                frame_start_index=None if not frames else int(frames[0].frame_index),
                frame_end_index=None if not frames else int(frames[-1].frame_index),
                mean_rms=mean_rms,
                peak_rms=peak_rms,
                active_frame_ratio=active_ratio,
                voiced_frame_ratio=voiced_ratio,
                mean_spectral_flux=mean_flux,
                maximum_onset_strength=maximum_onset,
                transient_count=int(transient_count),
                change_point_count=int(change_count),
                start_boundary_reason=left[1],
                end_boundary_reason=right[1],
                classification_reason=reason,
            )
        )

    non_silent = [segment for segment in segments if segment.kind is not SegmentKind.SILENCE]
    post_attack_candidates = [
        segment
        for segment in non_silent
        if attack_segment_index is None or segment.index > attack_segment_index
    ]
    sustain_candidates = [segment for segment in post_attack_candidates if segment.kind is SegmentKind.STEADY]
    if not sustain_candidates:
        sustain_candidates = [segment for segment in post_attack_candidates if segment.kind is not SegmentKind.ATTACK]
    primary = None
    if sustain_candidates:
        primary = sorted(
            sustain_candidates,
            key=lambda segment: (
                -(segment.duration_seconds * (0.5 + 0.5 * segment.active_frame_ratio) * (0.5 + 0.5 * segment.voiced_frame_ratio)),
                segment.index,
            ),
        )[0]

    if attack_segment_index is None:
        attack_decision = AttackDecision.NOT_PRESENT
        decision_reason = "No qualified first-onset attack segment was detected."
    elif selected_policy is AttackPolicy.KEEP:
        attack_decision = AttackDecision.KEEP
        decision_reason = "The explicit keep policy retains the detected attack as a representative source state."
    elif selected_policy is AttackPolicy.REJECT:
        attack_decision = AttackDecision.REJECT
        decision_reason = "The explicit reject policy excludes the detected attack from usable segment selection."
    else:
        attack = segments[attack_segment_index]
        primary_duration_ms = 0.0 if primary is None else primary.duration_seconds * 1000.0
        keep = (
            attack.duration_seconds * 1000.0 <= maximum_attack_duration_ms
            and attack.maximum_onset_strength >= minimum_attack_strength
            and primary is not None
            and primary.index > attack.index
            and primary_duration_ms >= minimum_steady_duration_ms
        )
        if keep:
            attack_decision = AttackDecision.KEEP
            decision_reason = "The attack is bounded, exceeds the onset gate, and is followed by a sufficiently long usable segment."
        else:
            attack_decision = AttackDecision.REJECT
            decision_reason = "The attack fails a duration, onset, or post-attack usability gate and is excluded from usable segments."

    usable = []
    for segment in segments:
        if segment.kind is SegmentKind.SILENCE:
            continue
        if segment.index == attack_segment_index and attack_decision is AttackDecision.REJECT:
            continue
        usable.append(segment.index)
    primary_index = None if primary is None or primary.index not in usable else primary.index

    return SegmentationAnalysis(
        schema_version=1,
        tool_version=tool_version,
        sample_rate=sample_rate,
        sample_count=sample_count,
        sample_sha256=signal_analysis.sample_sha256,
        signal_analysis_sha256=signal_analysis.analysis_sha256,
        working_pitch_plan_sha256=working_pitch_plan.analysis_sha256,
        working_frequency_hz=working_pitch_plan.target_frequency_hz,
        working_period_samples=working_pitch_plan.target_period_samples,
        repitch_required=bool(working_pitch_plan.repitch_required),
        attack_policy=selected_policy,
        attack_decision=attack_decision,
        minimum_segment_duration_ms=float(minimum_segment_duration_ms),
        boundary_merge_window_ms=float(boundary_merge_window_ms),
        attack_window_ms=float(attack_window_ms),
        maximum_attack_duration_ms=float(maximum_attack_duration_ms),
        minimum_attack_strength=float(minimum_attack_strength),
        minimum_steady_duration_ms=float(minimum_steady_duration_ms),
        silence_rms_threshold=float(silence_rms_threshold),
        transition_flux_threshold=float(transition_flux_threshold),
        segments=tuple(segments),
        attack_segment_index=attack_segment_index,
        usable_segment_indices=tuple(usable),
        primary_sustain_segment_index=primary_index,
        decision_reason=decision_reason,
    )


def analyze_audio_source_segmentation(
    source: Any,
    *,
    working_pitch_policy: WorkingPitchPolicy | str = WorkingPitchPolicy.AUTO,
    locked_frequency_hz: float | None = None,
    attack_policy: AttackPolicy | str = AttackPolicy.AUTO,
    **segmentation_kwargs: float | str,
) -> SegmentationAnalysis:
    """Run the canonical V6-A pitch plan and V6-B segmentation for one source."""

    signal_analysis = analyze_audio_source_signal(source)
    working_pitch_plan = plan_working_pitch(
        signal_analysis.pitch_periodicity_analysis,
        policy=working_pitch_policy,
        locked_frequency_hz=locked_frequency_hz,
    )
    return segment_source(
        signal_analysis,
        working_pitch_plan,
        attack_policy=attack_policy,
        **segmentation_kwargs,
    )
