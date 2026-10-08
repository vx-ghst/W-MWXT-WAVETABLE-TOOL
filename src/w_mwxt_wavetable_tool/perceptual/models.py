from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any


PERCEPTUAL_FEATURE_NAMES = (
    "low_frequency_power",
    "fundamental_presence",
    "brightness",
    "hardness",
    "saturation",
    "density",
    "motion",
    "tonalness",
    "noisiness",
)


def _finite(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked):
        raise ValueError(f"{name} must be finite")
    return checked


def _ratio(value: float, *, name: str) -> float:
    checked = _finite(value, name=name)
    if not 0.0 <= checked <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return checked


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
class PerceptualFeatureVector:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    signal_analysis_sha256: str
    signal_extension_analysis_sha256: str
    spectral_analysis_sha256: str
    harmonic_perceptual_analysis_sha256: str
    spectral_evolution_analysis_sha256: str
    formant_analysis_sha256: str
    low_frequency_power: float
    fundamental_presence: float
    brightness: float
    hardness: float
    saturation: float
    density: float
    motion: float
    tonalness: float
    noisiness: float
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported perceptual-feature schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "signal_analysis_sha256",
            "signal_extension_analysis_sha256",
            "spectral_analysis_sha256",
            "harmonic_perceptual_analysis_sha256",
            "spectral_evolution_analysis_sha256",
            "formant_analysis_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        for name in PERCEPTUAL_FEATURE_NAMES:
            _ratio(getattr(self, name), name=name)
        if not self.evidence or any(
            not item or item.strip() != item for item in self.evidence
        ):
            raise ValueError("evidence must contain normalized non-empty entries")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    @property
    def feature_map(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in PERCEPTUAL_FEATURE_NAMES}

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "signal_analysis_sha256": self.signal_analysis_sha256,
            "signal_extension_analysis_sha256": self.signal_extension_analysis_sha256,
            "spectral_analysis_sha256": self.spectral_analysis_sha256,
            "harmonic_perceptual_analysis_sha256": self.harmonic_perceptual_analysis_sha256,
            "spectral_evolution_analysis_sha256": self.spectral_evolution_analysis_sha256,
            "formant_analysis_sha256": self.formant_analysis_sha256,
            "features": self.feature_map,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result.update(self.feature_map)
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class PerceptualFeatureDelta:
    name: str
    absolute_delta: float
    weight: float
    weighted_contribution: float

    def __post_init__(self) -> None:
        if self.name not in PERCEPTUAL_FEATURE_NAMES:
            raise ValueError("unknown perceptual feature name")
        _ratio(self.absolute_delta, name="absolute_delta")
        if _finite(self.weight, name="weight") <= 0.0:
            raise ValueError("weight must be positive")
        if _finite(self.weighted_contribution, name="weighted_contribution") < 0.0:
            raise ValueError("weighted_contribution must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "absolute_delta": self.absolute_delta,
            "weight": self.weight,
            "weighted_contribution": self.weighted_contribution,
        }


@dataclass(frozen=True, slots=True)
class PerceptualDistance:
    schema_version: int
    left_feature_sha256: str
    right_feature_sha256: str
    deltas: tuple[PerceptualFeatureDelta, ...]
    distance: float
    redundancy_threshold: float
    audibly_redundant: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported perceptual-distance schema version")
        for name in ("left_feature_sha256", "right_feature_sha256"):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if tuple(delta.name for delta in self.deltas) != PERCEPTUAL_FEATURE_NAMES:
            raise ValueError("deltas must contain every feature in canonical order")
        _ratio(self.distance, name="distance")
        threshold = _ratio(self.redundancy_threshold, name="redundancy_threshold")
        if self.audibly_redundant != (self.distance <= threshold):
            raise ValueError("audibly_redundant is inconsistent with threshold")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "left_feature_sha256": self.left_feature_sha256,
            "right_feature_sha256": self.right_feature_sha256,
            "deltas": [delta.to_dict() for delta in self.deltas],
            "distance": self.distance,
            "redundancy_threshold": self.redundancy_threshold,
            "audibly_redundant": self.audibly_redundant,
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
class PerceptualDistancePair:
    left_index: int
    right_index: int
    distance: PerceptualDistance

    def __post_init__(self) -> None:
        if self.left_index < 0 or self.right_index <= self.left_index:
            raise ValueError("distance pair indexes must form a canonical pair")

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_index": self.left_index,
            "right_index": self.right_index,
            "distance": self.distance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PerceptualDistanceMatrix:
    schema_version: int
    feature_sha256: tuple[str, ...]
    pairs: tuple[PerceptualDistancePair, ...]
    redundant_groups: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported perceptual-distance-matrix schema version")
        if len(self.feature_sha256) < 2:
            raise ValueError("at least two perceptual vectors are required")
        if any(not _hash_is_valid(value) for value in self.feature_sha256):
            raise ValueError("feature_sha256 contains an invalid hash")
        expected = tuple(
            (left, right)
            for left in range(len(self.feature_sha256))
            for right in range(left + 1, len(self.feature_sha256))
        )
        actual = tuple((pair.left_index, pair.right_index) for pair in self.pairs)
        if actual != expected:
            raise ValueError("distance pairs must use canonical order")
        flattened = [index for group in self.redundant_groups for index in group]
        if len(flattened) != len(set(flattened)):
            raise ValueError("redundant groups must not overlap")
        if any(
            tuple(sorted(group)) != group or len(group) < 2
            for group in self.redundant_groups
        ):
            raise ValueError("redundant groups must be sorted and contain at least two indexes")
        if any(index < 0 or index >= len(self.feature_sha256) for index in flattened):
            raise ValueError("redundant group index is outside the feature range")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "feature_sha256": list(self.feature_sha256),
            "pairs": [pair.to_dict() for pair in self.pairs],
            "redundant_groups": [list(group) for group in self.redundant_groups],
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class SweepTransition:
    index: int
    left_feature_sha256: str
    right_feature_sha256: str
    distance: float
    discontinuity: bool

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("transition index must not be negative")
        for name in ("left_feature_sha256", "right_feature_sha256"):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        _ratio(self.distance, name="distance")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "left_feature_sha256": self.left_feature_sha256,
            "right_feature_sha256": self.right_feature_sha256,
            "distance": self.distance,
            "discontinuity": self.discontinuity,
        }


@dataclass(frozen=True, slots=True)
class SweepContinuityAnalysis:
    schema_version: int
    feature_sha256: tuple[str, ...]
    discontinuity_threshold: float
    transitions: tuple[SweepTransition, ...]
    mean_distance: float
    maximum_distance: float
    continuity_score: float
    discontinuity_count: int
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported sweep-continuity schema version")
        if not self.feature_sha256:
            raise ValueError("feature_sha256 must not be empty")
        if any(not _hash_is_valid(value) for value in self.feature_sha256):
            raise ValueError("feature_sha256 contains an invalid hash")
        threshold = _ratio(self.discontinuity_threshold, name="discontinuity_threshold")
        if len(self.transitions) != max(0, len(self.feature_sha256) - 1):
            raise ValueError("transition count is inconsistent")
        if tuple(transition.index for transition in self.transitions) != tuple(
            range(len(self.transitions))
        ):
            raise ValueError("transition indexes must be contiguous")
        for index, transition in enumerate(self.transitions):
            if transition.left_feature_sha256 != self.feature_sha256[index]:
                raise ValueError("transition left hash is inconsistent")
            if transition.right_feature_sha256 != self.feature_sha256[index + 1]:
                raise ValueError("transition right hash is inconsistent")
            if transition.discontinuity != (transition.distance > threshold):
                raise ValueError("transition discontinuity flag is inconsistent")
        for name in ("mean_distance", "maximum_distance", "continuity_score"):
            _ratio(getattr(self, name), name=name)
        if self.discontinuity_count != sum(
            transition.discontinuity for transition in self.transitions
        ):
            raise ValueError("discontinuity_count is inconsistent")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "feature_sha256": list(self.feature_sha256),
            "discontinuity_threshold": self.discontinuity_threshold,
            "transitions": [transition.to_dict() for transition in self.transitions],
            "mean_distance": self.mean_distance,
            "maximum_distance": self.maximum_distance,
            "continuity_score": self.continuity_score,
            "discontinuity_count": self.discontinuity_count,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result
