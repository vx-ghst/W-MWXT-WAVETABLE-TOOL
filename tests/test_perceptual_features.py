from __future__ import annotations

from dataclasses import replace

import pytest

from v8c_helpers import build_bundle, deterministic_noise, evolving_tone, tone
from w_mwxt_wavetable_tool.perceptual.features import analyze_perceptual_features


def test_all_perceptual_features_are_bounded_and_explained() -> None:
    vector = build_bundle(tone()).perceptual
    assert all(0.0 <= value <= 1.0 for value in vector.feature_map.values())
    assert len(vector.evidence) >= 9
    assert "engineering estimates" in vector.reason


def test_low_tone_has_more_low_frequency_power_than_high_tone() -> None:
    low = build_bundle(tone((80.0, 160.0), (0.8, 0.2))).perceptual
    high = build_bundle(tone((1600.0, 3200.0), (0.8, 0.2))).perceptual
    assert low.low_frequency_power > high.low_frequency_power
    assert high.brightness > low.brightness


def test_noise_has_more_noisiness_and_less_tonalness() -> None:
    tonal = build_bundle(tone()).perceptual
    noise = build_bundle(deterministic_noise()).perceptual
    assert noise.noisiness > tonal.noisiness
    assert noise.tonalness < tonal.tonalness


def test_evolving_source_has_more_motion_than_stable_tone() -> None:
    stable = build_bundle(tone()).perceptual
    evolving = build_bundle(evolving_tone()).perceptual
    assert evolving.motion > stable.motion


def test_perceptual_features_are_deterministic() -> None:
    bundle = build_bundle(tone())
    repeated = analyze_perceptual_features(
        bundle.signal,
        bundle.extension,
        bundle.spectral,
        bundle.harmonic,
        bundle.evolution,
        bundle.formants,
    )
    assert repeated == bundle.perceptual
    assert repeated.analysis_sha256 == bundle.perceptual.analysis_sha256


@pytest.mark.parametrize(
    "component,field",
    [
        ("extension", "signal_analysis_sha256"),
        ("harmonic", "spectral_analysis_sha256"),
        ("evolution", "spectral_analysis_sha256"),
        ("formants", "spectral_analysis_sha256"),
    ],
)
def test_broken_analysis_links_are_rejected(component: str, field: str) -> None:
    bundle = build_bundle(tone())
    values = {
        "signal_analysis": bundle.signal,
        "signal_extension_analysis": bundle.extension,
        "spectral_analysis": bundle.spectral,
        "harmonic_perceptual_analysis": bundle.harmonic,
        "spectral_evolution_analysis": bundle.evolution,
        "formant_analysis": bundle.formants,
    }
    key = {
        "extension": "signal_extension_analysis",
        "harmonic": "harmonic_perceptual_analysis",
        "evolution": "spectral_evolution_analysis",
        "formants": "formant_analysis",
    }[component]
    values[key] = replace(values[key], **{field: "f" * 64})
    with pytest.raises(ValueError, match="does not link"):
        analyze_perceptual_features(**values)


def test_sample_identity_mismatch_is_rejected() -> None:
    bundle = build_bundle(tone())
    changed = replace(bundle.formants, sample_count=bundle.formants.sample_count + 1)
    with pytest.raises(ValueError, match="sample counts"):
        analyze_perceptual_features(
            bundle.signal,
            bundle.extension,
            bundle.spectral,
            bundle.harmonic,
            bundle.evolution,
            changed,
        )
