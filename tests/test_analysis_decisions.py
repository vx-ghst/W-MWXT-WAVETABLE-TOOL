from __future__ import annotations

import json
from dataclasses import replace

import pytest

from w_mwxt_wavetable_tool.analysis.classification import (
    ClassificationFeature,
    SourceClass,
    SourceClassScore,
    SourceClassification,
)
from w_mwxt_wavetable_tool.analysis.decisions import (
    DecisionStatus,
    EngineeringDecision,
    EngineeringRecommendation,
    RecommendationCode,
    RecommendationPriority,
    decide_wavetable_readiness,
)


HASH = "a" * 64
SIGNAL_HASH = "b" * 64
SPECTRAL_HASH = "c" * 64
HARMONIC_HASH = "d" * 64


def classification(
    *,
    source_class: SourceClass = SourceClass.STABLE_TONAL,
    confidence: float = 0.82,
    active: float = 1.0,
    tonal: float = 0.89,
    stability: float = 0.85,
    instability: float = 0.17,
    noise: float = 0.07,
    transient: float = 0.26,
    complexity: float = 0.16,
) -> SourceClassification:
    if source_class is SourceClass.SILENT:
        normalized = {item: (1.0 if item is SourceClass.SILENT else 0.0) for item in SourceClass}
    else:
        normalized = {item: 0.08 for item in SourceClass}
        normalized[source_class] = 0.60
    scores = tuple(
        SourceClassScore(source_class=item, raw_score=normalized[item], score=normalized[item])
        for item in SourceClass
    )
    feature_values = {
        "active_presence": active,
        "periodicity": tonal,
        "harmonicity": tonal,
        "spectral_concentration": tonal,
        "tonal_presence": tonal,
        "global_stability": stability,
        "temporal_instability": instability,
        "noise_presence": noise,
        "transient_activity": transient,
        "spectral_complexity": complexity,
    }
    return SourceClassification(
        schema_version=1,
        sample_rate=48_000,
        sample_count=48_000,
        sample_sha256=HASH,
        signal_analysis_sha256=SIGNAL_HASH,
        spectral_analysis_sha256=SPECTRAL_HASH,
        harmonic_perceptual_analysis_sha256=HARMONIC_HASH,
        source_class=source_class,
        confidence=confidence,
        ambiguity=1.0 - confidence,
        class_scores=scores,
        features=tuple(
            ClassificationFeature(name=name, value=value, explanation=f"{name} explanation")
            for name, value in feature_values.items()
        ),
        evidence=("classification evidence",),
        classification_reason="classification reason",
    )


def codes(decision: EngineeringDecision) -> set[RecommendationCode]:
    return {item.code for item in decision.recommendations}


def test_stable_tonal_is_ready():
    assert decide_wavetable_readiness(classification()).status is DecisionStatus.READY


def test_silent_is_not_recommended():
    result = decide_wavetable_readiness(
        classification(
            source_class=SourceClass.SILENT,
            active=0.0,
            tonal=0.0,
            stability=0.0,
            instability=0.0,
            noise=0.0,
            transient=0.0,
            complexity=0.0,
        )
    )
    assert result.status is DecisionStatus.NOT_RECOMMENDED


def test_very_low_active_content_is_not_recommended():
    result = decide_wavetable_readiness(classification(active=0.01))
    assert result.status is DecisionStatus.NOT_RECOMMENDED


def test_evolving_tonal_requires_review():
    result = decide_wavetable_readiness(
        classification(
            source_class=SourceClass.EVOLVING_TONAL,
            stability=0.45,
            instability=0.65,
        )
    )
    assert result.status is DecisionStatus.REVIEW


def test_noisy_texture_requires_review():
    result = decide_wavetable_readiness(
        classification(source_class=SourceClass.NOISY_TEXTURE, tonal=0.30, noise=0.80)
    )
    assert result.status is DecisionStatus.REVIEW


def test_transient_rich_requires_review():
    result = decide_wavetable_readiness(
        classification(source_class=SourceClass.TRANSIENT_RICH, tonal=0.35, transient=0.85)
    )
    assert result.status is DecisionStatus.REVIEW


def test_mixed_complex_requires_review():
    result = decide_wavetable_readiness(
        classification(source_class=SourceClass.MIXED_COMPLEX, tonal=0.50, complexity=0.80)
    )
    assert result.status is DecisionStatus.REVIEW


def test_readiness_and_risk_sum_to_one():
    result = decide_wavetable_readiness(classification())
    assert result.readiness_score + result.risk_score == pytest.approx(1.0)


def test_hash_is_deterministic():
    assert decide_wavetable_readiness(classification()).analysis_sha256 == decide_wavetable_readiness(classification()).analysis_sha256


def test_hash_changes_with_feature():
    assert decide_wavetable_readiness(classification()).analysis_sha256 != decide_wavetable_readiness(classification(noise=0.20)).analysis_sha256


def test_to_dict_is_finite_json():
    rendered = json.dumps(decide_wavetable_readiness(classification()).to_dict(), allow_nan=False)
    assert "NaN" not in rendered and "Infinity" not in rendered


def test_classification_hash_link_is_preserved():
    source = classification()
    result = decide_wavetable_readiness(source)
    assert result.source_classification_sha256 == source.analysis_sha256


def test_sample_identity_is_preserved():
    result = decide_wavetable_readiness(classification())
    assert (result.sample_rate, result.sample_count, result.sample_sha256) == (48_000, 48_000, HASH)


def test_recommendations_are_nonempty():
    assert decide_wavetable_readiness(classification()).recommendations


def test_recommendations_are_never_automated():
    assert all(not item.automated for item in decide_wavetable_readiness(classification()).recommendations)


def test_recommendation_order_is_deterministic():
    first = decide_wavetable_readiness(classification(noise=0.80, transient=0.80, complexity=0.90))
    second = decide_wavetable_readiness(classification(noise=0.80, transient=0.80, complexity=0.90))
    assert first.recommendation_codes == second.recommendation_codes


def test_missing_required_feature_raises():
    source = classification()
    incomplete = replace(source, features=source.features[:-1])
    with pytest.raises(ValueError, match="missing required features"):
        decide_wavetable_readiness(incomplete)


def test_invalid_classification_hash_raises(monkeypatch):
    source = classification()
    monkeypatch.setattr(SourceClassification, "analysis_sha256", property(lambda self: "bad"))
    with pytest.raises(ValueError, match="analysis hash is invalid"):
        decide_wavetable_readiness(source)


def test_noise_threshold_adds_recommendation():
    assert RecommendationCode.EXCESS_NOISE in codes(decide_wavetable_readiness(classification(noise=0.46)))


def test_transient_threshold_adds_recommendation():
    assert RecommendationCode.TRANSIENT_DOMINANCE in codes(decide_wavetable_readiness(classification(transient=0.46)))


def test_instability_threshold_adds_recommendation():
    assert RecommendationCode.TEMPORAL_INSTABILITY in codes(decide_wavetable_readiness(classification(instability=0.46)))


def test_complexity_threshold_adds_recommendation():
    assert RecommendationCode.SPECTRAL_COMPLEXITY in codes(decide_wavetable_readiness(classification(complexity=0.66)))


def test_low_confidence_adds_recommendation():
    assert RecommendationCode.LOW_CLASSIFICATION_CONFIDENCE in codes(decide_wavetable_readiness(classification(confidence=0.54)))


def test_weak_tonal_core_adds_recommendation():
    assert RecommendationCode.WEAK_TONAL_CORE in codes(decide_wavetable_readiness(classification(tonal=0.54)))


def test_stable_tonal_adds_preservation_recommendation():
    assert RecommendationCode.PRESERVE_TONAL_CORE in codes(decide_wavetable_readiness(classification()))


def test_evolving_tonal_adds_preservation_recommendation():
    result = decide_wavetable_readiness(classification(source_class=SourceClass.EVOLVING_TONAL))
    assert RecommendationCode.PRESERVE_EVOLUTION in codes(result)


def test_ready_adds_extraction_recommendation():
    assert RecommendationCode.READY_FOR_EXTRACTION in codes(decide_wavetable_readiness(classification()))


def test_silent_adds_blocker():
    result = decide_wavetable_readiness(
        classification(source_class=SourceClass.SILENT, active=0.0, tonal=0.0, stability=0.0)
    )
    assert result.blockers


def test_ready_has_no_blocker():
    assert not decide_wavetable_readiness(classification()).blockers


def test_decision_reason_is_nonempty():
    assert decide_wavetable_readiness(classification()).decision_reason


def test_evidence_has_canonical_length():
    assert len(decide_wavetable_readiness(classification()).evidence) == 11


def test_recommendation_rejects_automation():
    with pytest.raises(ValueError, match="must never be automated"):
        EngineeringRecommendation(
            code=RecommendationCode.MANUAL_REVIEW,
            priority=RecommendationPriority.LOW,
            title="Title",
            rationale="Rationale",
            suggested_action="Action",
            evidence=("evidence",),
            automated=True,
        )


def test_decision_rejects_non_complementary_scores():
    valid = decide_wavetable_readiness(classification())
    with pytest.raises(ValueError, match="must sum to one"):
        replace(valid, readiness_score=0.5, risk_score=0.4)


def test_decision_rejects_invalid_hash():
    valid = decide_wavetable_readiness(classification())
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(valid, sample_sha256="BAD")


def test_enum_values_are_stable():
    assert [item.value for item in DecisionStatus] == ["ready", "review", "not_recommended"]
