from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any


class BehaviorClass(str, Enum):
    PERIODIC = "periodic"
    QUASI_PERIODIC = "quasi_periodic"
    EVOLVING = "evolving"
    PITCH_VARIABLE = "pitch_variable"
    TRANSIENT = "transient"
    NOISY = "noisy"
    NON_PERIODIC = "non_periodic"
    HYBRID = "hybrid"


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


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True, slots=True)
class BehaviorScore:
    behavior: BehaviorClass
    raw_score: float
    score: float
    explanation: str

    def __post_init__(self) -> None:
        if _finite(self.raw_score, name="raw_score") < 0.0:
            raise ValueError("raw_score must not be negative")
        _ratio(self.score, name="score")
        if not self.explanation or self.explanation.strip() != self.explanation:
            raise ValueError("explanation must be a non-empty normalized string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "behavior": self.behavior.value,
            "raw_score": self.raw_score,
            "score": self.score,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class BehaviorClassification:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    signal_analysis_sha256: str
    signal_extension_analysis_sha256: str
    behavior: BehaviorClass
    confidence: float
    ambiguity: float
    scores: tuple[BehaviorScore, ...]
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported behavior-classification schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "signal_analysis_sha256",
            "signal_extension_analysis_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        _ratio(self.confidence, name="confidence")
        _ratio(self.ambiguity, name="ambiguity")
        if not math.isclose(self.confidence + self.ambiguity, 1.0, abs_tol=1e-12):
            raise ValueError("confidence and ambiguity must sum to one")
        if tuple(item.behavior for item in self.scores) != tuple(BehaviorClass):
            raise ValueError("scores must contain every behavior in canonical order")
        if not math.isclose(sum(item.score for item in self.scores), 1.0, abs_tol=1e-12):
            raise ValueError("normalized behavior scores must sum to one")
        selected = max(self.scores, key=lambda item: item.score)
        if selected.behavior is not self.behavior:
            raise ValueError("behavior must match the highest normalized score")
        if not self.evidence or any(not item for item in self.evidence):
            raise ValueError("evidence must contain non-empty entries")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    @property
    def score_map(self) -> dict[str, float]:
        return {item.behavior.value: item.score for item in self.scores}

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "signal_analysis_sha256": self.signal_analysis_sha256,
            "signal_extension_analysis_sha256": self.signal_extension_analysis_sha256,
            "behavior": self.behavior.value,
            "confidence": self.confidence,
            "ambiguity": self.ambiguity,
            "scores": [item.to_dict() for item in self.scores],
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        rendered = json.dumps(
            self._content_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(rendered).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["score_map"] = self.score_map
        result["analysis_sha256"] = self.analysis_sha256
        return result


class MusicalClass(str, Enum):
    SUB = "sub"
    BASS = "bass"
    REESE = "reese"
    FM_BASS = "fm_bass"
    DIRTY_BASS = "dirty_bass"
    HOOVER = "hoover"
    ACID = "acid"
    LEAD = "lead"
    PAD = "pad"
    DRONE = "drone"
    ORGAN = "organ"
    PWM = "pwm"
    SUPERSAW = "supersaw"
    WAVETABLE = "wavetable"
    BELL = "bell"
    FM_BELL = "fm_bell"
    PLUCK = "pluck"
    VOCAL = "vocal"
    CHOIR = "choir"
    TEXTURE = "texture"
    DIGITAL_NOISE = "digital_noise"
    NOISE = "noise"
    PIANO = "piano"
    GUITAR = "guitar"
    PERCUSSION = "percussion"
    FX = "fx"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class MusicalClassScore:
    musical_class: MusicalClass
    score: float
    selected: bool
    explanation: str

    def __post_init__(self) -> None:
        _ratio(self.score, name="score")
        if not self.explanation or self.explanation.strip() != self.explanation:
            raise ValueError("explanation must be a non-empty normalized string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "musical_class": self.musical_class.value,
            "score": self.score,
            "selected": self.selected,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class MusicalClassification:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    behavior_classification_sha256: str
    perceptual_feature_sha256: str
    formant_analysis_sha256: str
    score_threshold: float
    maximum_labels: int
    scores: tuple[MusicalClassScore, ...]
    selected_classes: tuple[MusicalClass, ...]
    confidence: float
    ambiguity: float
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported musical-classification schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "behavior_classification_sha256",
            "perceptual_feature_sha256",
            "formant_analysis_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        _ratio(self.score_threshold, name="score_threshold")
        if self.maximum_labels <= 0 or self.maximum_labels > len(MusicalClass):
            raise ValueError("maximum_labels is outside the musical-class range")
        if tuple(item.musical_class for item in self.scores) != tuple(MusicalClass):
            raise ValueError("scores must contain all 27 musical classes in canonical order")
        if len(MusicalClass) != 27:
            raise ValueError("the canonical musical taxonomy must contain exactly 27 classes")
        expected_selected = tuple(
            item.musical_class for item in self.scores if item.selected
        )
        if self.selected_classes != expected_selected:
            raise ValueError("selected_classes is inconsistent with score flags")
        if not self.selected_classes:
            raise ValueError("at least one musical class must be selected")
        if len(self.selected_classes) > self.maximum_labels:
            raise ValueError("selected class count exceeds maximum_labels")
        if tuple(dict.fromkeys(self.selected_classes)) != self.selected_classes:
            raise ValueError("selected_classes must be unique and ordered")
        _ratio(self.confidence, name="confidence")
        _ratio(self.ambiguity, name="ambiguity")
        if not math.isclose(self.confidence + self.ambiguity, 1.0, abs_tol=1e-12):
            raise ValueError("confidence and ambiguity must sum to one")
        if not self.evidence or any(
            not item or item.strip() != item for item in self.evidence
        ):
            raise ValueError("evidence must contain normalized non-empty entries")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    @property
    def score_map(self) -> dict[str, float]:
        return {item.musical_class.value: item.score for item in self.scores}

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "behavior_classification_sha256": self.behavior_classification_sha256,
            "perceptual_feature_sha256": self.perceptual_feature_sha256,
            "formant_analysis_sha256": self.formant_analysis_sha256,
            "score_threshold": self.score_threshold,
            "maximum_labels": self.maximum_labels,
            "scores": [item.to_dict() for item in self.scores],
            "selected_classes": [item.value for item in self.selected_classes],
            "confidence": self.confidence,
            "ambiguity": self.ambiguity,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        rendered = json.dumps(
            self._content_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(rendered).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["score_map"] = self.score_map
        result["analysis_sha256"] = self.analysis_sha256
        return result


class ConversionMode(str, Enum):
    STABLE_CYCLE = "stable_cycle"
    EVOLVING_HARMONICS = "evolving_harmonics"
    DYNAMIC_PITCH = "dynamic_pitch"
    SPECTRAL_RECONSTRUCTION = "spectral_reconstruction"
    HYBRID = "hybrid"


class ModeDecisionStatus(str, Enum):
    SELECTED = "selected"
    OVERRIDDEN = "overridden"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ModeExecutionPath:
    mode: ConversionMode
    module: str
    callable_name: str
    strategy_argument: str | None
    purpose: str

    def __post_init__(self) -> None:
        for name in ("module", "callable_name", "purpose"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a non-empty normalized string")
        if self.strategy_argument is not None and (
            not self.strategy_argument
            or self.strategy_argument.strip() != self.strategy_argument
        ):
            raise ValueError("strategy_argument must be normalized when defined")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "module": self.module,
            "callable_name": self.callable_name,
            "strategy_argument": self.strategy_argument,
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class ModeScore:
    mode: ConversionMode
    raw_score: float
    score: float
    explanation: str

    def __post_init__(self) -> None:
        if _finite(self.raw_score, name="raw_score") < 0.0:
            raise ValueError("raw_score must not be negative")
        _ratio(self.score, name="score")
        if not self.explanation or self.explanation.strip() != self.explanation:
            raise ValueError("explanation must be a non-empty normalized string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "raw_score": self.raw_score,
            "score": self.score,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class ModeDecision:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    behavior_classification_sha256: str
    musical_classification_sha256: str
    perceptual_feature_sha256: str
    spectral_evolution_analysis_sha256: str
    status: ModeDecisionStatus
    selected_mode: ConversionMode | None
    requested_override: ConversionMode | None
    scores: tuple[ModeScore, ...]
    confidence: float
    ambiguity: float
    execution_path: ModeExecutionPath | None
    warnings: tuple[str, ...]
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported mode-decision schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "behavior_classification_sha256",
            "musical_classification_sha256",
            "perceptual_feature_sha256",
            "spectral_evolution_analysis_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if tuple(item.mode for item in self.scores) != tuple(ConversionMode):
            raise ValueError("scores must contain every conversion mode in canonical order")
        if not math.isclose(sum(item.score for item in self.scores), 1.0, abs_tol=1e-12):
            raise ValueError("normalized mode scores must sum to one")
        _ratio(self.confidence, name="confidence")
        _ratio(self.ambiguity, name="ambiguity")
        if not math.isclose(self.confidence + self.ambiguity, 1.0, abs_tol=1e-12):
            raise ValueError("confidence and ambiguity must sum to one")
        if self.status is ModeDecisionStatus.REJECTED:
            if self.selected_mode is not None or self.execution_path is not None:
                raise ValueError("rejected decisions must not expose a mode or execution path")
        else:
            if self.selected_mode is None or self.execution_path is None:
                raise ValueError("accepted decisions require a mode and execution path")
            if self.execution_path.mode is not self.selected_mode:
                raise ValueError("execution path does not match selected mode")
        if self.status is ModeDecisionStatus.OVERRIDDEN:
            if self.requested_override is None or self.requested_override is not self.selected_mode:
                raise ValueError("overridden decisions must select the requested mode")
        elif self.status is ModeDecisionStatus.SELECTED and self.requested_override is not None:
            raise ValueError("automatic selections must not expose requested_override")
        if any(not item or item.strip() != item for item in self.warnings):
            raise ValueError("warnings must contain normalized entries")
        if not self.evidence or any(
            not item or item.strip() != item for item in self.evidence
        ):
            raise ValueError("evidence must contain normalized non-empty entries")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    @property
    def score_map(self) -> dict[str, float]:
        return {item.mode.value: item.score for item in self.scores}

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "behavior_classification_sha256": self.behavior_classification_sha256,
            "musical_classification_sha256": self.musical_classification_sha256,
            "perceptual_feature_sha256": self.perceptual_feature_sha256,
            "spectral_evolution_analysis_sha256": self.spectral_evolution_analysis_sha256,
            "status": self.status.value,
            "selected_mode": None if self.selected_mode is None else self.selected_mode.value,
            "requested_override": (
                None if self.requested_override is None else self.requested_override.value
            ),
            "scores": [item.to_dict() for item in self.scores],
            "confidence": self.confidence,
            "ambiguity": self.ambiguity,
            "execution_path": (
                None if self.execution_path is None else self.execution_path.to_dict()
            ),
            "warnings": list(self.warnings),
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        rendered = json.dumps(
            self._content_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(rendered).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["score_map"] = self.score_map
        result["analysis_sha256"] = self.analysis_sha256
        return result
