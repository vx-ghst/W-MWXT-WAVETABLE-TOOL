from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any


_EPSILON = 1.0e-12


def _canonical_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True, slots=True)
class BassPitchEvaluation:
    candidate_sha256: str
    target_frequency_hz: float
    target_period_samples: float
    base_score: float
    period_compatibility: float
    retained_harmonic_ratio: float
    aliasing_safety: float
    low_note_power: float
    bass_score: float
    explanation: str

    def __post_init__(self) -> None:
        if not _hash_is_valid(self.candidate_sha256):
            raise ValueError("candidate_sha256 must be a lowercase SHA-256 digest")
        if self.target_frequency_hz <= 0.0 or self.target_period_samples <= 0.0:
            raise ValueError("pitch values must be positive")
        for name in (
            "base_score",
            "period_compatibility",
            "retained_harmonic_ratio",
            "aliasing_safety",
            "low_note_power",
            "bass_score",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be a finite ratio")
        if not self.explanation or self.explanation.strip() != self.explanation:
            raise ValueError("explanation must be normalized")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_sha256": self.candidate_sha256,
            "target_frequency_hz": self.target_frequency_hz,
            "target_period_samples": self.target_period_samples,
            "base_score": self.base_score,
            "period_compatibility": self.period_compatibility,
            "retained_harmonic_ratio": self.retained_harmonic_ratio,
            "aliasing_safety": self.aliasing_safety,
            "low_note_power": self.low_note_power,
            "bass_score": self.bass_score,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class BassPitchComparison:
    schema_version: int
    working_pitch_candidates_sha256: str
    evaluations: tuple[BassPitchEvaluation, ...]
    selected_candidate_sha256: str
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported Bass-pitch-comparison schema version")
        if not _hash_is_valid(self.working_pitch_candidates_sha256):
            raise ValueError("working_pitch_candidates_sha256 must be a SHA-256 digest")
        if not self.evaluations:
            raise ValueError("evaluations must not be empty")
        hashes = tuple(item.candidate_sha256 for item in self.evaluations)
        if len(set(hashes)) != len(hashes):
            raise ValueError("pitch evaluations must be unique")
        selected = max(self.evaluations, key=lambda item: (item.bass_score, -item.target_frequency_hz))
        if selected.candidate_sha256 != self.selected_candidate_sha256:
            raise ValueError("selected_candidate_sha256 is inconsistent")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be normalized")

    @property
    def selected(self) -> BassPitchEvaluation:
        return next(item for item in self.evaluations if item.candidate_sha256 == self.selected_candidate_sha256)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "working_pitch_candidates_sha256": self.working_pitch_candidates_sha256,
            "evaluations": [item.to_dict() for item in self.evaluations],
            "selected_candidate_sha256": self.selected_candidate_sha256,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def evaluate_bass_working_pitches(
    working_pitch_candidates: Any,
    *,
    playback_ceiling_hz: float = 16000.0,
    xt_harmonic_capacity: int = 31,
    preferred_bass_frequency_hz: float = 82.41,
) -> BassPitchComparison:
    """Re-rank accepted V6 pitch candidates with an explicit Bass/Sub objective."""

    ceiling = float(playback_ceiling_hz)
    preferred = float(preferred_bass_frequency_hz)
    if not math.isfinite(ceiling) or ceiling <= 0.0:
        raise ValueError("playback_ceiling_hz must be positive")
    if not math.isfinite(preferred) or preferred <= 0.0:
        raise ValueError("preferred_bass_frequency_hz must be positive")
    if xt_harmonic_capacity <= 0:
        raise ValueError("xt_harmonic_capacity must be positive")
    source_hash = getattr(working_pitch_candidates, "analysis_sha256")
    if not _hash_is_valid(source_hash):
        raise ValueError("working pitch candidate hash is invalid")
    candidates = tuple(getattr(working_pitch_candidates, "candidates"))
    if not candidates:
        raise ValueError("Bass/Sub pitch comparison requires pitched candidates")
    evaluations: list[BassPitchEvaluation] = []
    for candidate in candidates:
        frequency = float(candidate.target_frequency_hz)
        period = float(candidate.target_period_samples)
        base = min(1.0, max(0.0, float(candidate.score)))
        period_compatibility = 1.0 / (1.0 + abs(math.log2(period / 128.0)))
        retained_count = min(xt_harmonic_capacity, max(1, int(math.floor(ceiling / frequency))))
        retained_ratio = retained_count / xt_harmonic_capacity
        aliasing_safety = retained_ratio
        low_note_power = 1.0 / (1.0 + 0.35 * abs(math.log2(frequency / preferred)))
        score = (
            0.25 * base
            + 0.25 * period_compatibility
            + 0.20 * retained_ratio
            + 0.15 * aliasing_safety
            + 0.15 * low_note_power
        )
        evaluations.append(
            BassPitchEvaluation(
                candidate_sha256=candidate.candidate_sha256,
                target_frequency_hz=frequency,
                target_period_samples=period,
                base_score=base,
                period_compatibility=period_compatibility,
                retained_harmonic_ratio=retained_ratio,
                aliasing_safety=aliasing_safety,
                low_note_power=low_note_power,
                bass_score=float(score),
                explanation=(
                    "Score combines the accepted V6 candidate score, 128-sample period "
                    "compatibility, retained XT harmonics, aliasing safety, and low-note power."
                ),
            )
        )
    ordered = tuple(sorted(evaluations, key=lambda item: (-item.bass_score, item.target_frequency_hz, item.candidate_sha256)))
    return BassPitchComparison(
        schema_version=1,
        working_pitch_candidates_sha256=source_hash,
        evaluations=ordered,
        selected_candidate_sha256=ordered[0].candidate_sha256,
        reason=(
            "All accepted working-pitch candidates were compared under one explicit Bass/Sub "
            "objective; no pitch was selected from musical class alone."
        ),
    )


@dataclass(frozen=True, slots=True)
class BassSequenceConsistency:
    schema_version: int
    wave_count: int
    amplitude_consistency: float
    bass_power_consistency: float
    combined_score: float
    warning: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported Bass-sequence-consistency schema version")
        if self.wave_count <= 0:
            raise ValueError("wave_count must be positive")
        for name in (
            "amplitude_consistency",
            "bass_power_consistency",
            "combined_score",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be a finite ratio")
        expected = self.combined_score < 0.65
        if self.warning != expected:
            raise ValueError("warning is inconsistent with combined_score")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be normalized")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "wave_count": self.wave_count,
            "amplitude_consistency": self.amplitude_consistency,
            "bass_power_consistency": self.bass_power_consistency,
            "combined_score": self.combined_score,
            "warning": self.warning,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def analyze_bass_sequence_consistency(
    wave_metrics: Any,
) -> BassSequenceConsistency:
    """Measure amplitude and Bass-score consistency across an ordered wave set."""

    metrics = tuple(wave_metrics)
    if not metrics:
        raise ValueError("Bass sequence consistency requires at least one wave metric")
    amplitudes = tuple(float(item.reconstructed_rms) for item in metrics)
    bass_scores = tuple(float(item.bass_score) for item in metrics)
    if any(not math.isfinite(value) or value < 0.0 for value in amplitudes):
        raise ValueError("reconstructed RMS values must be finite and non-negative")
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in bass_scores):
        raise ValueError("Bass scores must be finite ratios")

    amplitude_mean = sum(amplitudes) / len(amplitudes)
    amplitude_span = max(amplitudes) - min(amplitudes)
    amplitude_consistency = max(
        0.0,
        1.0 - amplitude_span / max(amplitude_mean, _EPSILON),
    )
    bass_span = max(bass_scores) - min(bass_scores)
    bass_consistency = max(0.0, 1.0 - bass_span)
    combined = 0.5 * amplitude_consistency + 0.5 * bass_consistency
    return BassSequenceConsistency(
        schema_version=1,
        wave_count=len(metrics),
        amplitude_consistency=float(min(1.0, amplitude_consistency)),
        bass_power_consistency=float(min(1.0, bass_consistency)),
        combined_score=float(min(1.0, combined)),
        warning=combined < 0.65,
        reason=(
            "Consistency combines reconstructed RMS span and per-wave Bass-score span; "
            "it is advisory evidence for the later 61-position builder."
        ),
    )
