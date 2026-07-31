from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.analysis.classification import (
    ClassificationFeature,
    SourceClass,
    SourceClassScore,
    SourceClassification,
    classify_source,
)


HASH = "a" * 64
SIGNAL_HASH = "b" * 64
SPECTRAL_HASH = "c" * 64
HARMONIC_HASH = "d" * 64


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def analyses(
    *,
    silent: bool = False,
    active: float = 1.0,
    periodicity: float = 0.95,
    voiced: float = 1.0,
    pitch_stability: float = 0.95,
    phase_stability: float = 0.95,
    discontinuity: float = 0.0,
    amplitude_stability: float = 0.95,
    spectral_stationarity: float = 0.95,
    noise_stationarity: float = 0.95,
    snr_db: float | None = 35.0,
    transient_density: float = 0.1,
    change_ratio: float = 0.0,
    onset: float = 0.2,
    median_flux: float = 0.01,
    maximum_flux: float = 0.03,
    spectral_entropy: float = 0.15,
    harmonicity: float = 0.92,
    residual: float = 0.08,
    concentration: float = 0.88,
    noisiness: float = 0.02,
    bark_entropy: float = 0.10,
    frequency: float | None = 440.0,
):
    signal = ns(
        sample_rate=48_000,
        sample_count=48_000,
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
            frequency_hz=frequency,
            active_frame_ratio=active,
            voiced_active_ratio=voiced,
            periodicity_score=periodicity,
            pitch_stability=pitch_stability,
        ),
        phase_motion_analysis=ns(
            phase_stability=phase_stability,
            discontinuity_ratio=discontinuity,
        ),
        noise_analysis=ns(
            snr_db=snr_db,
            noise_stationarity=noise_stationarity,
        ),
        transient_change_analysis=ns(
            transient_density_per_second=transient_density,
            change_ratio=change_ratio,
            maximum_onset_strength=onset,
        ),
    )
    spectral = ns(
        sample_rate=48_000,
        sample_count=48_000,
        sample_sha256=HASH,
        analysis_sha256=SPECTRAL_HASH,
        active_frame_ratio=active,
        spectral_stationarity=spectral_stationarity,
        median_spectral_flux=median_flux,
        maximum_spectral_flux=maximum_flux,
        entropy=spectral_entropy,
    )
    harmonic = ns(
        sample_rate=48_000,
        sample_count=48_000,
        sample_sha256=HASH,
        analysis_sha256=HARMONIC_HASH,
        spectral_analysis_sha256=SPECTRAL_HASH,
        fundamental_frequency_hz=frequency,
        harmonic_energy_ratio=harmonicity,
        residual_energy_ratio=residual,
        spectral_concentration=concentration,
        spectral_noisiness=noisiness,
        bark_entropy=bark_entropy,
    )
    return signal, spectral, harmonic


def classify(**kwargs):
    return classify_source(*analyses(**kwargs))


def test_stable_tonal_source():
    assert classify().source_class is SourceClass.STABLE_TONAL


def test_evolving_tonal_source():
    result = classify(
        pitch_stability=0.15,
        phase_stability=0.25,
        discontinuity=0.60,
        spectral_stationarity=0.20,
        median_flux=0.18,
        maximum_flux=0.45,
        amplitude_stability=0.55,
        spectral_entropy=0.25,
    )
    assert result.source_class is SourceClass.EVOLVING_TONAL


def test_noisy_texture_source():
    result = classify(
        periodicity=0.05,
        voiced=0.10,
        harmonicity=0.08,
        residual=0.92,
        concentration=0.10,
        noisiness=0.95,
        snr_db=2.0,
        spectral_entropy=0.95,
        bark_entropy=0.90,
        spectral_stationarity=0.80,
    )
    assert result.source_class is SourceClass.NOISY_TEXTURE


def test_transient_rich_source():
    result = classify(
        periodicity=0.10,
        voiced=0.20,
        harmonicity=0.12,
        residual=0.45,
        concentration=0.25,
        transient_density=8.0,
        change_ratio=0.30,
        onset=15.0,
        median_flux=0.35,
        maximum_flux=0.90,
        spectral_stationarity=0.15,
    )
    assert result.source_class is SourceClass.TRANSIENT_RICH


def test_mixed_complex_source():
    result = classify(
        periodicity=0.60,
        voiced=0.70,
        pitch_stability=0.50,
        phase_stability=0.50,
        amplitude_stability=0.50,
        spectral_stationarity=0.45,
        noise_stationarity=0.45,
        snr_db=9.0,
        transient_density=2.0,
        change_ratio=0.08,
        onset=5.0,
        median_flux=0.14,
        maximum_flux=0.38,
        spectral_entropy=0.95,
        harmonicity=0.55,
        residual=0.45,
        concentration=0.30,
        noisiness=0.50,
        bark_entropy=0.95,
    )
    assert result.source_class is SourceClass.MIXED_COMPLEX


def test_silent_source_override():
    result = classify(
        silent=True,
        active=0.0,
        periodicity=0.0,
        voiced=0.0,
        pitch_stability=0.0,
        phase_stability=0.0,
        amplitude_stability=0.0,
        spectral_stationarity=0.0,
        harmonicity=0.0,
        residual=0.0,
        concentration=0.0,
        noisiness=0.0,
        frequency=None,
    )
    assert result.source_class is SourceClass.SILENT
    assert result.class_score_map["silent"] == 1.0


def test_scores_sum_to_one():
    result = classify()
    assert sum(result.class_score_map.values()) == pytest.approx(1.0)


def test_confidence_and_ambiguity_sum_to_one():
    result = classify()
    assert result.confidence + result.ambiguity == pytest.approx(1.0)


def test_selected_class_has_highest_score():
    result = classify()
    assert result.class_score_map[result.source_class.value] == max(result.class_score_map.values())


def test_analysis_hash_is_deterministic():
    assert classify().analysis_sha256 == classify().analysis_sha256


def test_analysis_hash_changes_with_input():
    assert classify().analysis_sha256 != classify(pitch_stability=0.50).analysis_sha256


def test_to_dict_is_finite_json():
    rendered = json.dumps(classify().to_dict(), allow_nan=False, sort_keys=True)
    assert "NaN" not in rendered
    assert "Infinity" not in rendered


def test_evidence_is_deterministic_and_nonempty():
    first = classify().evidence
    second = classify().evidence
    assert first == second
    assert len(first) == 7


def test_features_are_canonical_and_unique():
    result = classify()
    names = [feature.name for feature in result.features]
    assert names == [
        "active_presence",
        "periodicity",
        "harmonicity",
        "spectral_concentration",
        "tonal_presence",
        "global_stability",
        "temporal_instability",
        "noise_presence",
        "transient_activity",
        "spectral_complexity",
    ]
    assert len(names) == len(set(names))


def test_rejects_sample_rate_mismatch():
    signal, spectral, harmonic = analyses()
    spectral.sample_rate = 44_100
    with pytest.raises(ValueError, match="sample rates"):
        classify_source(signal, spectral, harmonic)


def test_rejects_sample_count_mismatch():
    signal, spectral, harmonic = analyses()
    harmonic.sample_count = 47_999
    with pytest.raises(ValueError, match="sample counts"):
        classify_source(signal, spectral, harmonic)


def test_rejects_sample_hash_mismatch():
    signal, spectral, harmonic = analyses()
    harmonic.sample_sha256 = "e" * 64
    with pytest.raises(ValueError, match="sample hashes"):
        classify_source(signal, spectral, harmonic)


def test_rejects_spectral_link_mismatch():
    signal, spectral, harmonic = analyses()
    harmonic.spectral_analysis_sha256 = "e" * 64
    with pytest.raises(ValueError, match="does not link"):
        classify_source(signal, spectral, harmonic)


def test_rejects_fundamental_mismatch():
    signal, spectral, harmonic = analyses()
    harmonic.fundamental_frequency_hz = 441.0
    with pytest.raises(ValueError, match="fundamental"):
        classify_source(signal, spectral, harmonic)


def test_rejects_fundamental_availability_mismatch():
    signal, spectral, harmonic = analyses(frequency=None)
    harmonic.fundamental_frequency_hz = 440.0
    with pytest.raises(ValueError, match="availability"):
        classify_source(signal, spectral, harmonic)


@pytest.mark.parametrize("source_class", list(SourceClass))
def test_source_class_values_are_stable(source_class: SourceClass):
    assert SourceClass(source_class.value) is source_class


@pytest.mark.parametrize(
    "attribute",
    [
        "active_presence",
        "periodicity",
        "harmonicity",
        "spectral_concentration",
        "tonal_presence",
        "global_stability",
        "temporal_instability",
        "noise_presence",
        "transient_activity",
        "spectral_complexity",
    ],
)
def test_feature_values_are_bounded(attribute: str):
    feature_map = {feature.name: feature.value for feature in classify().features}
    assert 0.0 <= feature_map[attribute] <= 1.0


def test_feature_model_rejects_out_of_range():
    with pytest.raises(ValueError, match="between 0 and 1"):
        ClassificationFeature("bad", 1.1, "bad feature")


def test_score_model_rejects_negative_raw_score():
    with pytest.raises(ValueError, match="must not be negative"):
        SourceClassScore(SourceClass.SILENT, -0.1, 0.0)


def test_classification_is_immutable():
    result = classify()
    with pytest.raises((AttributeError, TypeError)):
        result.confidence = 0.0
