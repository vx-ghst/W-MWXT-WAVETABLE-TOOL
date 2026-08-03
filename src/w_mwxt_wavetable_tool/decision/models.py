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
