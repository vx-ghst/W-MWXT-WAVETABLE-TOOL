from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any

from ..version import __version__
from .periodicity import analyze_audio_source_pitch_periodicity
from .pitch_candidates import (
    WorkingPitchCandidate,
    WorkingPitchCandidateKind,
    WorkingPitchCandidates,
    generate_working_pitch_candidates,
)


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
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


class WorkingPitchPolicy(str, Enum):
    AUTO = "auto"
    LOCK = "lock"
    NO_REPITCH = "no_repitch"


class WorkingPitchDecision(str, Enum):
    REPITCH = "repitch"
    NO_REPITCH = "no_repitch"
    PITCH_UNAVAILABLE = "pitch_unavailable"


@dataclass(frozen=True, slots=True)
class WorkingPitchPlan:
    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    pitch_periodicity_analysis_sha256: str
    pitch_candidates: WorkingPitchCandidates
    policy: WorkingPitchPolicy
    decision: WorkingPitchDecision
    selected_candidate: WorkingPitchCandidate | None
    repitch_required: bool
    locked: bool
    minimum_periodicity_score: float
    minimum_pitch_stability: float
    minimum_score_improvement: float
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported working-pitch plan schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise ValueError("tool_version must be a non-empty normalized string")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if not _hash_is_valid(self.sample_sha256):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if not _hash_is_valid(self.pitch_periodicity_analysis_sha256):
            raise ValueError(
                "pitch_periodicity_analysis_sha256 must be a lowercase SHA-256 digest"
            )
        if self.pitch_candidates.sample_rate != self.sample_rate:
            raise ValueError("pitch candidates have an inconsistent sample rate")
        if self.pitch_candidates.sample_count != self.sample_count:
            raise ValueError("pitch candidates have an inconsistent sample count")
        if self.pitch_candidates.sample_sha256 != self.sample_sha256:
            raise ValueError("pitch candidates have an inconsistent sample hash")
        if (
            self.pitch_candidates.pitch_periodicity_analysis_sha256
            != self.pitch_periodicity_analysis_sha256
        ):
            raise ValueError("pitch candidates do not link to pitch analysis")
        _require_ratio(
            self.minimum_periodicity_score, name="minimum_periodicity_score"
        )
        _require_ratio(self.minimum_pitch_stability, name="minimum_pitch_stability")
        _require_ratio(
            self.minimum_score_improvement, name="minimum_score_improvement"
        )
        if not self.decision_reason:
            raise ValueError("decision_reason must not be empty")
        candidate_hashes = set(self.pitch_candidates.candidate_sha256)
        if self.selected_candidate is not None:
            if self.selected_candidate.candidate_sha256 not in candidate_hashes:
                raise ValueError("selected candidate is not in the candidate analysis")
        if self.decision is WorkingPitchDecision.REPITCH:
            if self.selected_candidate is None or not self.repitch_required:
                raise ValueError("repitch decisions require a selected repitch candidate")
        if self.repitch_required:
            if self.selected_candidate is None:
                raise ValueError("repitch_required needs a selected candidate")
            if math.isclose(
                self.selected_candidate.repitch_ratio,
                1.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("repitch_required cannot use a unity ratio")
        if self.locked:
            if self.policy is not WorkingPitchPolicy.LOCK:
                raise ValueError("locked plans require the lock policy")
            if (
                self.selected_candidate is None
                or self.selected_candidate.kind
                is not WorkingPitchCandidateKind.EXPLICIT_LOCK
            ):
                raise ValueError("locked plans require the explicit lock candidate")
        elif self.policy is WorkingPitchPolicy.LOCK:
            raise ValueError("lock policy plans must be marked locked")
        if self.decision is WorkingPitchDecision.PITCH_UNAVAILABLE:
            if self.selected_candidate is not None or self.repitch_required:
                raise ValueError("pitch-unavailable plans cannot select repitch data")

    @property
    def selected_candidate_sha256(self) -> str | None:
        if self.selected_candidate is None:
            return None
        return self.selected_candidate.candidate_sha256

    @property
    def repitch_ratio(self) -> float | None:
        if self.selected_candidate is None:
            return None
        return self.selected_candidate.repitch_ratio

    @property
    def target_frequency_hz(self) -> float | None:
        if self.selected_candidate is None:
            return None
        return self.selected_candidate.target_frequency_hz

    @property
    def target_period_samples(self) -> float | None:
        if self.selected_candidate is None:
            return None
        return self.selected_candidate.target_period_samples

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "pitch_periodicity_analysis_sha256": (
                self.pitch_periodicity_analysis_sha256
            ),
            "pitch_candidates_sha256": self.pitch_candidates.analysis_sha256,
            "pitch_candidates": self.pitch_candidates.to_dict(),
            "policy": self.policy.value,
            "decision": self.decision.value,
            "selected_candidate_sha256": self.selected_candidate_sha256,
            "selected_candidate": (
                None
                if self.selected_candidate is None
                else self.selected_candidate.to_dict()
            ),
            "repitch_required": self.repitch_required,
            "repitch_ratio": self.repitch_ratio,
            "target_frequency_hz": self.target_frequency_hz,
            "target_period_samples": self.target_period_samples,
            "locked": self.locked,
            "minimum_periodicity_score": self.minimum_periodicity_score,
            "minimum_pitch_stability": self.minimum_pitch_stability,
            "minimum_score_improvement": self.minimum_score_improvement,
            "decision_reason": self.decision_reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _source_candidate(candidates: WorkingPitchCandidates) -> WorkingPitchCandidate:
    for candidate in candidates.candidates:
        if (
            candidate.kind is WorkingPitchCandidateKind.SOURCE_OCTAVE
            and candidate.octave_shift == 0
        ):
            return candidate
    raise ValueError("candidate analysis does not contain the source-pitch candidate")


def _locked_candidate(candidates: WorkingPitchCandidates) -> WorkingPitchCandidate:
    for candidate in candidates.candidates:
        if candidate.kind is WorkingPitchCandidateKind.EXPLICIT_LOCK:
            return candidate
    raise ValueError("candidate analysis does not contain an explicit lock")


def _build_plan(
    candidates: WorkingPitchCandidates,
    *,
    policy: WorkingPitchPolicy,
    decision: WorkingPitchDecision,
    selected_candidate: WorkingPitchCandidate | None,
    repitch_required: bool,
    locked: bool,
    minimum_periodicity_score: float,
    minimum_pitch_stability: float,
    minimum_score_improvement: float,
    decision_reason: str,
    tool_version: str,
) -> WorkingPitchPlan:
    return WorkingPitchPlan(
        schema_version=1,
        tool_version=tool_version,
        sample_rate=candidates.sample_rate,
        sample_count=candidates.sample_count,
        sample_sha256=candidates.sample_sha256,
        pitch_periodicity_analysis_sha256=(
            candidates.pitch_periodicity_analysis_sha256
        ),
        pitch_candidates=candidates,
        policy=policy,
        decision=decision,
        selected_candidate=selected_candidate,
        repitch_required=repitch_required,
        locked=locked,
        minimum_periodicity_score=minimum_periodicity_score,
        minimum_pitch_stability=minimum_pitch_stability,
        minimum_score_improvement=minimum_score_improvement,
        decision_reason=decision_reason,
    )


def plan_working_pitch(
    pitch_analysis: Any,
    *,
    policy: WorkingPitchPolicy | str = WorkingPitchPolicy.AUTO,
    locked_frequency_hz: float | None = None,
    preferred_period_samples: float = 128.0,
    minimum_period_samples: float = 64.0,
    maximum_period_samples: float = 256.0,
    maximum_octave_shift: int = 4,
    minimum_periodicity_score: float = 0.60,
    minimum_pitch_stability: float = 0.25,
    minimum_score_improvement: float = 0.10,
    tool_version: str = __version__,
) -> WorkingPitchPlan:
    """Create an explainable, non-destructive temporary repitch plan."""

    selected_policy = WorkingPitchPolicy(policy)
    periodicity_threshold = _require_ratio(
        minimum_periodicity_score, name="minimum_periodicity_score"
    )
    stability_threshold = _require_ratio(
        minimum_pitch_stability, name="minimum_pitch_stability"
    )
    improvement_threshold = _require_ratio(
        minimum_score_improvement, name="minimum_score_improvement"
    )
    if selected_policy is WorkingPitchPolicy.LOCK and locked_frequency_hz is None:
        raise ValueError("lock policy requires locked_frequency_hz")
    if selected_policy is not WorkingPitchPolicy.LOCK and locked_frequency_hz is not None:
        raise ValueError("locked_frequency_hz is only valid with lock policy")

    candidates = generate_working_pitch_candidates(
        pitch_analysis,
        preferred_period_samples=preferred_period_samples,
        minimum_period_samples=minimum_period_samples,
        maximum_period_samples=maximum_period_samples,
        maximum_octave_shift=maximum_octave_shift,
        locked_frequency_hz=locked_frequency_hz,
        tool_version=tool_version,
    )

    if candidates.source_frequency_hz is None:
        if selected_policy is WorkingPitchPolicy.NO_REPITCH:
            return _build_plan(
                candidates,
                policy=selected_policy,
                decision=WorkingPitchDecision.NO_REPITCH,
                selected_candidate=None,
                repitch_required=False,
                locked=False,
                minimum_periodicity_score=periodicity_threshold,
                minimum_pitch_stability=stability_threshold,
                minimum_score_improvement=improvement_threshold,
                decision_reason=(
                    "No source pitch was available; the explicit no-repitch policy "
                    "preserves the source for later non-periodic reconstruction."
                ),
                tool_version=tool_version,
            )
        return _build_plan(
            candidates,
            policy=selected_policy,
            decision=WorkingPitchDecision.PITCH_UNAVAILABLE,
            selected_candidate=None,
            repitch_required=False,
            locked=False,
            minimum_periodicity_score=periodicity_threshold,
            minimum_pitch_stability=stability_threshold,
            minimum_score_improvement=improvement_threshold,
            decision_reason=(
                "No source pitch was available, so automatic temporary repitching "
                "cannot be planned."
            ),
            tool_version=tool_version,
        )

    source = _source_candidate(candidates)
    if selected_policy is WorkingPitchPolicy.NO_REPITCH:
        return _build_plan(
            candidates,
            policy=selected_policy,
            decision=WorkingPitchDecision.NO_REPITCH,
            selected_candidate=source,
            repitch_required=False,
            locked=False,
            minimum_periodicity_score=periodicity_threshold,
            minimum_pitch_stability=stability_threshold,
            minimum_score_improvement=improvement_threshold,
            decision_reason=(
                "The explicit no-repitch policy preserves the detected source pitch."
            ),
            tool_version=tool_version,
        )

    if selected_policy is WorkingPitchPolicy.LOCK:
        locked = _locked_candidate(candidates)
        required = not math.isclose(
            locked.repitch_ratio, 1.0, rel_tol=0.0, abs_tol=1e-12
        )
        return _build_plan(
            candidates,
            policy=selected_policy,
            decision=(
                WorkingPitchDecision.REPITCH
                if required
                else WorkingPitchDecision.NO_REPITCH
            ),
            selected_candidate=locked,
            repitch_required=required,
            locked=True,
            minimum_periodicity_score=periodicity_threshold,
            minimum_pitch_stability=stability_threshold,
            minimum_score_improvement=improvement_threshold,
            decision_reason=(
                "The explicit working-pitch lock is authoritative."
                if required
                else "The explicit working-pitch lock matches the detected source pitch."
            ),
            tool_version=tool_version,
        )

    if candidates.source_periodicity_score < periodicity_threshold:
        return _build_plan(
            candidates,
            policy=selected_policy,
            decision=WorkingPitchDecision.NO_REPITCH,
            selected_candidate=source,
            repitch_required=False,
            locked=False,
            minimum_periodicity_score=periodicity_threshold,
            minimum_pitch_stability=stability_threshold,
            minimum_score_improvement=improvement_threshold,
            decision_reason=(
                "The detected periodicity is below the configured confidence gate, "
                "so automatic temporary repitching is withheld."
            ),
            tool_version=tool_version,
        )
    if candidates.source_pitch_stability < stability_threshold:
        return _build_plan(
            candidates,
            policy=selected_policy,
            decision=WorkingPitchDecision.NO_REPITCH,
            selected_candidate=source,
            repitch_required=False,
            locked=False,
            minimum_periodicity_score=periodicity_threshold,
            minimum_pitch_stability=stability_threshold,
            minimum_score_improvement=improvement_threshold,
            decision_reason=(
                "Pitch stability is below the configured gate, so automatic "
                "temporary repitching is withheld."
            ),
            tool_version=tool_version,
        )

    best = candidates.candidates[0]
    score_improvement = float(best.score - source.score)
    required = not math.isclose(
        best.repitch_ratio, 1.0, rel_tol=0.0, abs_tol=1e-12
    )
    if required and score_improvement >= improvement_threshold:
        return _build_plan(
            candidates,
            policy=selected_policy,
            decision=WorkingPitchDecision.REPITCH,
            selected_candidate=best,
            repitch_required=True,
            locked=False,
            minimum_periodicity_score=periodicity_threshold,
            minimum_pitch_stability=stability_threshold,
            minimum_score_improvement=improvement_threshold,
            decision_reason=(
                "The top octave-preserving candidate improves working-period fitness "
                f"by {score_improvement:.12f}, meeting the configured gate."
            ),
            tool_version=tool_version,
        )
    return _build_plan(
        candidates,
        policy=selected_policy,
        decision=WorkingPitchDecision.NO_REPITCH,
        selected_candidate=source,
        repitch_required=False,
        locked=False,
        minimum_periodicity_score=periodicity_threshold,
        minimum_pitch_stability=stability_threshold,
        minimum_score_improvement=improvement_threshold,
        decision_reason=(
            "The source pitch is already the best safe working choice or the "
            "candidate improvement does not meet the configured gate."
        ),
        tool_version=tool_version,
    )


def analyze_audio_source_working_pitch(
    source: Any,
    *,
    pitch_frame_size: int = 4096,
    pitch_hop_size: int = 1024,
    minimum_frequency_hz: float = 40.0,
    maximum_frequency_hz: float = 2000.0,
    active_rms_threshold: float = 1e-6,
    pitch_confidence_threshold: float = 0.60,
    reference_a4_hz: float = 440.0,
    **plan_kwargs: Any,
) -> WorkingPitchPlan:
    pitch_analysis = analyze_audio_source_pitch_periodicity(
        source,
        frame_size=pitch_frame_size,
        hop_size=pitch_hop_size,
        minimum_frequency_hz=minimum_frequency_hz,
        maximum_frequency_hz=maximum_frequency_hz,
        active_rms_threshold=active_rms_threshold,
        confidence_threshold=pitch_confidence_threshold,
        reference_a4_hz=reference_a4_hz,
    )
    return plan_working_pitch(pitch_analysis, **plan_kwargs)
