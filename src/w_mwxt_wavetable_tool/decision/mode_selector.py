from __future__ import annotations

import math

from ..analysis.signal import SignalAnalysis, SignalExtensionAnalysis
from ..analysis.spectral_evolution import SpectralEvolutionAnalysis
from ..perceptual.models import PerceptualFeatureVector
from .explanations import (
    confidence_from_ranked_scores,
    execution_path_for_mode,
    validate_mode_execution_paths,
)
from .models import (
    BehaviorClass,
    BehaviorClassification,
    ConversionMode,
    ModeDecision,
    ModeDecisionStatus,
    ModeScore,
    MusicalClass,
    MusicalClassification,
)


def _clip01(value: float) -> float:
    checked = float(value)
    if not math.isfinite(checked):
        return 0.0
    return float(min(1.0, max(0.0, checked)))


def _validate_links(
    signal: SignalAnalysis,
    extension: SignalExtensionAnalysis,
    behavior: BehaviorClassification,
    musical: MusicalClassification,
    perceptual: PerceptualFeatureVector,
    evolution: SpectralEvolutionAnalysis,
) -> None:
    identities = (
        (signal.sample_rate, signal.sample_count, signal.sample_sha256),
        (extension.sample_rate, extension.sample_count, extension.sample_sha256),
        (behavior.sample_rate, behavior.sample_count, behavior.sample_sha256),
        (musical.sample_rate, musical.sample_count, musical.sample_sha256),
        (perceptual.sample_rate, perceptual.sample_count, perceptual.sample_sha256),
        (evolution.sample_rate, evolution.sample_count, evolution.sample_sha256),
    )
    if len({item[0] for item in identities}) != 1:
        raise ValueError("mode-selection inputs have inconsistent sample rates")
    if len({item[1] for item in identities}) != 1:
        raise ValueError("mode-selection inputs have inconsistent sample counts")
    if len({item[2] for item in identities}) != 1:
        raise ValueError("mode-selection inputs have inconsistent sample hashes")
    if extension.signal_analysis_sha256 != signal.analysis_sha256:
        raise ValueError("signal extension does not link to signal analysis")
    if behavior.signal_analysis_sha256 != signal.analysis_sha256:
        raise ValueError("behavior classification does not link to signal analysis")
    if behavior.signal_extension_analysis_sha256 != extension.analysis_sha256:
        raise ValueError("behavior classification does not link to signal extension")
    if musical.behavior_classification_sha256 != behavior.analysis_sha256:
        raise ValueError("musical classification does not link to behavior classification")
    if musical.perceptual_feature_sha256 != perceptual.analysis_sha256:
        raise ValueError("musical classification does not link to perceptual features")
    if perceptual.signal_analysis_sha256 != signal.analysis_sha256:
        raise ValueError("perceptual features do not link to signal analysis")
    if perceptual.signal_extension_analysis_sha256 != extension.analysis_sha256:
        raise ValueError("perceptual features do not link to signal extension")
    if perceptual.spectral_evolution_analysis_sha256 != evolution.analysis_sha256:
        raise ValueError("perceptual features do not link to spectral evolution")


def _musical_priors(classification: MusicalClassification) -> dict[ConversionMode, float]:
    selected = set(classification.selected_classes)
    groups = {
        ConversionMode.STABLE_CYCLE: {
            MusicalClass.SUB,
            MusicalClass.BASS,
            MusicalClass.LEAD,
            MusicalClass.ORGAN,
            MusicalClass.PWM,
            MusicalClass.BELL,
            MusicalClass.PLUCK,
        },
        ConversionMode.EVOLVING_HARMONICS: {
            MusicalClass.REESE,
            MusicalClass.HOOVER,
            MusicalClass.ACID,
            MusicalClass.PAD,
            MusicalClass.DRONE,
            MusicalClass.SUPERSAW,
            MusicalClass.WAVETABLE,
            MusicalClass.CHOIR,
        },
        ConversionMode.DYNAMIC_PITCH: {
            MusicalClass.FM_BASS,
            MusicalClass.FM_BELL,
            MusicalClass.FX,
        },
        ConversionMode.SPECTRAL_RECONSTRUCTION: {
            MusicalClass.VOCAL,
            MusicalClass.TEXTURE,
            MusicalClass.DIGITAL_NOISE,
            MusicalClass.NOISE,
            MusicalClass.PIANO,
            MusicalClass.GUITAR,
            MusicalClass.PERCUSSION,
        },
        ConversionMode.HYBRID: {
            MusicalClass.DIRTY_BASS,
            MusicalClass.HYBRID,
        },
    }
    return {
        mode: min(
            0.08,
            0.04 * len(selected.intersection(labels)),
        )
        for mode, labels in groups.items()
    }


_EXPLANATIONS: dict[ConversionMode, str] = {
    ConversionMode.STABLE_CYCLE: (
        "Stable periodicity, tonal presence, and low motion support direct cycle extraction."
    ),
    ConversionMode.EVOLVING_HARMONICS: (
        "Tonal material changes spectrally over time and benefits from region-weighted states."
    ),
    ConversionMode.DYNAMIC_PITCH: (
        "Pitch movement or rapid frequency modulation requires explicit working-pitch handling."
    ),
    ConversionMode.SPECTRAL_RECONSTRUCTION: (
        "Weak periodicity, noise, transients, or formant-rich content favor spectral reconstruction."
    ),
    ConversionMode.HYBRID: (
        "Several materially different signal families require a combined executable path."
    ),
}


def select_conversion_mode(
    signal_analysis: SignalAnalysis,
    signal_extension_analysis: SignalExtensionAnalysis,
    behavior_classification: BehaviorClassification,
    musical_classification: MusicalClassification,
    perceptual_features: PerceptualFeatureVector,
    spectral_evolution_analysis: SpectralEvolutionAnalysis,
    *,
    mode_override: ConversionMode | str | None = None,
) -> ModeDecision:
    """Select one of five executable modes with explicit override and refusal states."""

    _validate_links(
        signal_analysis,
        signal_extension_analysis,
        behavior_classification,
        musical_classification,
        perceptual_features,
        spectral_evolution_analysis,
    )
    validate_mode_execution_paths()
    requested_override: ConversionMode | None = None
    if mode_override is not None:
        try:
            requested_override = ConversionMode(mode_override)
        except ValueError as exc:
            raise ValueError(f"Unknown conversion mode override: {mode_override!r}") from exc

    behavior_scores = behavior_classification.score_map

    def behavior(kind: BehaviorClass) -> float:
        return _clip01(behavior_scores[kind.value])

    pitch = signal_analysis.pitch_periodicity_analysis
    levels = signal_analysis.time_domain_analysis.levels
    envelope = signal_analysis.time_domain_analysis.envelope
    extension = signal_extension_analysis
    perceptual = perceptual_features
    evolution = spectral_evolution_analysis
    periodicity = _clip01(pitch.periodicity_score)
    pitch_stability = _clip01(pitch.pitch_stability)
    active_presence = _clip01(envelope.active_frame_ratio)
    rapid_fm = extension.frequency_modulation_analysis.rapid_fm_score
    priors = _musical_priors(musical_classification)

    raw: dict[ConversionMode, float] = {
        ConversionMode.STABLE_CYCLE: (
            0.30 * behavior(BehaviorClass.PERIODIC)
            + 0.22 * periodicity
            + 0.18 * pitch_stability
            + 0.15 * perceptual.tonalness
            + 0.10 * (1.0 - perceptual.motion)
            + 0.05 * (1.0 - perceptual.noisiness)
        ),
        ConversionMode.EVOLVING_HARMONICS: (
            0.28 * behavior(BehaviorClass.EVOLVING)
            + 0.20 * evolution.useful_change_score
            + 0.17 * perceptual.motion
            + 0.15 * perceptual.tonalness
            + 0.10 * evolution.harmonic_evolution_score
            + 0.10 * perceptual.density
        ),
        ConversionMode.DYNAMIC_PITCH: (
            0.30 * behavior(BehaviorClass.PITCH_VARIABLE)
            + 0.24 * rapid_fm
            + 0.20 * (1.0 - pitch_stability)
            + 0.13 * perceptual.motion
            + 0.13 * periodicity
        ),
        ConversionMode.SPECTRAL_RECONSTRUCTION: (
            0.20 * behavior(BehaviorClass.NON_PERIODIC)
            + 0.16 * behavior(BehaviorClass.NOISY)
            + 0.14 * behavior(BehaviorClass.TRANSIENT)
            + 0.18 * (1.0 - periodicity)
            + 0.14 * perceptual.noisiness
            + 0.10 * (1.0 - perceptual.tonalness)
            + 0.08 * perceptual.density
        ),
        ConversionMode.HYBRID: (
            0.34 * behavior(BehaviorClass.HYBRID)
            + 0.18 * perceptual.density
            + 0.16 * perceptual.motion
            + 0.14 * evolution.useful_change_score
            + 0.10 * behavior_classification.ambiguity
            + 0.08 * musical_classification.ambiguity
        ),
    }
    raw = {
        mode: max(1.0e-12, _clip01(value + priors[mode]))
        for mode, value in raw.items()
    }
    total = sum(raw.values())
    normalized = {mode: raw[mode] / total for mode in ConversionMode}
    score_items = tuple(
        ModeScore(
            mode=mode,
            raw_score=raw[mode],
            score=normalized[mode],
            explanation=_EXPLANATIONS[mode],
        )
        for mode in ConversionMode
    )
    confidence, ambiguity = confidence_from_ranked_scores(
        tuple(normalized[mode] for mode in ConversionMode)
    )
    automatic_mode = max(
        ConversionMode,
        key=lambda mode: (normalized[mode], -tuple(ConversionMode).index(mode)),
    )
    evidence = (
        f"active_presence={active_presence:.6f}",
        f"periodicity={periodicity:.6f}",
        f"pitch_stability={pitch_stability:.6f}",
        f"rapid_fm={rapid_fm:.6f}",
        f"tonalness={perceptual.tonalness:.6f}",
        f"noisiness={perceptual.noisiness:.6f}",
        f"motion={perceptual.motion:.6f}",
        f"spectral_change={evolution.useful_change_score:.6f}",
        "musical_class_prior_cap=0.080000",
    )

    if levels.is_silent or active_presence <= 0.01:
        return ModeDecision(
            schema_version=1,
            sample_rate=signal_analysis.sample_rate,
            sample_count=signal_analysis.sample_count,
            sample_sha256=signal_analysis.sample_sha256,
            behavior_classification_sha256=behavior_classification.analysis_sha256,
            musical_classification_sha256=musical_classification.analysis_sha256,
            perceptual_feature_sha256=perceptual_features.analysis_sha256,
            spectral_evolution_analysis_sha256=spectral_evolution_analysis.analysis_sha256,
            status=ModeDecisionStatus.REJECTED,
            selected_mode=None,
            requested_override=requested_override,
            scores=score_items,
            confidence=confidence,
            ambiguity=ambiguity,
            execution_path=None,
            warnings=("No conversion path may run without sufficient active signal.",),
            evidence=evidence,
            reason=(
                "Conversion mode selection was explicitly refused because the source is "
                "silent or contains insufficient active material."
            ),
        )

    warnings: list[str] = []
    if requested_override is None:
        selected_mode = automatic_mode
        status = ModeDecisionStatus.SELECTED
        reason = (
            f"Automatic selection chose {selected_mode.value} from linked behavioral, "
            "spectral, perceptual, and pitch evidence."
        )
    else:
        selected_mode = requested_override
        status = ModeDecisionStatus.OVERRIDDEN
        if selected_mode is not automatic_mode:
            warnings.append(
                f"Manual override replaced automatic mode {automatic_mode.value}."
            )
        if selected_mode is ConversionMode.STABLE_CYCLE and periodicity < 0.35:
            warnings.append(
                "Stable Cycle was forced despite weak periodicity; cycle discovery may refuse candidates."
            )
        if (
            selected_mode is ConversionMode.SPECTRAL_RECONSTRUCTION
            and perceptual.tonalness > 0.80
        ):
            warnings.append(
                "Spectral Reconstruction was forced despite strong tonal evidence."
            )
        reason = (
            f"Manual override selected {selected_mode.value}; the automatic scores remain "
            "serialized for comparison and audit."
        )

    return ModeDecision(
        schema_version=1,
        sample_rate=signal_analysis.sample_rate,
        sample_count=signal_analysis.sample_count,
        sample_sha256=signal_analysis.sample_sha256,
        behavior_classification_sha256=behavior_classification.analysis_sha256,
        musical_classification_sha256=musical_classification.analysis_sha256,
        perceptual_feature_sha256=perceptual_features.analysis_sha256,
        spectral_evolution_analysis_sha256=spectral_evolution_analysis.analysis_sha256,
        status=status,
        selected_mode=selected_mode,
        requested_override=requested_override,
        scores=score_items,
        confidence=confidence,
        ambiguity=ambiguity,
        execution_path=execution_path_for_mode(selected_mode),
        warnings=tuple(warnings),
        evidence=evidence,
        reason=reason,
    )
