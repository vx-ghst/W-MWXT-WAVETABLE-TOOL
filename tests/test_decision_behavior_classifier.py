from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.decision import BehaviorClass, classify_behavior


HASH = "a" * 64
SIGNAL_HASH = "b" * 64
EXTENSION_HASH = "c" * 64


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def analyses(
    *,
    silent: bool = False,
    active: float = 1.0,
    periodicity: float = 0.95,
    voiced: float = 1.0,
    pitch_stability: float = 0.95,
    quasi: float = 0.90,
    phase_stability: float = 0.95,
    amplitude_stability: float = 0.95,
    fm: float = 0.0,
    saturation_variation: float = 0.0,
    saturation_mean: float = 0.0,
    complexity: float = 0.10,
    entropy: float = 0.10,
    close_pair: float = 0.0,
    close_detected: bool = False,
    signal_rms: float = 0.5,
    noise_floor: float = 0.001,
    snr_db: float | None = 40.0,
    transient_density: float = 0.0,
    change_ratio: float = 0.0,
    onset: float = 0.0,
    flux: float = 0.0,
):
    signal = ns(
        sample_rate=48000,
        sample_count=48000,
        sample_sha256=HASH,
        analysis_sha256=SIGNAL_HASH,
        time_domain_analysis=ns(
            levels=ns(is_silent=silent),
            envelope=ns(
                active_frame_ratio=active,
                amplitude_stability=amplitude_stability,
            ),
        ),
        pitch_periodicity_analysis=ns(
            periodicity_score=periodicity,
            voiced_active_ratio=voiced,
            pitch_stability=pitch_stability,
            quasi_periodicity_score=quasi,
        ),
        phase_motion_analysis=ns(phase_stability=phase_stability),
        noise_analysis=ns(
            signal_rms=signal_rms,
            noise_floor_rms=noise_floor,
            snr_db=snr_db,
        ),
        transient_change_analysis=ns(
            frames=(ns(spectral_flux=flux),),
            change_ratio=change_ratio,
            maximum_onset_strength=onset,
            transient_density_per_second=transient_density,
        ),
    )
    extension = ns(
        sample_rate=48000,
        sample_count=48000,
        sample_sha256=HASH,
        signal_analysis_sha256=SIGNAL_HASH,
        analysis_sha256=EXTENSION_HASH,
        frequency_modulation_analysis=ns(rapid_fm_score=fm),
        saturation_analysis=ns(
            saturation_variation=saturation_variation,
            mean_saturation_score=saturation_mean,
        ),
        complexity_analysis=ns(
            complexity_score=complexity,
            spectral_entropy=entropy,
        ),
        beating_analysis=ns(
            confidence=close_pair,
            close_fundamentals_detected=close_detected,
        ),
    )
    return signal, extension


def classify(**kwargs):
    return classify_behavior(*analyses(**kwargs))


@pytest.mark.parametrize(
    "expected,parameters",
    [
        (BehaviorClass.PERIODIC, {}),
        (
            BehaviorClass.QUASI_PERIODIC,
            dict(
                periodicity=0.90,
                pitch_stability=0.35,
                phase_stability=0.45,
                amplitude_stability=0.75,
                close_pair=0.95,
                close_detected=True,
                complexity=0.20,
            ),
        ),
        (
            BehaviorClass.EVOLVING,
            dict(
                periodicity=0.45,
                voiced=0.60,
                pitch_stability=0.65,
                phase_stability=0.55,
                amplitude_stability=0.05,
                saturation_variation=0.95,
                change_ratio=0.50,
                flux=0.50,
                complexity=0.45,
            ),
        ),
        (
            BehaviorClass.PITCH_VARIABLE,
            dict(
                periodicity=0.90,
                voiced=0.95,
                pitch_stability=0.05,
                phase_stability=0.40,
                fm=1.0,
                complexity=0.20,
            ),
        ),
        (
            BehaviorClass.TRANSIENT,
            dict(
                periodicity=0.05,
                voiced=0.10,
                pitch_stability=0.20,
                phase_stability=0.20,
                transient_density=12.0,
                change_ratio=0.60,
                onset=20.0,
                flux=0.90,
                complexity=0.50,
            ),
        ),
        (
            BehaviorClass.NOISY,
            dict(
                periodicity=0.02,
                voiced=0.05,
                pitch_stability=0.10,
                phase_stability=0.10,
                signal_rms=0.20,
                noise_floor=0.18,
                snr_db=1.0,
                complexity=0.95,
                entropy=0.98,
            ),
        ),
        (
            BehaviorClass.NON_PERIODIC,
            dict(
                periodicity=0.0,
                voiced=0.0,
                pitch_stability=0.0,
                phase_stability=0.0,
                amplitude_stability=0.90,
                signal_rms=0.50,
                noise_floor=0.001,
                snr_db=50.0,
                complexity=0.35,
                entropy=0.30,
            ),
        ),
        (
            BehaviorClass.HYBRID,
            dict(
                periodicity=0.60,
                voiced=0.70,
                pitch_stability=0.45,
                quasi=0.60,
                phase_stability=0.45,
                amplitude_stability=0.45,
                fm=0.45,
                saturation_variation=0.60,
                saturation_mean=0.90,
                complexity=1.0,
                entropy=0.90,
                close_pair=1.0,
                close_detected=True,
                signal_rms=0.50,
                noise_floor=0.15,
                snr_db=8.0,
                transient_density=2.0,
                change_ratio=0.15,
                onset=5.0,
                flux=0.20,
            ),
        ),
    ],
)
def test_all_eight_behaviors_have_executable_paths(expected, parameters):
    result = classify(**parameters)
    assert result.behavior is expected
    assert len(result.scores) == 8
    assert all(item.explanation for item in result.scores)


def test_silence_is_explicitly_non_periodic() -> None:
    result = classify(silent=True, active=0.0, periodicity=0.0, voiced=0.0)
    assert result.behavior is BehaviorClass.NON_PERIODIC
    assert result.score_map["non_periodic"] == 1.0


def test_scores_confidence_and_ambiguity_are_normalized() -> None:
    result = classify()
    assert sum(result.score_map.values()) == pytest.approx(1.0)
    assert result.confidence + result.ambiguity == pytest.approx(1.0)


def test_hash_evidence_and_json_are_deterministic() -> None:
    first = classify(fm=0.25, pitch_stability=0.5)
    second = classify(fm=0.25, pitch_stability=0.5)
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.evidence == second.evidence
    json.dumps(first.to_dict(), allow_nan=False, sort_keys=True)


def test_link_mismatch_is_rejected() -> None:
    signal, extension = analyses()
    extension.signal_analysis_sha256 = "d" * 64
    with pytest.raises(ValueError, match="does not link"):
        classify_behavior(signal, extension)


def test_silent_reason_is_explicit() -> None:
    result = classify(silent=True, active=0.0, periodicity=0.0, voiced=0.0)
    assert "silent" in result.reason
    assert "ninth class" in result.reason


def test_non_finite_upstream_metric_is_rejected() -> None:
    signal, extension = analyses()
    extension.frequency_modulation_analysis.rapid_fm_score = float("nan")
    with pytest.raises(ValueError, match="finite"):
        classify_behavior(signal, extension)


@pytest.mark.parametrize(
    "corpus_name,expected",
    [
        ("stable_sine", BehaviorClass.PERIODIC),
        ("white_noise", BehaviorClass.NOISY),
        ("rapid_fm", BehaviorClass.PITCH_VARIABLE),
        ("click_train", BehaviorClass.TRANSIENT),
    ],
)
def test_real_signal_corpus_paths(corpus_name, expected) -> None:
    import numpy as np

    from w_mwxt_wavetable_tool.analysis import (
        analyze_signal,
        analyze_signal_extensions,
    )

    sample_rate = 48000
    sample_count = sample_rate * 2
    time = np.arange(sample_count, dtype=np.float64) / sample_rate
    if corpus_name == "stable_sine":
        samples = 0.4 * np.sin(2.0 * np.pi * 220.0 * time)
    elif corpus_name == "white_noise":
        samples = np.random.default_rng(12345).normal(0.0, 0.2, sample_count)
    elif corpus_name == "rapid_fm":
        modulation_rate = 6.0
        frequency_deviation = 25.0
        samples = 0.4 * np.sin(
            2.0 * np.pi * 220.0 * time
            + (frequency_deviation / modulation_rate)
            * np.sin(2.0 * np.pi * modulation_rate * time)
        )
    else:
        samples = np.zeros(sample_count, dtype=np.float64)
        samples[::2400] = 1.0

    signal = analyze_signal(samples, sample_rate, maximum_frequency_hz=3000.0)
    extension = analyze_signal_extensions(
        samples,
        sample_rate,
        signal_analysis=signal,
        beating_maximum_frequency_hz=3000.0,
    )
    result = classify_behavior(signal, extension)
    assert result.behavior is expected
    assert all(item.explanation for item in result.scores)
    json.dumps(result.to_dict(), allow_nan=False, sort_keys=True)
