from __future__ import annotations

import math

from ..analysis.formants import FormantAnalysis
from ..analysis.signal import SignalExtensionAnalysis
from ..perceptual.models import PerceptualFeatureVector
from .models import (
    BehaviorClass,
    BehaviorClassification,
    MusicalClass,
    MusicalClassScore,
    MusicalClassification,
)
from .explanations import confidence_from_ranked_scores


def _clip01(value: float) -> float:
    checked = float(value)
    if not math.isfinite(checked):
        return 0.0
    return float(min(1.0, max(0.0, checked)))


def _validate_links(
    behavior: BehaviorClassification,
    perceptual: PerceptualFeatureVector,
    formants: FormantAnalysis,
    extension: SignalExtensionAnalysis,
) -> None:
    identities = (
        (behavior.sample_rate, behavior.sample_count, behavior.sample_sha256),
        (perceptual.sample_rate, perceptual.sample_count, perceptual.sample_sha256),
        (formants.sample_rate, formants.sample_count, formants.sample_sha256),
        (extension.sample_rate, extension.sample_count, extension.sample_sha256),
    )
    if len({item[0] for item in identities}) != 1:
        raise ValueError("musical classification inputs have inconsistent sample rates")
    if len({item[1] for item in identities}) != 1:
        raise ValueError("musical classification inputs have inconsistent sample counts")
    if len({item[2] for item in identities}) != 1:
        raise ValueError("musical classification inputs have inconsistent sample hashes")
    if behavior.signal_extension_analysis_sha256 != extension.analysis_sha256:
        raise ValueError("behavior classification does not link to signal extension")
    if perceptual.signal_extension_analysis_sha256 != extension.analysis_sha256:
        raise ValueError("perceptual features do not link to signal extension")
    if perceptual.formant_analysis_sha256 != formants.analysis_sha256:
        raise ValueError("perceptual features do not link to formant analysis")


def _moderate(value: float, target: float = 0.5) -> float:
    return _clip01(1.0 - abs(float(value) - target) / max(target, 1.0 - target))


_EXPLANATIONS: dict[MusicalClass, str] = {
    MusicalClass.SUB: "Low-frequency power and fundamental presence dominate with limited brightness.",
    MusicalClass.BASS: "Low-band power, tonal center, and density support a general bass label.",
    MusicalClass.REESE: "Close fundamentals, motion, density, and low-frequency weight support a Reese label.",
    MusicalClass.FM_BASS: "Rapid frequency modulation, hardness, and low-frequency weight support FM Bass.",
    MusicalClass.DIRTY_BASS: "Saturation, hardness, noise, and low-frequency weight support Dirty Bass.",
    MusicalClass.HOOVER: "Detuned density, broad brightness, and motion support a Hoover-like label.",
    MusicalClass.ACID: "Bright hard tonal motion and saturation support an Acid-like label.",
    MusicalClass.LEAD: "A clear tonal fundamental with focused brightness supports a Lead label.",
    MusicalClass.PAD: "Sustained density with limited hardness and gradual motion supports a Pad label.",
    MusicalClass.DRONE: "Slow movement, sustained density, and stable low-frequency content support a Drone label.",
    MusicalClass.ORGAN: "Stable harmonic density and a strong tonal center support an Organ label.",
    MusicalClass.PWM: "Periodic tonal motion with changing spectral density supports a PWM label.",
    MusicalClass.SUPERSAW: "Close fundamentals, brightness, density, and motion support a Supersaw label.",
    MusicalClass.WAVETABLE: "Structured spectral motion and tonal density support a Wavetable label.",
    MusicalClass.BELL: "Bright tonal transients with low saturation support a Bell label.",
    MusicalClass.FM_BELL: "Bright transient energy plus rapid FM and hardness support FM Bell.",
    MusicalClass.PLUCK: "A strong transient with a tonal fundamental supports a Pluck label.",
    MusicalClass.VOCAL: "Broad formant structure and a tonal center support a Vocal label.",
    MusicalClass.CHOIR: "Formant structure, harmonic density, and close voices support a Choir label.",
    MusicalClass.TEXTURE: "Dense noisy spectral motion supports a Texture label.",
    MusicalClass.DIGITAL_NOISE: "Bright hard noisy energy supports a Digital Noise label.",
    MusicalClass.NOISE: "Noisiness and non-periodic behavior dominate the evidence.",
    MusicalClass.PIANO: "A tonal transient, clear fundamental, and broad brightness support Piano.",
    MusicalClass.GUITAR: "A tonal transient with moderate hardness and spectral density supports Guitar.",
    MusicalClass.PERCUSSION: "Transient dominance, hardness, and noise support a Percussion label.",
    MusicalClass.FX: "Strong movement, transient change, and spectral ambiguity support an FX label.",
    MusicalClass.HYBRID: "Several balanced source families remain materially present without one dominant label.",
}


def classify_musical_source(
    behavior_classification: BehaviorClassification,
    perceptual_features: PerceptualFeatureVector,
    formant_analysis: FormantAnalysis,
    signal_extension_analysis: SignalExtensionAnalysis,
    *,
    score_threshold: float = 0.58,
    maximum_labels: int = 5,
) -> MusicalClassification:
    """Return the canonical 27-label multi-label classification with explanations."""

    _validate_links(
        behavior_classification,
        perceptual_features,
        formant_analysis,
        signal_extension_analysis,
    )
    threshold = float(score_threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("score_threshold must be between 0 and 1")
    if int(maximum_labels) <= 0 or int(maximum_labels) > len(MusicalClass):
        raise ValueError("maximum_labels is outside the musical-class range")

    feature = perceptual_features
    extension = signal_extension_analysis
    behavior_scores = behavior_classification.score_map

    def behavior(kind: BehaviorClass) -> float:
        return _clip01(behavior_scores[kind.value])

    periodic = behavior(BehaviorClass.PERIODIC)
    quasi = behavior(BehaviorClass.QUASI_PERIODIC)
    evolving = behavior(BehaviorClass.EVOLVING)
    pitch_variable = behavior(BehaviorClass.PITCH_VARIABLE)
    transient = behavior(BehaviorClass.TRANSIENT)
    noisy = behavior(BehaviorClass.NOISY)
    non_periodic = behavior(BehaviorClass.NON_PERIODIC)
    hybrid_behavior = behavior(BehaviorClass.HYBRID)
    fm = extension.frequency_modulation_analysis.rapid_fm_score
    close_pair = (
        extension.beating_analysis.confidence
        if extension.beating_analysis.close_fundamentals_detected
        else 0.0
    )
    formant = formant_analysis.aggregate_confidence
    low = feature.low_frequency_power
    fundamental = feature.fundamental_presence
    brightness = feature.brightness
    hardness = feature.hardness
    saturation = feature.saturation
    density = feature.density
    motion = feature.motion
    tonal = feature.tonalness
    noise = feature.noisiness

    raw: dict[MusicalClass, float] = {
        MusicalClass.SUB: 0.48 * low + 0.32 * fundamental + 0.20 * (1.0 - brightness),
        MusicalClass.BASS: 0.38 * low + 0.25 * fundamental + 0.22 * tonal + 0.15 * density,
        MusicalClass.REESE: 0.27 * low + 0.27 * close_pair + 0.18 * motion + 0.18 * density + 0.10 * saturation,
        MusicalClass.FM_BASS: 0.22 * low + 0.32 * fm + 0.20 * hardness + 0.14 * density + 0.12 * tonal,
        MusicalClass.DIRTY_BASS: 0.22 * low + 0.30 * saturation + 0.22 * hardness + 0.16 * noise + 0.10 * density,
        MusicalClass.HOOVER: 0.15 * low + 0.22 * close_pair + 0.20 * motion + 0.17 * brightness + 0.16 * density + 0.10 * saturation,
        MusicalClass.ACID: 0.21 * tonal + 0.24 * brightness + 0.20 * motion + 0.20 * hardness + 0.15 * saturation,
        MusicalClass.LEAD: 0.30 * tonal + 0.23 * fundamental + 0.20 * brightness + 0.15 * periodic + 0.12 * (1.0 - low),
        MusicalClass.PAD: 0.22 * tonal + 0.23 * density + 0.22 * (1.0 - transient) + 0.18 * (1.0 - hardness) + 0.15 * evolving,
        MusicalClass.DRONE: 0.30 * (1.0 - motion) + 0.18 * low + 0.18 * density + 0.17 * tonal + 0.17 * (1.0 - transient),
        MusicalClass.ORGAN: 0.34 * tonal + 0.20 * fundamental + 0.22 * (1.0 - motion) + 0.14 * density + 0.10 * periodic,
        MusicalClass.PWM: 0.24 * motion + 0.25 * tonal + 0.18 * periodic + 0.17 * density + 0.16 * hardness,
        MusicalClass.SUPERSAW: 0.26 * close_pair + 0.21 * brightness + 0.23 * density + 0.15 * motion + 0.15 * quasi,
        MusicalClass.WAVETABLE: 0.34 * motion + 0.20 * tonal + 0.20 * density + 0.14 * evolving + 0.12 * hybrid_behavior,
        MusicalClass.BELL: 0.25 * tonal + 0.24 * brightness + 0.20 * transient + 0.16 * hardness + 0.15 * (1.0 - saturation),
        MusicalClass.FM_BELL: 0.30 * fm + 0.24 * brightness + 0.20 * hardness + 0.16 * transient + 0.10 * tonal,
        MusicalClass.PLUCK: 0.34 * transient + 0.25 * tonal + 0.16 * fundamental + 0.15 * brightness + 0.10 * (1.0 - motion),
        MusicalClass.VOCAL: 0.50 * formant + 0.18 * tonal + 0.12 * fundamental + 0.12 * motion + 0.08 * density,
        MusicalClass.CHOIR: 0.25 * formant + 0.24 * density + 0.20 * tonal + 0.16 * close_pair + 0.15 * motion,
        MusicalClass.TEXTURE: 0.26 * noise + 0.29 * density + 0.25 * motion + 0.20 * hybrid_behavior,
        MusicalClass.DIGITAL_NOISE: 0.34 * noise + 0.24 * hardness + 0.20 * brightness + 0.12 * transient + 0.10 * density,
        MusicalClass.NOISE: 0.52 * noise + 0.27 * non_periodic + 0.21 * noisy,
        MusicalClass.PIANO: 0.23 * transient + 0.25 * tonal + 0.20 * fundamental + 0.15 * brightness + 0.10 * density + 0.07 * (1.0 - saturation),
        MusicalClass.GUITAR: 0.23 * transient + 0.24 * tonal + 0.17 * fundamental + 0.17 * hardness + 0.12 * density + 0.07 * motion,
        MusicalClass.PERCUSSION: 0.46 * transient + 0.20 * noise + 0.18 * hardness + 0.16 * density,
        MusicalClass.FX: 0.30 * motion + 0.20 * noise + 0.20 * transient + 0.15 * density + 0.15 * hybrid_behavior,
        MusicalClass.HYBRID: 0.40 * hybrid_behavior + 0.20 * _moderate(tonal) + 0.15 * _moderate(noise) + 0.15 * _moderate(motion) + 0.10 * density,
    }
    raw = {key: _clip01(value) for key, value in raw.items()}
    ranked = sorted(raw, key=lambda item: (-raw[item], tuple(MusicalClass).index(item)))
    selected_ranked = [item for item in ranked if raw[item] >= threshold][
        : int(maximum_labels)
    ]
    if not selected_ranked:
        selected_ranked = [ranked[0]]
    selected_set = set(selected_ranked)
    score_items = tuple(
        MusicalClassScore(
            musical_class=musical_class,
            score=raw[musical_class],
            selected=musical_class in selected_set,
            explanation=_EXPLANATIONS[musical_class],
        )
        for musical_class in MusicalClass
    )
    selected_classes = tuple(
        musical_class for musical_class in MusicalClass if musical_class in selected_set
    )
    confidence, ambiguity = confidence_from_ranked_scores(tuple(raw.values()))
    evidence = (
        f"behavior={behavior_classification.behavior.value}",
        f"low_frequency_power={low:.6f}",
        f"fundamental_presence={fundamental:.6f}",
        f"brightness={brightness:.6f}",
        f"hardness={hardness:.6f}",
        f"saturation={saturation:.6f}",
        f"density={density:.6f}",
        f"motion={motion:.6f}",
        f"tonalness={tonal:.6f}",
        f"noisiness={noise:.6f}",
        f"formant_confidence={formant:.6f}",
        f"rapid_fm={fm:.6f}",
        f"close_fundamentals={close_pair:.6f}",
    )
    return MusicalClassification(
        schema_version=1,
        sample_rate=behavior_classification.sample_rate,
        sample_count=behavior_classification.sample_count,
        sample_sha256=behavior_classification.sample_sha256,
        behavior_classification_sha256=behavior_classification.analysis_sha256,
        perceptual_feature_sha256=perceptual_features.analysis_sha256,
        formant_analysis_sha256=formant_analysis.analysis_sha256,
        score_threshold=threshold,
        maximum_labels=int(maximum_labels),
        scores=score_items,
        selected_classes=selected_classes,
        confidence=confidence,
        ambiguity=ambiguity,
        evidence=evidence,
        reason=(
            "The canonical 27-label taxonomy is evaluated as a multi-label heuristic; "
            "classification guides priorities but does not independently select a conversion mode."
        ),
    )
