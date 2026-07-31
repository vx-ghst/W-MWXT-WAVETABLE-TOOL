from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any


class SourceClass(str, Enum):
    SILENT = "silent"
    STABLE_TONAL = "stable_tonal"
    EVOLVING_TONAL = "evolving_tonal"
    NOISY_TEXTURE = "noisy_texture"
    TRANSIENT_RICH = "transient_rich"
    MIXED_COMPLEX = "mixed_complex"


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


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _optional_ratio(value: float | None, default: float = 0.0) -> float:
    if value is None:
        return _clip01(default)
    checked = float(value)
    if not math.isfinite(checked):
        return _clip01(default)
    return _clip01(checked)


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _geometric_mean(values: tuple[float, ...]) -> float:
    if not values:
        return 0.0
    product = 1.0
    for value in values:
        product *= _clip01(value)
    return float(product ** (1.0 / len(values)))


def _snr_noise_presence(snr_db: float | None) -> float:
    if snr_db is None:
        return 0.0
    checked = float(snr_db)
    if not math.isfinite(checked):
        return 0.0
    # 6 dB maps to 0.5, high SNR tends toward zero, low SNR toward one.
    exponent = max(-12.0, min(12.0, (checked - 6.0) / 12.0))
    return _clip01(1.0 / (1.0 + 10.0**exponent))


@dataclass(frozen=True, slots=True)
class ClassificationFeature:
    name: str
    value: float
    explanation: str

    def __post_init__(self) -> None:
        if not self.name or self.name.strip() != self.name:
            raise ValueError("feature name must be a non-empty normalized string")
        _ratio(self.value, name=f"feature {self.name}")
        if not self.explanation or self.explanation.strip() != self.explanation:
            raise ValueError("feature explanation must be a non-empty normalized string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class SourceClassScore:
    source_class: SourceClass
    raw_score: float
    score: float

    def __post_init__(self) -> None:
        raw = _finite(self.raw_score, name="raw_score")
        if raw < 0.0:
            raise ValueError("raw_score must not be negative")
        _ratio(self.score, name="score")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_class": self.source_class.value,
            "raw_score": self.raw_score,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class SourceClassification:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    signal_analysis_sha256: str
    spectral_analysis_sha256: str
    harmonic_perceptual_analysis_sha256: str
    source_class: SourceClass
    confidence: float
    ambiguity: float
    class_scores: tuple[SourceClassScore, ...]
    features: tuple[ClassificationFeature, ...]
    evidence: tuple[str, ...]
    classification_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported source-classification schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "signal_analysis_sha256",
            "spectral_analysis_sha256",
            "harmonic_perceptual_analysis_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        _ratio(self.confidence, name="confidence")
        _ratio(self.ambiguity, name="ambiguity")
        if not math.isclose(self.confidence + self.ambiguity, 1.0, abs_tol=1e-12):
            raise ValueError("confidence and ambiguity must sum to one")
        if tuple(score.source_class for score in self.class_scores) != tuple(SourceClass):
            raise ValueError("class_scores must contain every source class in canonical order")
        score_sum = sum(score.score for score in self.class_scores)
        if not math.isclose(score_sum, 1.0, abs_tol=1e-12):
            raise ValueError("normalized class scores must sum to one")
        selected = max(self.class_scores, key=lambda item: item.score)
        if selected.source_class is not self.source_class:
            raise ValueError("source_class must match the highest normalized score")
        feature_names = tuple(feature.name for feature in self.features)
        if len(set(feature_names)) != len(feature_names):
            raise ValueError("classification feature names must be unique")
        if not self.features:
            raise ValueError("classification features must not be empty")
        if not self.evidence or any(not item for item in self.evidence):
            raise ValueError("evidence must contain non-empty entries")
        if not self.classification_reason or self.classification_reason.strip() != self.classification_reason:
            raise ValueError("classification_reason must be a non-empty normalized string")

    @property
    def class_score_map(self) -> dict[str, float]:
        return {item.source_class.value: item.score for item in self.class_scores}

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "signal_analysis_sha256": self.signal_analysis_sha256,
            "spectral_analysis_sha256": self.spectral_analysis_sha256,
            "harmonic_perceptual_analysis_sha256": self.harmonic_perceptual_analysis_sha256,
            "source_class": self.source_class.value,
            "confidence": self.confidence,
            "ambiguity": self.ambiguity,
            "class_scores": [item.to_dict() for item in self.class_scores],
            "features": [item.to_dict() for item in self.features],
            "evidence": list(self.evidence),
            "classification_reason": self.classification_reason,
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
        result["class_score_map"] = self.class_score_map
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _validate_analysis_links(
    signal_analysis: Any,
    spectral_analysis: Any,
    harmonic_perceptual_analysis: Any,
) -> None:
    identities = (
        (signal_analysis.sample_rate, signal_analysis.sample_count, signal_analysis.sample_sha256),
        (spectral_analysis.sample_rate, spectral_analysis.sample_count, spectral_analysis.sample_sha256),
        (
            harmonic_perceptual_analysis.sample_rate,
            harmonic_perceptual_analysis.sample_count,
            harmonic_perceptual_analysis.sample_sha256,
        ),
    )
    if len({identity[0] for identity in identities}) != 1:
        raise ValueError("classification analyses have inconsistent sample rates")
    if len({identity[1] for identity in identities}) != 1:
        raise ValueError("classification analyses have inconsistent sample counts")
    if len({identity[2] for identity in identities}) != 1:
        raise ValueError("classification analyses have inconsistent sample hashes")
    if harmonic_perceptual_analysis.spectral_analysis_sha256 != spectral_analysis.analysis_sha256:
        raise ValueError("harmonic/perceptual analysis does not link to the supplied spectral analysis")
    pitch_frequency = signal_analysis.pitch_periodicity_analysis.frequency_hz
    harmonic_frequency = harmonic_perceptual_analysis.fundamental_frequency_hz
    if pitch_frequency is None or harmonic_frequency is None:
        if pitch_frequency is not harmonic_frequency:
            raise ValueError("harmonic fundamental availability is inconsistent with pitch analysis")
    elif not math.isclose(float(pitch_frequency), float(harmonic_frequency), rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("harmonic fundamental does not match the supplied pitch analysis")


def _classification_reason(source_class: SourceClass, features: dict[str, float]) -> str:
    if source_class is SourceClass.SILENT:
        return "The source is silent or has no active analysis frame."
    if source_class is SourceClass.STABLE_TONAL:
        return (
            "Strong periodic and harmonic evidence combines with stable pitch, phase, "
            "amplitude, and spectrum."
        )
    if source_class is SourceClass.EVOLVING_TONAL:
        return (
            "The source remains materially tonal while pitch, phase, or spectral content "
            "changes over time."
        )
    if source_class is SourceClass.NOISY_TEXTURE:
        return (
            "Residual energy, spectral noisiness, weak periodicity, or low concentration "
            "dominate the evidence."
        )
    if source_class is SourceClass.TRANSIENT_RICH:
        return (
            "Transient density, change points, onset strength, or spectral flux dominate "
            "the evidence."
        )
    return (
        "No single tonal, noisy, or transient family dominates and the measured spectral "
        "complexity remains material."
    )


def classify_source(
    signal_analysis: Any,
    spectral_analysis: Any,
    harmonic_perceptual_analysis: Any,
) -> SourceClassification:
    """Classify accepted CODE V4/V5 analyses without changing their measurements."""

    _validate_analysis_links(
        signal_analysis,
        spectral_analysis,
        harmonic_perceptual_analysis,
    )

    time_domain = signal_analysis.time_domain_analysis
    pitch = signal_analysis.pitch_periodicity_analysis
    phase = signal_analysis.phase_motion_analysis
    noise = signal_analysis.noise_analysis
    transient = signal_analysis.transient_change_analysis
    harmonic = harmonic_perceptual_analysis

    amplitude_active = _optional_ratio(time_domain.envelope.active_frame_ratio)
    spectral_active = _optional_ratio(spectral_analysis.active_frame_ratio)
    pitch_active = _optional_ratio(pitch.active_frame_ratio)
    active_presence = (amplitude_active + spectral_active + pitch_active) / 3.0

    periodicity = _clip01(
        _optional_ratio(pitch.periodicity_score)
        * math.sqrt(_optional_ratio(pitch.voiced_active_ratio))
    )
    pitch_stability = _optional_ratio(pitch.pitch_stability)
    phase_stability = _optional_ratio(phase.phase_stability)
    amplitude_stability = _optional_ratio(time_domain.envelope.amplitude_stability)
    spectral_stationarity = _optional_ratio(spectral_analysis.spectral_stationarity)
    noise_stationarity = _optional_ratio(noise.noise_stationarity)

    harmonicity = _optional_ratio(harmonic.harmonic_energy_ratio)
    residual = _optional_ratio(harmonic.residual_energy_ratio)
    concentration = _optional_ratio(harmonic.spectral_concentration)
    noisiness = _optional_ratio(harmonic.spectral_noisiness)
    spectral_entropy = _optional_ratio(spectral_analysis.entropy)
    bark_entropy = _optional_ratio(harmonic.bark_entropy)

    snr_noise = _snr_noise_presence(noise.snr_db)
    noise_presence = _clip01(
        0.30 * residual
        + 0.25 * noisiness
        + 0.25 * snr_noise
        + 0.10 * (1.0 - periodicity)
        + 0.10 * (1.0 - concentration)
    )

    median_flux = max(0.0, float(spectral_analysis.median_spectral_flux))
    maximum_flux = max(0.0, float(spectral_analysis.maximum_spectral_flux))
    flux_activity = _clip01(
        0.6 * min(1.0, median_flux / 0.20)
        + 0.4 * min(1.0, maximum_flux / 0.50)
    )
    transient_density = max(0.0, float(transient.transient_density_per_second))
    change_ratio = _optional_ratio(transient.change_ratio)
    maximum_onset = max(0.0, float(transient.maximum_onset_strength))
    transient_activity = _clip01(
        0.40 * min(1.0, transient_density / 4.0)
        + 0.30 * min(1.0, change_ratio / 0.10)
        + 0.20 * flux_activity
        + 0.10 * min(1.0, maximum_onset / 8.0)
    )

    phase_instability = max(1.0 - phase_stability, _optional_ratio(phase.discontinuity_ratio))
    spectral_change = max(1.0 - spectral_stationarity, flux_activity)
    pitch_change = 1.0 - pitch_stability
    temporal_instability = _clip01(
        0.40 * pitch_change + 0.30 * phase_instability + 0.30 * spectral_change
    )

    tonal_presence = _geometric_mean((periodicity, harmonicity, concentration))
    global_stability = _clip01(
        0.30 * pitch_stability
        + 0.25 * phase_stability
        + 0.25 * spectral_stationarity
        + 0.20 * amplitude_stability
    )
    complexity = _clip01(
        0.35 * spectral_entropy
        + 0.25 * bark_entropy
        + 0.20 * (1.0 - concentration)
        + 0.10 * spectral_change
        + 0.10 * (1.0 - noise_stationarity)
    )

    features = {
        "active_presence": _clip01(active_presence),
        "periodicity": periodicity,
        "harmonicity": harmonicity,
        "spectral_concentration": concentration,
        "tonal_presence": tonal_presence,
        "global_stability": global_stability,
        "temporal_instability": temporal_instability,
        "noise_presence": noise_presence,
        "transient_activity": transient_activity,
        "spectral_complexity": complexity,
    }

    is_silent = bool(time_domain.levels.is_silent) or features["active_presence"] <= 1e-12
    if is_silent:
        raw_scores = {
            SourceClass.SILENT: 1.0,
            SourceClass.STABLE_TONAL: 0.0,
            SourceClass.EVOLVING_TONAL: 0.0,
            SourceClass.NOISY_TEXTURE: 0.0,
            SourceClass.TRANSIENT_RICH: 0.0,
            SourceClass.MIXED_COMPLEX: 0.0,
        }
    else:
        balance_inputs = (tonal_presence, noise_presence, transient_activity)
        balance = 1.0 - (max(balance_inputs) - min(balance_inputs))
        raw_scores = {
            SourceClass.SILENT: max(0.0, (1.0 - active_presence) ** 4 * 0.05),
            SourceClass.STABLE_TONAL: tonal_presence
            * global_stability
            * (1.0 - 0.35 * transient_activity),
            SourceClass.EVOLVING_TONAL: tonal_presence
            * temporal_instability
            * (0.55 + 0.45 * spectral_change),
            SourceClass.NOISY_TEXTURE: noise_presence
            * (0.70 + 0.30 * (1.0 - transient_activity)),
            SourceClass.TRANSIENT_RICH: transient_activity
            * (0.65 + 0.35 * (1.0 - tonal_presence)),
            SourceClass.MIXED_COMPLEX: complexity
            * (0.55 + 0.45 * _clip01(balance)),
        }

    total = sum(raw_scores.values())
    if total <= 0.0:
        raw_scores[SourceClass.MIXED_COMPLEX] = 1.0
        total = 1.0
    normalized = {source_class: raw_scores[source_class] / total for source_class in SourceClass}
    ordered_scores = tuple(
        SourceClassScore(
            source_class=source_class,
            raw_score=float(raw_scores[source_class]),
            score=float(normalized[source_class]),
        )
        for source_class in SourceClass
    )
    ranked = sorted(ordered_scores, key=lambda item: (-item.score, list(SourceClass).index(item.source_class)))
    winner = ranked[0]
    runner_up = ranked[1]
    margin = winner.score - runner_up.score
    confidence = _clip01(winner.score + 0.5 * margin)
    ambiguity = float(1.0 - confidence)

    feature_models = tuple(
        ClassificationFeature(name=name, value=value, explanation=explanation)
        for name, value, explanation in (
            ("active_presence", features["active_presence"], "Mean active-frame evidence across amplitude, spectrum, and pitch."),
            ("periodicity", periodicity, "Pitch-periodicity confidence weighted by voiced active coverage."),
            ("harmonicity", harmonicity, "Share of spectral energy assigned to detected harmonics."),
            ("spectral_concentration", concentration, "One minus normalized spectral entropy from the perceptual analysis."),
            ("tonal_presence", tonal_presence, "Geometric agreement between periodicity, harmonicity, and concentration."),
            ("global_stability", global_stability, "Weighted pitch, phase, spectral, and amplitude stability."),
            ("temporal_instability", temporal_instability, "Weighted pitch, phase, and spectral change evidence."),
            ("noise_presence", noise_presence, "Residual, flatness, SNR, periodicity, and concentration evidence."),
            ("transient_activity", transient_activity, "Transient density, change ratio, onset, and spectral-flux evidence."),
            ("spectral_complexity", complexity, "Spectral/Bark entropy, spread, change, and noise variability evidence."),
        )
    )
    evidence = (
        f"tonal_presence={tonal_presence:.6f}",
        f"global_stability={global_stability:.6f}",
        f"temporal_instability={temporal_instability:.6f}",
        f"noise_presence={noise_presence:.6f}",
        f"transient_activity={transient_activity:.6f}",
        f"spectral_complexity={complexity:.6f}",
        f"winner_margin={margin:.6f}",
    )

    return SourceClassification(
        schema_version=1,
        sample_rate=int(signal_analysis.sample_rate),
        sample_count=int(signal_analysis.sample_count),
        sample_sha256=signal_analysis.sample_sha256,
        signal_analysis_sha256=signal_analysis.analysis_sha256,
        spectral_analysis_sha256=spectral_analysis.analysis_sha256,
        harmonic_perceptual_analysis_sha256=(harmonic_perceptual_analysis.analysis_sha256),
        source_class=winner.source_class,
        confidence=confidence,
        ambiguity=ambiguity,
        class_scores=ordered_scores,
        features=feature_models,
        evidence=evidence,
        classification_reason=_classification_reason(winner.source_class, features),
    )
