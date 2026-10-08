from __future__ import annotations

import math

from .models import ConversionMode, ModeDecision, MusicalClass, MusicalClassification
from ..profiles import (
    OptimizationProfile,
    ProfileScore,
    ProfileSelection,
    profile_definition,
)


_CLASS_PROFILE_PRIORS: dict[MusicalClass, tuple[tuple[OptimizationProfile, float], ...]] = {
    MusicalClass.SUB: ((OptimizationProfile.BASS_SUB, 1.0),),
    MusicalClass.BASS: ((OptimizationProfile.BASS_SUB, 0.9), (OptimizationProfile.LEAD, 0.1)),
    MusicalClass.REESE: ((OptimizationProfile.BASS_SUB, 0.55), (OptimizationProfile.TEXTURE, 0.25), (OptimizationProfile.EXPERIMENTAL, 0.20)),
    MusicalClass.FM_BASS: ((OptimizationProfile.BASS_SUB, 0.55), (OptimizationProfile.BELL_FM, 0.35), (OptimizationProfile.EXPERIMENTAL, 0.10)),
    MusicalClass.DIRTY_BASS: ((OptimizationProfile.BASS_SUB, 0.55), (OptimizationProfile.EXPERIMENTAL, 0.30), (OptimizationProfile.TEXTURE, 0.15)),
    MusicalClass.HOOVER: ((OptimizationProfile.LEAD, 0.40), (OptimizationProfile.TEXTURE, 0.30), (OptimizationProfile.EXPERIMENTAL, 0.30)),
    MusicalClass.ACID: ((OptimizationProfile.LEAD, 0.65), (OptimizationProfile.EXPERIMENTAL, 0.20), (OptimizationProfile.BASS_SUB, 0.15)),
    MusicalClass.LEAD: ((OptimizationProfile.LEAD, 1.0),),
    MusicalClass.PAD: ((OptimizationProfile.PAD, 0.85), (OptimizationProfile.TEXTURE, 0.15)),
    MusicalClass.DRONE: ((OptimizationProfile.DRONE, 0.85), (OptimizationProfile.PAD, 0.15)),
    MusicalClass.ORGAN: ((OptimizationProfile.DRONE, 0.45), (OptimizationProfile.LEAD, 0.35), (OptimizationProfile.PAD, 0.20)),
    MusicalClass.PWM: ((OptimizationProfile.LEAD, 0.55), (OptimizationProfile.PAD, 0.25), (OptimizationProfile.EXPERIMENTAL, 0.20)),
    MusicalClass.SUPERSAW: ((OptimizationProfile.PAD, 0.45), (OptimizationProfile.LEAD, 0.35), (OptimizationProfile.TEXTURE, 0.20)),
    MusicalClass.WAVETABLE: ((OptimizationProfile.TEXTURE, 0.45), (OptimizationProfile.PAD, 0.35), (OptimizationProfile.LEAD, 0.20)),
    MusicalClass.BELL: ((OptimizationProfile.BELL_FM, 1.0),),
    MusicalClass.FM_BELL: ((OptimizationProfile.BELL_FM, 0.90), (OptimizationProfile.EXPERIMENTAL, 0.10)),
    MusicalClass.PLUCK: ((OptimizationProfile.PERCUSSIVE, 0.60), (OptimizationProfile.LEAD, 0.40)),
    MusicalClass.VOCAL: ((OptimizationProfile.VOCAL_CHOIR, 1.0),),
    MusicalClass.CHOIR: ((OptimizationProfile.VOCAL_CHOIR, 0.85), (OptimizationProfile.PAD, 0.15)),
    MusicalClass.TEXTURE: ((OptimizationProfile.TEXTURE, 0.80), (OptimizationProfile.EXPERIMENTAL, 0.20)),
    MusicalClass.DIGITAL_NOISE: ((OptimizationProfile.TEXTURE, 0.55), (OptimizationProfile.EXPERIMENTAL, 0.45)),
    MusicalClass.NOISE: ((OptimizationProfile.TEXTURE, 0.65), (OptimizationProfile.PERCUSSIVE, 0.20), (OptimizationProfile.EXPERIMENTAL, 0.15)),
    MusicalClass.PIANO: ((OptimizationProfile.PERCUSSIVE, 0.45), (OptimizationProfile.VOCAL_CHOIR, 0.30), (OptimizationProfile.BELL_FM, 0.25)),
    MusicalClass.GUITAR: ((OptimizationProfile.LEAD, 0.45), (OptimizationProfile.PERCUSSIVE, 0.30), (OptimizationProfile.VOCAL_CHOIR, 0.25)),
    MusicalClass.PERCUSSION: ((OptimizationProfile.PERCUSSIVE, 1.0),),
    MusicalClass.FX: ((OptimizationProfile.EXPERIMENTAL, 0.55), (OptimizationProfile.TEXTURE, 0.45)),
    MusicalClass.HYBRID: ((OptimizationProfile.EXPERIMENTAL, 0.45), (OptimizationProfile.TEXTURE, 0.30), (OptimizationProfile.PAD, 0.25)),
}

_MODE_PRIORS: dict[ConversionMode, tuple[tuple[OptimizationProfile, float], ...]] = {
    ConversionMode.STABLE_CYCLE: ((OptimizationProfile.BASS_SUB, 0.30), (OptimizationProfile.LEAD, 0.25), (OptimizationProfile.DRONE, 0.20), (OptimizationProfile.BELL_FM, 0.15), (OptimizationProfile.PAD, 0.10)),
    ConversionMode.EVOLVING_HARMONICS: ((OptimizationProfile.PAD, 0.30), (OptimizationProfile.TEXTURE, 0.25), (OptimizationProfile.DRONE, 0.15), (OptimizationProfile.LEAD, 0.15), (OptimizationProfile.EXPERIMENTAL, 0.15)),
    ConversionMode.DYNAMIC_PITCH: ((OptimizationProfile.EXPERIMENTAL, 0.30), (OptimizationProfile.LEAD, 0.25), (OptimizationProfile.TEXTURE, 0.20), (OptimizationProfile.PAD, 0.15), (OptimizationProfile.BASS_SUB, 0.10)),
    ConversionMode.SPECTRAL_RECONSTRUCTION: ((OptimizationProfile.VOCAL_CHOIR, 0.25), (OptimizationProfile.TEXTURE, 0.25), (OptimizationProfile.BELL_FM, 0.20), (OptimizationProfile.PERCUSSIVE, 0.20), (OptimizationProfile.EXPERIMENTAL, 0.10)),
    ConversionMode.HYBRID: ((OptimizationProfile.EXPERIMENTAL, 0.30), (OptimizationProfile.TEXTURE, 0.25), (OptimizationProfile.PAD, 0.20), (OptimizationProfile.LEAD, 0.15), (OptimizationProfile.BASS_SUB, 0.10)),
}


def _confidence(scores: tuple[ProfileScore, ...]) -> tuple[float, float]:
    ranked = sorted((item.score for item in scores), reverse=True)
    gap = ranked[0] - ranked[1]
    confidence = min(1.0, max(0.0, 0.5 + 0.5 * gap))
    return confidence, 1.0 - confidence


def select_optimization_profile(
    musical_classification: MusicalClassification,
    mode_decision: ModeDecision,
    *,
    requested_override: OptimizationProfile | None = None,
    mode_prior_cap: float = 0.20,
) -> ProfileSelection:
    """Select one of nine effective profiles with a capped conversion-mode prior."""

    cap = float(mode_prior_cap)
    if not math.isfinite(cap) or not 0.0 <= cap <= 0.25:
        raise ValueError("mode_prior_cap must be between 0 and 0.25")

    raw = {profile: 1.0e-12 for profile in OptimizationProfile}
    class_evidence: list[str] = []
    for item in musical_classification.scores:
        value = float(item.score)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("musical class scores must be finite ratios")
        if value <= 0.0:
            continue
        for profile, weight in _CLASS_PROFILE_PRIORS[item.musical_class]:
            raw[profile] += value * weight * (1.0 - cap)
        if item.musical_class in musical_classification.selected_classes:
            class_evidence.append(f"{item.musical_class.value}={value:.6f}")

    mode = mode_decision.selected_mode
    if mode is not None:
        for profile, weight in _MODE_PRIORS[mode]:
            raw[profile] += cap * weight

    total = sum(raw.values())
    normalized = {profile: raw[profile] / total for profile in OptimizationProfile}
    scores = tuple(
        ProfileScore(
            profile=profile,
            raw_score=raw[profile],
            score=normalized[profile],
            explanation=(
                "Score combines the complete musical-class vector with a conversion-mode "
                f"prior capped at {cap:.3f}."
            ),
        )
        for profile in OptimizationProfile
    )
    automatic = max(scores, key=lambda item: (item.score, -list(OptimizationProfile).index(item.profile))).profile
    override = None if requested_override is None else OptimizationProfile(requested_override)
    selected = automatic if override is None else override
    warnings: list[str] = []
    if override is not None and selected is not automatic:
        warnings.append(
            f"Profile override selects {selected.value} instead of automatic {automatic.value}."
        )
    if selected is OptimizationProfile.EXPERIMENTAL:
        warnings.append(
            "Experimental may preserve named controlled defects but never unsafe numeric output."
        )
    confidence, ambiguity = _confidence(scores)
    reason = (
        f"Automatic profile {selected.value} selected from the full class vector and capped mode prior."
        if requested_override is None
        else f"User override selected profile {selected.value}; automatic evidence remains serialized."
    )
    evidence = tuple(class_evidence) + (
        f"conversion_mode={None if mode is None else mode.value}",
        f"mode_prior_cap={cap:.6f}",
        f"automatic_profile={automatic.value}",
    )
    return ProfileSelection(
        schema_version=1,
        musical_classification_sha256=musical_classification.analysis_sha256,
        mode_decision_sha256=mode_decision.analysis_sha256,
        selected_profile=selected,
        requested_override=override,
        scores=scores,
        confidence=confidence,
        ambiguity=ambiguity,
        definition=profile_definition(selected),
        warnings=tuple(warnings),
        evidence=evidence,
        reason=reason,
    )
