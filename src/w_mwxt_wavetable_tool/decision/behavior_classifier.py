from __future__ import annotations

import math
from typing import Any

from .models import BehaviorClass, BehaviorClassification, BehaviorScore


def _clip01(value: float, *, name: str = "value") -> float:
    checked = float(value)
    if not math.isfinite(checked):
        raise ValueError(f"{name} must be finite")
    return float(min(1.0, max(0.0, checked)))


def _snr_noise_score(snr_db: float | None) -> float:
    if snr_db is None:
        return 0.0
    checked = float(snr_db)
    if not math.isfinite(checked):
        raise ValueError("snr_db must be finite when defined")
    exponent = max(-12.0, min(12.0, (checked - 6.0) / 12.0))
    return _clip01(1.0 / (1.0 + 10.0**exponent))


def _validate_links(signal_analysis: Any, extension_analysis: Any) -> None:
    if signal_analysis.sample_rate != extension_analysis.sample_rate:
        raise ValueError("behavior analyses have inconsistent sample rates")
    if signal_analysis.sample_count != extension_analysis.sample_count:
        raise ValueError("behavior analyses have inconsistent sample counts")
    if signal_analysis.sample_sha256 != extension_analysis.sample_sha256:
        raise ValueError("behavior analyses have inconsistent sample hashes")
    if extension_analysis.signal_analysis_sha256 != signal_analysis.analysis_sha256:
        raise ValueError("signal extension does not link to the supplied signal analysis")


def classify_behavior(
    signal_analysis: Any,
    signal_extension_analysis: Any,
) -> BehaviorClassification:
    _validate_links(signal_analysis, signal_extension_analysis)

    time_domain = signal_analysis.time_domain_analysis
    pitch = signal_analysis.pitch_periodicity_analysis
    phase = signal_analysis.phase_motion_analysis
    noise = signal_analysis.noise_analysis
    transient = signal_analysis.transient_change_analysis
    fm = signal_extension_analysis.frequency_modulation_analysis
    saturation = signal_extension_analysis.saturation_analysis
    complexity = signal_extension_analysis.complexity_analysis
    beating = signal_extension_analysis.beating_analysis

    active = _clip01(
        time_domain.envelope.active_frame_ratio, name="active_frame_ratio"
    )
    periodicity = _clip01(
        pitch.periodicity_score * pitch.voiced_active_ratio,
        name="periodicity",
    )
    pitch_stability = _clip01(pitch.pitch_stability, name="pitch_stability")
    quasi = _clip01(pitch.quasi_periodicity_score, name="quasi_periodicity")
    phase_stability = _clip01(phase.phase_stability, name="phase_stability")
    amplitude_stability = _clip01(
        time_domain.envelope.amplitude_stability,
        name="amplitude_stability",
    )
    fm_activity = _clip01(fm.rapid_fm_score, name="rapid_fm_score")
    pitch_variability = _clip01(
        0.75 * fm_activity + 0.25 * (1.0 - pitch_stability)
    )

    frame_flux = []
    for index, frame in enumerate(transient.frames):
        value = float(frame.spectral_flux)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"spectral_flux[{index}] must be finite and non-negative")
        frame_flux.append(value)
    median_flux = 0.0 if not frame_flux else sorted(frame_flux)[len(frame_flux) // 2]
    flux_score = _clip01(median_flux / 0.20)
    change_score = _clip01(
        transient.change_ratio / 0.10, name="change_ratio_score"
    )
    onset_score = _clip01(
        transient.maximum_onset_strength / 8.0, name="onset_score"
    )
    density_score = _clip01(
        transient.transient_density_per_second / 4.0,
        name="transient_density_score",
    )
    transient_activity = _clip01(
        0.35 * density_score
        + 0.30 * change_score
        + 0.20 * flux_score
        + 0.15 * onset_score
    )

    signal_rms = float(noise.signal_rms)
    noise_floor_rms = float(noise.noise_floor_rms)
    if not math.isfinite(signal_rms) or signal_rms < 0.0:
        raise ValueError("signal_rms must be finite and non-negative")
    if not math.isfinite(noise_floor_rms) or noise_floor_rms < 0.0:
        raise ValueError("noise_floor_rms must be finite and non-negative")
    noise_ratio = 0.0
    if signal_rms > 1e-15:
        noise_ratio = _clip01(
            noise_floor_rms / signal_rms, name="noise_floor_ratio"
        )
    noise_presence = _clip01(
        0.45 * _snr_noise_score(noise.snr_db)
        + 0.30 * noise_ratio
        + 0.15 * (1.0 - periodicity)
        + 0.10 * complexity.spectral_entropy
    )

    evolution = _clip01(
        0.30 * (1.0 - amplitude_stability)
        + 0.30 * change_score
        + 0.20 * flux_score
        + 0.20 * saturation.saturation_variation
    )
    non_periodicity = _clip01(
        0.55 * (1.0 - periodicity)
        + 0.20 * (1.0 - phase_stability)
        + 0.15 * complexity.complexity_score
        + 0.10 * noise_presence
    )
    periodic_stability = _clip01(
        0.45 * pitch_stability
        + 0.30 * phase_stability
        + 0.25 * amplitude_stability
    )
    close_pair = _clip01(beating.confidence if beating.close_fundamentals_detected else 0.0)

    if bool(time_domain.levels.is_silent) or active <= 1e-12:
        raw = {
            BehaviorClass.PERIODIC: 0.0,
            BehaviorClass.QUASI_PERIODIC: 0.0,
            BehaviorClass.EVOLVING: 0.0,
            BehaviorClass.PITCH_VARIABLE: 0.0,
            BehaviorClass.TRANSIENT: 0.0,
            BehaviorClass.NOISY: 0.0,
            BehaviorClass.NON_PERIODIC: 1.0,
            BehaviorClass.HYBRID: 0.0,
        }
    else:
        periodic_raw = periodicity * periodic_stability * (1.0 - 0.45 * fm_activity)
        quasi_raw = periodicity * (1.0 - 0.75 * periodic_stability)
        quasi_raw *= 0.70 + 0.30 * close_pair
        quasi_raw = max(quasi_raw, 0.35 * quasi * close_pair)
        evolving_raw = evolution * (0.35 + 0.65 * active)
        pitch_variable_raw = (
            pitch_variability
            * (0.35 + 0.65 * periodicity)
            * (1.0 - 0.50 * close_pair)
        )
        transient_raw = transient_activity
        noisy_raw = noise_presence
        non_periodic_raw = (
            non_periodicity
            * (1.0 - 0.45 * transient_activity)
            * (1.0 - 0.75 * noise_presence)
        )
        principal = (
            periodic_raw,
            quasi_raw,
            evolving_raw,
            pitch_variable_raw,
            transient_raw,
            noisy_raw,
            non_periodic_raw,
        )
        sorted_principal = sorted(principal, reverse=True)
        balance = 0.0 if len(sorted_principal) < 2 else sorted_principal[1]
        hybrid_raw = _clip01(
            0.55 * balance
            + 0.15 * complexity.complexity_score * balance
            + 0.30 * min(1.0, close_pair + saturation.mean_saturation_score)
        )
        raw = {
            BehaviorClass.PERIODIC: periodic_raw,
            BehaviorClass.QUASI_PERIODIC: quasi_raw,
            BehaviorClass.EVOLVING: evolving_raw,
            BehaviorClass.PITCH_VARIABLE: pitch_variable_raw,
            BehaviorClass.TRANSIENT: transient_raw,
            BehaviorClass.NOISY: noisy_raw,
            BehaviorClass.NON_PERIODIC: non_periodic_raw,
            BehaviorClass.HYBRID: hybrid_raw,
        }

    explanations = {
        BehaviorClass.PERIODIC: (
            "Periodicity, voiced-frame coverage, pitch stability, phase stability, and "
            "amplitude stability support a stable periodic source."
        ),
        BehaviorClass.QUASI_PERIODIC: (
            "Material periodicity remains present while stability is reduced or a close "
            "fundamental pair introduces controlled beating."
        ),
        BehaviorClass.EVOLVING: (
            "Envelope variation, spectral change points, flux, and saturation evolution "
            "support an evolving source."
        ),
        BehaviorClass.PITCH_VARIABLE: (
            "Pitch instability and the dedicated rapid-FM score support a pitch-variable source."
        ),
        BehaviorClass.TRANSIENT: (
            "Transient density, change ratio, onset strength, and spectral flux support a "
            "transient source."
        ),
        BehaviorClass.NOISY: (
            "Noise-floor ratio, SNR-derived noise presence, weak periodicity, and entropy "
            "support a noisy source."
        ),
        BehaviorClass.NON_PERIODIC: (
            "Weak periodicity and phase coherence with material complexity support a "
            "non-periodic source."
        ),
        BehaviorClass.HYBRID: (
            "Several behavior families have material scores and no single family fully "
            "explains the source."
        ),
    }

    total = float(sum(max(0.0, value) for value in raw.values()))
    if total <= 1e-24:
        raw[BehaviorClass.NON_PERIODIC] = 1.0
        total = 1.0
    normalized = {behavior: float(max(0.0, raw[behavior]) / total) for behavior in BehaviorClass}
    ranked = sorted(
        BehaviorClass,
        key=lambda behavior: (-normalized[behavior], list(BehaviorClass).index(behavior)),
    )
    selected = ranked[0]
    top = normalized[selected]
    second = normalized[ranked[1]] if len(ranked) > 1 else 0.0
    confidence = _clip01(top - second + 0.5 * top)
    ambiguity = float(1.0 - confidence)

    scores = tuple(
        BehaviorScore(
            behavior=behavior,
            raw_score=float(max(0.0, raw[behavior])),
            score=normalized[behavior],
            explanation=explanations[behavior],
        )
        for behavior in BehaviorClass
    )
    evidence = (
        f"periodicity={periodicity:.6f}",
        f"pitch_variability={pitch_variability:.6f}",
        f"evolution={evolution:.6f}",
        f"transient_activity={transient_activity:.6f}",
        f"noise_presence={noise_presence:.6f}",
        f"complexity={complexity.complexity_score:.6f}",
        f"beating_confidence={close_pair:.6f}",
    )
    if bool(time_domain.levels.is_silent) or active <= 1e-12:
        reason = (
            "The source is silent or contains no active frame, so it is explicitly "
            "classified as non-periodic rather than assigned an unsupported ninth class."
        )
    else:
        reason = explanations[selected]

    return BehaviorClassification(
        schema_version=1,
        sample_rate=int(signal_analysis.sample_rate),
        sample_count=int(signal_analysis.sample_count),
        sample_sha256=str(signal_analysis.sample_sha256),
        signal_analysis_sha256=str(signal_analysis.analysis_sha256),
        signal_extension_analysis_sha256=str(signal_extension_analysis.analysis_sha256),
        behavior=selected,
        confidence=confidence,
        ambiguity=ambiguity,
        scores=scores,
        evidence=evidence,
        reason=reason,
    )
