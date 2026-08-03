from __future__ import annotations

import math
from typing import Any

from ..analysis.formants import FormantAnalysis
from ..analysis.harmonic_perceptual import HarmonicPerceptualAnalysis
from ..analysis.signal import SignalAnalysis, SignalExtensionAnalysis
from ..analysis.spectral import SpectralAnalysis
from ..analysis.spectral_evolution import SpectralEvolutionAnalysis
from .models import PerceptualFeatureVector


def _clip01(value: float) -> float:
    checked = float(value)
    if not math.isfinite(checked):
        return 0.0
    return float(min(1.0, max(0.0, checked)))


def _optional(value: float | None, default: float = 0.0) -> float:
    return _clip01(default if value is None else value)


def _snr_noisiness(snr_db: float | None) -> float:
    if snr_db is None or not math.isfinite(float(snr_db)):
        return 0.0
    exponent = max(-12.0, min(12.0, (float(snr_db) - 6.0) / 12.0))
    return _clip01(1.0 / (1.0 + 10.0**exponent))


def _validate_links(
    signal: SignalAnalysis,
    extension: SignalExtensionAnalysis,
    spectral: SpectralAnalysis,
    harmonic: HarmonicPerceptualAnalysis,
    evolution: SpectralEvolutionAnalysis,
    formants: FormantAnalysis,
) -> None:
    identities = (
        (signal.sample_rate, signal.sample_count, signal.sample_sha256),
        (extension.sample_rate, extension.sample_count, extension.sample_sha256),
        (spectral.sample_rate, spectral.sample_count, spectral.sample_sha256),
        (harmonic.sample_rate, harmonic.sample_count, harmonic.sample_sha256),
        (evolution.sample_rate, evolution.sample_count, evolution.sample_sha256),
        (formants.sample_rate, formants.sample_count, formants.sample_sha256),
    )
    if len({identity[0] for identity in identities}) != 1:
        raise ValueError("perceptual inputs have inconsistent sample rates")
    if len({identity[1] for identity in identities}) != 1:
        raise ValueError("perceptual inputs have inconsistent sample counts")
    if len({identity[2] for identity in identities}) != 1:
        raise ValueError("perceptual inputs have inconsistent sample hashes")
    if extension.signal_analysis_sha256 != signal.analysis_sha256:
        raise ValueError("signal extension does not link to signal analysis")
    if harmonic.spectral_analysis_sha256 != spectral.analysis_sha256:
        raise ValueError("harmonic analysis does not link to spectral analysis")
    if evolution.spectral_analysis_sha256 != spectral.analysis_sha256:
        raise ValueError("spectral evolution does not link to spectral analysis")
    if evolution.harmonic_perceptual_analysis_sha256 != harmonic.analysis_sha256:
        raise ValueError("spectral evolution does not link to harmonic analysis")
    if formants.spectral_analysis_sha256 != spectral.analysis_sha256:
        raise ValueError("formant analysis does not link to spectral analysis")


def analyze_perceptual_features(
    signal_analysis: SignalAnalysis,
    signal_extension_analysis: SignalExtensionAnalysis,
    spectral_analysis: SpectralAnalysis,
    harmonic_perceptual_analysis: HarmonicPerceptualAnalysis,
    spectral_evolution_analysis: SpectralEvolutionAnalysis,
    formant_analysis: FormantAnalysis,
) -> PerceptualFeatureVector:
    """Derive explainable bounded psychoacoustic proxies from accepted measurements."""

    _validate_links(
        signal_analysis,
        signal_extension_analysis,
        spectral_analysis,
        harmonic_perceptual_analysis,
        spectral_evolution_analysis,
        formant_analysis,
    )

    pitch = signal_analysis.pitch_periodicity_analysis
    phase = signal_analysis.phase_motion_analysis
    noise = signal_analysis.noise_analysis
    transient = signal_analysis.transient_change_analysis
    envelope = signal_analysis.time_domain_analysis.envelope
    saturation = signal_extension_analysis.saturation_analysis
    complexity = signal_extension_analysis.complexity_analysis
    fm = signal_extension_analysis.frequency_modulation_analysis
    beating = signal_extension_analysis.beating_analysis
    harmonic = harmonic_perceptual_analysis
    evolution = spectral_evolution_analysis

    low_frequency_power = _clip01(
        0.55 * evolution.low_ratio
        + 0.30 * evolution.low_mid_ratio
        + 0.15 * _optional(harmonic.fundamental_power_ratio)
    )
    fundamental_presence = _clip01(
        0.40 * _optional(harmonic.fundamental_power_ratio)
        + 0.25 * _optional(pitch.periodicity_score)
        + 0.20 * _optional(pitch.voiced_active_ratio)
        + 0.15 * _optional(harmonic.harmonic_energy_ratio)
    )
    brightness = _clip01(
        0.55 * _optional(harmonic.perceptual_brightness)
        + 0.25 * evolution.high_ratio
        + 0.20 * evolution.mid_ratio
    )
    inharmonicity = _clip01(
        0.0
        if harmonic.inharmonicity_cents is None
        else float(harmonic.inharmonicity_cents) / 100.0
    )
    hardness = _clip01(
        0.30 * evolution.high_ratio
        + 0.20 * _optional(spectral_analysis.crest, 0.0) / 8.0
        + 0.25 * saturation.maximum_saturation_score
        + 0.15 * inharmonicity
        + 0.10 * _optional(harmonic.spectral_noisiness)
    )
    perceived_saturation = _clip01(
        0.55 * saturation.mean_saturation_score
        + 0.30 * saturation.maximum_saturation_score
        + 0.15 * saturation.saturated_frame_ratio
    )
    perceived_density = _clip01(
        0.30 * complexity.density_score
        + 0.25 * complexity.complexity_score
        + 0.20 * _optional(spectral_analysis.entropy)
        + 0.15 * evolution.mean_inharmonic_energy_ratio
        + 0.10 * evolution.mid_ratio
    )
    transient_motion = _clip01(
        0.55 * _optional(transient.change_ratio)
        + 0.25 * min(1.0, float(transient.transient_density_per_second) / 8.0)
        + 0.20 * min(1.0, float(transient.maximum_onset_strength) / 12.0)
    )
    pitch_motion = _clip01(
        0.55 * fm.rapid_fm_score + 0.45 * (1.0 - _optional(pitch.pitch_stability))
    )
    spectral_motion = _clip01(
        0.50 * evolution.useful_change_score
        + 0.25 * evolution.harmonic_evolution_score
        + 0.25 * (1.0 - evolution.mean_adjacent_correlation)
    )
    motion = _clip01(
        0.40 * spectral_motion
        + 0.30 * pitch_motion
        + 0.20 * transient_motion
        + 0.10 * saturation.saturation_variation
    )
    tonalness = _clip01(
        0.30 * _optional(pitch.periodicity_score)
        + 0.25 * _optional(harmonic.harmonic_energy_ratio)
        + 0.20 * _optional(harmonic.spectral_concentration)
        + 0.15 * _optional(pitch.pitch_stability)
        + 0.10 * _optional(phase.phase_stability)
    )
    noisiness = _clip01(
        0.30 * _optional(harmonic.spectral_noisiness)
        + 0.25 * _optional(harmonic.residual_energy_ratio)
        + 0.20 * _snr_noisiness(noise.snr_db)
        + 0.15 * evolution.mean_inharmonic_energy_ratio
        + 0.10 * (1.0 - _optional(noise.noise_stationarity))
    )

    formant_evidence = formant_analysis.aggregate_confidence
    close_pair = 1.0 if beating.close_fundamentals_detected else 0.0
    evidence = (
        f"low_bands={evolution.low_ratio + evolution.low_mid_ratio:.6f}",
        f"fundamental_power={_optional(harmonic.fundamental_power_ratio):.6f}",
        f"brightness_proxy={_optional(harmonic.perceptual_brightness):.6f}",
        f"saturation_mean={saturation.mean_saturation_score:.6f}",
        f"density_score={complexity.density_score:.6f}",
        f"spectral_change={evolution.useful_change_score:.6f}",
        f"rapid_fm={fm.rapid_fm_score:.6f}",
        f"formant_confidence={formant_evidence:.6f}",
        f"close_fundamentals={close_pair:.6f}",
        f"amplitude_stability={envelope.amplitude_stability:.6f}",
    )

    return PerceptualFeatureVector(
        schema_version=1,
        sample_rate=signal_analysis.sample_rate,
        sample_count=signal_analysis.sample_count,
        sample_sha256=signal_analysis.sample_sha256,
        signal_analysis_sha256=signal_analysis.analysis_sha256,
        signal_extension_analysis_sha256=signal_extension_analysis.analysis_sha256,
        spectral_analysis_sha256=spectral_analysis.analysis_sha256,
        harmonic_perceptual_analysis_sha256=harmonic_perceptual_analysis.analysis_sha256,
        spectral_evolution_analysis_sha256=spectral_evolution_analysis.analysis_sha256,
        formant_analysis_sha256=formant_analysis.analysis_sha256,
        low_frequency_power=low_frequency_power,
        fundamental_presence=fundamental_presence,
        brightness=brightness,
        hardness=hardness,
        saturation=perceived_saturation,
        density=perceived_density,
        motion=motion,
        tonalness=tonalness,
        noisiness=noisiness,
        evidence=evidence,
        reason=(
            "Perceptual proxies combine linked signal, spectral, harmonic, formant, and "
            "temporal measurements; they are deterministic engineering estimates, not "
            "hardware-calibrated loudness claims."
        ),
    )
