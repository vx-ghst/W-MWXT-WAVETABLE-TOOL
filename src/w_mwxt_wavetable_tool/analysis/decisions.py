from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any

from .classification import SourceClass, SourceClassification


class DecisionStatus(str, Enum):
    READY = "ready"
    REVIEW = "review"
    NOT_RECOMMENDED = "not_recommended"


class RecommendationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"


class RecommendationCode(str, Enum):
    SILENT_SOURCE = "silent_source"
    LOW_ACTIVE_CONTENT = "low_active_content"
    LOW_CLASSIFICATION_CONFIDENCE = "low_classification_confidence"
    WEAK_TONAL_CORE = "weak_tonal_core"
    TEMPORAL_INSTABILITY = "temporal_instability"
    EXCESS_NOISE = "excess_noise"
    TRANSIENT_DOMINANCE = "transient_dominance"
    SPECTRAL_COMPLEXITY = "spectral_complexity"
    PRESERVE_TONAL_CORE = "preserve_tonal_core"
    PRESERVE_EVOLUTION = "preserve_evolution"
    MANUAL_REVIEW = "manual_review"
    READY_FOR_EXTRACTION = "ready_for_extraction"


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


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


@dataclass(frozen=True, slots=True)
class EngineeringRecommendation:
    code: RecommendationCode
    priority: RecommendationPriority
    title: str
    rationale: str
    suggested_action: str
    evidence: tuple[str, ...]
    automated: bool = False

    def __post_init__(self) -> None:
        for name in ("title", "rationale", "suggested_action"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a non-empty normalized string")
        if not self.evidence or any(not item or item.strip() != item for item in self.evidence):
            raise ValueError("recommendation evidence must contain normalized entries")
        if self.automated:
            raise ValueError("CODE V5-D recommendations must never be automated")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "priority": self.priority.value,
            "title": self.title,
            "rationale": self.rationale,
            "suggested_action": self.suggested_action,
            "evidence": list(self.evidence),
            "automated": self.automated,
        }


@dataclass(frozen=True, slots=True)
class EngineeringDecision:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    source_classification_sha256: str
    status: DecisionStatus
    readiness_score: float
    risk_score: float
    recommendations: tuple[EngineeringRecommendation, ...]
    blockers: tuple[str, ...]
    evidence: tuple[str, ...]
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported engineering-decision schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in ("sample_sha256", "source_classification_sha256"):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        _ratio(self.readiness_score, name="readiness_score")
        _ratio(self.risk_score, name="risk_score")
        if not math.isclose(self.readiness_score + self.risk_score, 1.0, abs_tol=1e-12):
            raise ValueError("readiness_score and risk_score must sum to one")
        if not self.recommendations:
            raise ValueError("recommendations must not be empty")
        codes = tuple(item.code for item in self.recommendations)
        if len(set(codes)) != len(codes):
            raise ValueError("recommendation codes must be unique")
        if any(not item or item.strip() != item for item in self.blockers):
            raise ValueError("blockers must contain normalized entries")
        if any(not item or item.strip() != item for item in self.evidence):
            raise ValueError("evidence must contain normalized entries")
        if not self.evidence:
            raise ValueError("evidence must not be empty")
        if not self.decision_reason or self.decision_reason.strip() != self.decision_reason:
            raise ValueError("decision_reason must be a non-empty normalized string")
        if self.status is DecisionStatus.NOT_RECOMMENDED and not self.blockers:
            raise ValueError("not_recommended decisions require at least one blocker")
        if self.status is not DecisionStatus.NOT_RECOMMENDED and self.blockers:
            raise ValueError("only not_recommended decisions may expose blockers")

    @property
    def recommendation_codes(self) -> tuple[str, ...]:
        return tuple(item.code.value for item in self.recommendations)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "source_classification_sha256": self.source_classification_sha256,
            "status": self.status.value,
            "readiness_score": self.readiness_score,
            "risk_score": self.risk_score,
            "recommendations": [item.to_dict() for item in self.recommendations],
            "recommendation_codes": list(self.recommendation_codes),
            "blockers": list(self.blockers),
            "evidence": list(self.evidence),
            "decision_reason": self.decision_reason,
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
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _feature_map(classification: SourceClassification) -> dict[str, float]:
    result = {feature.name: feature.value for feature in classification.features}
    required = {
        "active_presence",
        "tonal_presence",
        "global_stability",
        "temporal_instability",
        "noise_presence",
        "transient_activity",
        "spectral_complexity",
    }
    missing = sorted(required.difference(result))
    if missing:
        raise ValueError(f"classification is missing required features: {', '.join(missing)}")
    for name in required:
        _ratio(result[name], name=f"classification feature {name}")
    return result


def _recommendation(
    code: RecommendationCode,
    priority: RecommendationPriority,
    title: str,
    rationale: str,
    suggested_action: str,
    *evidence: str,
) -> EngineeringRecommendation:
    return EngineeringRecommendation(
        code=code,
        priority=priority,
        title=title,
        rationale=rationale,
        suggested_action=suggested_action,
        evidence=tuple(evidence),
        automated=False,
    )


def _priority_rank(priority: RecommendationPriority) -> int:
    return {
        RecommendationPriority.BLOCKING: 0,
        RecommendationPriority.HIGH: 1,
        RecommendationPriority.MEDIUM: 2,
        RecommendationPriority.LOW: 3,
    }[priority]


def _decision_reason(status: DecisionStatus, source_class: SourceClass) -> str:
    if status is DecisionStatus.READY:
        return (
            "The linked measurements support direct wavetable extraction with only "
            "non-destructive review recommendations."
        )
    if status is DecisionStatus.NOT_RECOMMENDED:
        return (
            "The source lacks enough usable active content for a defensible extraction "
            "decision."
        )
    if source_class is SourceClass.EVOLVING_TONAL:
        return (
            "The source is usable, but its tonal evolution should be segmented or "
            "preserved deliberately before extraction."
        )
    return (
        "The source is analyzable, but one or more measured risks require manual "
        "engineering review before extraction."
    )


def decide_wavetable_readiness(
    classification: SourceClassification,
) -> EngineeringDecision:
    """Convert an accepted source classification into an auditable recommendation set."""

    if not _hash_is_valid(classification.analysis_sha256):
        raise ValueError("source classification analysis hash is invalid")
    features = _feature_map(classification)

    active = features["active_presence"]
    tonal = features["tonal_presence"]
    stability = features["global_stability"]
    instability = features["temporal_instability"]
    noise = features["noise_presence"]
    transient = features["transient_activity"]
    complexity = features["spectral_complexity"]
    confidence = _ratio(classification.confidence, name="classification confidence")

    readiness = _clip01(
        0.25 * active
        + 0.25 * tonal
        + 0.20 * stability
        + 0.10 * confidence
        + 0.075 * (1.0 - noise)
        + 0.075 * (1.0 - transient)
        + 0.05 * (1.0 - complexity)
    )
    if classification.source_class is SourceClass.STABLE_TONAL:
        readiness = _clip01(readiness + 0.03)
    elif classification.source_class in {
        SourceClass.NOISY_TEXTURE,
        SourceClass.TRANSIENT_RICH,
    }:
        readiness = _clip01(readiness - 0.05)
    elif classification.source_class is SourceClass.MIXED_COMPLEX:
        readiness = _clip01(readiness - 0.02)
    if classification.source_class is SourceClass.SILENT:
        readiness = 0.0
    risk = float(1.0 - readiness)

    recommendations: list[EngineeringRecommendation] = []
    blockers: list[str] = []

    if classification.source_class is SourceClass.SILENT:
        blockers.append("The classified source is silent.")
        recommendations.append(
            _recommendation(
                RecommendationCode.SILENT_SOURCE,
                RecommendationPriority.BLOCKING,
                "Provide an audible source",
                "No active signal is available for wavetable extraction.",
                "Replace the source or isolate an audible region before continuing.",
                f"source_class={classification.source_class.value}",
                f"active_presence={active:.6f}",
            )
        )
    elif active <= 0.05:
        blockers.append("Active material occupies too little of the source.")
        recommendations.append(
            _recommendation(
                RecommendationCode.LOW_ACTIVE_CONTENT,
                RecommendationPriority.BLOCKING,
                "Isolate active material",
                "The measured active presence is too low for a reliable extraction decision.",
                "Trim silence and provide a sustained active region.",
                f"active_presence={active:.6f}",
            )
        )
    elif active < 0.40:
        recommendations.append(
            _recommendation(
                RecommendationCode.LOW_ACTIVE_CONTENT,
                RecommendationPriority.HIGH,
                "Trim inactive regions",
                "Long inactive regions reduce the reliability of frame selection.",
                "Trim silence or isolate the sustained portion before extraction.",
                f"active_presence={active:.6f}",
            )
        )

    if confidence < 0.55:
        recommendations.append(
            _recommendation(
                RecommendationCode.LOW_CLASSIFICATION_CONFIDENCE,
                RecommendationPriority.MEDIUM,
                "Review overlapping source evidence",
                "The source-family winner is not sufficiently separated from alternatives.",
                "Inspect the class scores and choose the intended extraction strategy manually.",
                f"classification_confidence={confidence:.6f}",
                f"classification_ambiguity={classification.ambiguity:.6f}",
            )
        )
    if tonal < 0.55 and classification.source_class is not SourceClass.SILENT:
        recommendations.append(
            _recommendation(
                RecommendationCode.WEAK_TONAL_CORE,
                RecommendationPriority.MEDIUM,
                "Choose a clearer tonal region",
                "Weak periodic, harmonic, or concentrated energy may produce an unstable table.",
                "Select a more periodic region or intentionally accept a texture-driven result.",
                f"tonal_presence={tonal:.6f}",
            )
        )
    if instability > 0.45 or stability < 0.55:
        recommendations.append(
            _recommendation(
                RecommendationCode.TEMPORAL_INSTABILITY,
                RecommendationPriority.MEDIUM,
                "Control temporal evolution",
                "Pitch, phase, amplitude, or spectrum changes materially across the source.",
                "Segment the source or preserve the evolution intentionally across table frames.",
                f"global_stability={stability:.6f}",
                f"temporal_instability={instability:.6f}",
            )
        )
    if noise > 0.45:
        recommendations.append(
            _recommendation(
                RecommendationCode.EXCESS_NOISE,
                RecommendationPriority.HIGH,
                "Review noise before extraction",
                "Residual and spectral noise evidence is high enough to dominate frame content.",
                "Reduce unwanted noise while preserving any texture that is musically intentional.",
                f"noise_presence={noise:.6f}",
            )
        )
    if transient > 0.45:
        recommendations.append(
            _recommendation(
                RecommendationCode.TRANSIENT_DOMINANCE,
                RecommendationPriority.HIGH,
                "Use a sustained region",
                "Transient and change evidence may create clicks or unstable frame matching.",
                "Exclude attacks or attenuate transient-dominated regions before extraction.",
                f"transient_activity={transient:.6f}",
            )
        )
    if complexity > 0.65:
        recommendations.append(
            _recommendation(
                RecommendationCode.SPECTRAL_COMPLEXITY,
                RecommendationPriority.MEDIUM,
                "Reduce spectral ambiguity",
                "The spectral distribution is complex enough to make frame correspondence ambiguous.",
                "Use a shorter coherent region or increase frame density during later processing.",
                f"spectral_complexity={complexity:.6f}",
            )
        )

    if classification.source_class is SourceClass.STABLE_TONAL and not blockers:
        recommendations.append(
            _recommendation(
                RecommendationCode.PRESERVE_TONAL_CORE,
                RecommendationPriority.LOW,
                "Preserve the stable tonal core",
                "The source has a strong stable tonal identity.",
                "Avoid unnecessary cleanup that would alter the accepted harmonic balance.",
                f"tonal_presence={tonal:.6f}",
                f"global_stability={stability:.6f}",
            )
        )
    elif classification.source_class is SourceClass.EVOLVING_TONAL and not blockers:
        recommendations.append(
            _recommendation(
                RecommendationCode.PRESERVE_EVOLUTION,
                RecommendationPriority.LOW,
                "Preserve intended evolution",
                "The source remains tonal while changing materially over time.",
                "Map the evolution deliberately across frames instead of flattening it.",
                f"temporal_instability={instability:.6f}",
            )
        )

    if not recommendations:
        recommendations.append(
            _recommendation(
                RecommendationCode.MANUAL_REVIEW,
                RecommendationPriority.LOW,
                "Perform a final listening review",
                "No threshold-specific issue was raised, but the source is not a canonical stable tonal case.",
                "Confirm the intended timbral result before extraction.",
                f"source_class={classification.source_class.value}",
            )
        )

    if blockers:
        status = DecisionStatus.NOT_RECOMMENDED
    else:
        high_priority = any(
            item.priority in {RecommendationPriority.HIGH, RecommendationPriority.BLOCKING}
            for item in recommendations
        )
        status = (
            DecisionStatus.READY
            if (
                classification.source_class is SourceClass.STABLE_TONAL
                and readiness >= 0.72
                and confidence >= 0.55
                and not high_priority
            )
            else DecisionStatus.REVIEW
        )

    if status is DecisionStatus.READY:
        recommendations.append(
            _recommendation(
                RecommendationCode.READY_FOR_EXTRACTION,
                RecommendationPriority.LOW,
                "Proceed to controlled extraction",
                "Readiness exceeds the acceptance threshold without a high-priority risk.",
                "Continue with deterministic frame generation and retain the current evidence report.",
                f"readiness_score={readiness:.6f}",
            )
        )

    code_order = {code: index for index, code in enumerate(RecommendationCode)}
    recommendations.sort(
        key=lambda item: (_priority_rank(item.priority), code_order[item.code])
    )

    evidence = (
        f"source_class={classification.source_class.value}",
        f"classification_confidence={confidence:.6f}",
        f"active_presence={active:.6f}",
        f"tonal_presence={tonal:.6f}",
        f"global_stability={stability:.6f}",
        f"temporal_instability={instability:.6f}",
        f"noise_presence={noise:.6f}",
        f"transient_activity={transient:.6f}",
        f"spectral_complexity={complexity:.6f}",
        f"readiness_score={readiness:.6f}",
        f"risk_score={risk:.6f}",
    )

    return EngineeringDecision(
        schema_version=1,
        sample_rate=classification.sample_rate,
        sample_count=classification.sample_count,
        sample_sha256=classification.sample_sha256,
        source_classification_sha256=classification.analysis_sha256,
        status=status,
        readiness_score=readiness,
        risk_score=risk,
        recommendations=tuple(recommendations),
        blockers=tuple(blockers),
        evidence=evidence,
        decision_reason=_decision_reason(status, classification.source_class),
    )
