from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any


PROFILE_METRIC_NAMES = (
    "time_fidelity",
    "spectral_fidelity",
    "phase_fidelity",
    "seam_quality",
    "fundamental",
    "h2",
    "h3",
    "low_band",
    "mid_band",
    "high_band",
    "perceptual",
    "aliasing",
    "ringing",
    "amplitude",
)


class OptimizationProfile(str, Enum):
    BASS_SUB = "bass_sub"
    LEAD = "lead"
    PAD = "pad"
    BELL_FM = "bell_fm"
    VOCAL_CHOIR = "vocal_choir"
    TEXTURE = "texture"
    DRONE = "drone"
    PERCUSSIVE = "percussive"
    EXPERIMENTAL = "experimental"


def _finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _ratio(value: float, *, name: str) -> float:
    result = _finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def _normalized_text(value: str, *, name: str) -> str:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized string")
    return value


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


@dataclass(frozen=True, slots=True)
class ProfileWeights:
    time_fidelity: float
    spectral_fidelity: float
    phase_fidelity: float
    seam_quality: float
    fundamental: float
    h2: float
    h3: float
    low_band: float
    mid_band: float
    high_band: float
    perceptual: float
    aliasing: float
    ringing: float
    amplitude: float

    def __post_init__(self) -> None:
        values = tuple(float(getattr(self, name)) for name in PROFILE_METRIC_NAMES)
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("profile weights must be finite and non-negative")
        if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise ValueError("profile weights must sum exactly to 1.0")

    @property
    def weight_map(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in PROFILE_METRIC_NAMES}

    def to_dict(self) -> dict[str, float]:
        return self.weight_map


@dataclass(frozen=True, slots=True)
class ProfileDefinition:
    schema_version: int
    profile: OptimizationProfile
    weights: ProfileWeights
    preserve_controlled_defects: tuple[str, ...]
    forbidden_defects: tuple[str, ...]
    priorities: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported optimization-profile schema version")
        for name, values in (
            ("preserve_controlled_defects", self.preserve_controlled_defects),
            ("forbidden_defects", self.forbidden_defects),
            ("priorities", self.priorities),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must contain unique values")
            if any(not value or value.strip() != value for value in values):
                raise ValueError(f"{name} must contain normalized strings")
        if set(self.preserve_controlled_defects).intersection(self.forbidden_defects):
            raise ValueError("preserved and forbidden defects must not overlap")
        if not self.priorities:
            raise ValueError("priorities must not be empty")
        _normalized_text(self.reason, name="reason")
        if self.profile is not OptimizationProfile.EXPERIMENTAL and self.preserve_controlled_defects:
            raise ValueError("only the experimental profile may preserve controlled defects")
        always_forbidden = {"non_finite", "overflow", "unsafe_negative_128"}
        if not always_forbidden.issubset(self.forbidden_defects):
            raise ValueError("every profile must forbid non-finite, overflow, and -128 output")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile.value,
            "weights": self.weights.to_dict(),
            "preserve_controlled_defects": list(self.preserve_controlled_defects),
            "forbidden_defects": list(self.forbidden_defects),
            "priorities": list(self.priorities),
            "reason": self.reason,
        }

    @property
    def profile_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["profile_sha256"] = self.profile_sha256
        return result


@dataclass(frozen=True, slots=True)
class ProfileScore:
    profile: OptimizationProfile
    raw_score: float
    score: float
    explanation: str

    def __post_init__(self) -> None:
        if _finite(self.raw_score, name="raw_score") < 0.0:
            raise ValueError("raw_score must not be negative")
        _ratio(self.score, name="score")
        _normalized_text(self.explanation, name="explanation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.value,
            "raw_score": self.raw_score,
            "score": self.score,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class ProfileSelection:
    schema_version: int
    musical_classification_sha256: str
    mode_decision_sha256: str
    selected_profile: OptimizationProfile
    requested_override: OptimizationProfile | None
    scores: tuple[ProfileScore, ...]
    confidence: float
    ambiguity: float
    definition: ProfileDefinition
    warnings: tuple[str, ...]
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported profile-selection schema version")
        for name in ("musical_classification_sha256", "mode_decision_sha256"):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if tuple(item.profile for item in self.scores) != tuple(OptimizationProfile):
            raise ValueError("scores must contain every profile in canonical order")
        if not math.isclose(sum(item.score for item in self.scores), 1.0, abs_tol=1.0e-12):
            raise ValueError("normalized profile scores must sum to one")
        if self.definition.profile is not self.selected_profile:
            raise ValueError("definition does not match selected_profile")
        if self.requested_override is None:
            selected = max(self.scores, key=lambda item: item.score)
            if selected.profile is not self.selected_profile:
                raise ValueError("automatic selection must match the highest score")
        elif self.requested_override is not self.selected_profile:
            raise ValueError("override must match selected_profile")
        _ratio(self.confidence, name="confidence")
        _ratio(self.ambiguity, name="ambiguity")
        if not math.isclose(self.confidence + self.ambiguity, 1.0, abs_tol=1.0e-12):
            raise ValueError("confidence and ambiguity must sum to one")
        if any(not item or item.strip() != item for item in self.warnings):
            raise ValueError("warnings must contain normalized strings")
        if not self.evidence or any(not item or item.strip() != item for item in self.evidence):
            raise ValueError("evidence must contain normalized non-empty strings")
        _normalized_text(self.reason, name="reason")

    @property
    def score_map(self) -> dict[str, float]:
        return {item.profile.value: item.score for item in self.scores}

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "musical_classification_sha256": self.musical_classification_sha256,
            "mode_decision_sha256": self.mode_decision_sha256,
            "selected_profile": self.selected_profile.value,
            "requested_override": None if self.requested_override is None else self.requested_override.value,
            "scores": [item.to_dict() for item in self.scores],
            "confidence": self.confidence,
            "ambiguity": self.ambiguity,
            "definition": self.definition.to_dict(),
            "warnings": list(self.warnings),
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["score_map"] = self.score_map
        result["analysis_sha256"] = self.analysis_sha256
        return result
