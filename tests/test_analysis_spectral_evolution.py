from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from v8c_helpers import build_bundle, evolving_tone, tone
from w_mwxt_wavetable_tool.analysis.harmonic_perceptual import analyze_harmonic_perceptual
from w_mwxt_wavetable_tool.analysis.spectral import analyze_spectral
from w_mwxt_wavetable_tool.analysis.spectral_evolution import (
    PartialKind,
    SpectralSpan,
    analyze_spectral_correlations,
    analyze_spectral_evolution,
)


def test_four_band_contract_is_complete_and_bounded() -> None:
    result = build_bundle(tone()).evolution
    assert result.active_frame_count > 0
    assert result.low_ratio + result.low_mid_ratio + result.mid_ratio + result.high_ratio == pytest.approx(1.0)
    assert all(0.0 <= value <= 1.0 for value in (
        result.low_ratio,
        result.low_mid_ratio,
        result.mid_ratio,
        result.high_ratio,
        result.mean_harmonic_energy_ratio,
        result.mean_inharmonic_energy_ratio,
        result.useful_change_score,
    ))


def test_evolving_source_has_more_useful_change_than_stable_tone() -> None:
    stable = build_bundle(tone()).evolution
    evolving = build_bundle(evolving_tone()).evolution
    assert evolving.useful_change_score > stable.useful_change_score
    assert evolving.harmonic_evolution_score >= stable.harmonic_evolution_score


def test_partial_inventory_contains_harmonic_and_inharmonic_kinds() -> None:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    samples = 0.7 * np.sin(2 * np.pi * 100 * time) + 0.3 * np.sin(2 * np.pi * 735 * time)
    spectral = analyze_spectral(samples, sample_rate, frame_size=1024, hop_size=256, fft_size=4096)
    harmonic = analyze_harmonic_perceptual(spectral, fundamental_frequency_hz=100.0)
    result = analyze_spectral_evolution(samples, sample_rate, spectral, harmonic)
    kinds = {partial.kind for partial in result.partials}
    assert PartialKind.HARMONIC in kinds
    assert PartialKind.INHARMONIC in kinds


def test_silence_has_zero_trajectories_and_no_partials() -> None:
    samples = np.zeros(16000, dtype=np.float64)
    spectral = analyze_spectral(samples, 16000, frame_size=1024, hop_size=256, fft_size=2048)
    harmonic = analyze_harmonic_perceptual(spectral, fundamental_frequency_hz=None)
    result = analyze_spectral_evolution(samples, 16000, spectral, harmonic)
    assert result.active_frame_count == 0
    assert result.partials == ()
    assert result.useful_change_score == 0.0
    assert result.mean_adjacent_correlation == 1.0


def test_spectral_evolution_is_deterministic_and_json_safe() -> None:
    bundle = build_bundle(evolving_tone())
    repeated = analyze_spectral_evolution(
        bundle.samples,
        bundle.sample_rate,
        bundle.spectral,
        bundle.harmonic,
    )
    assert bundle.evolution.analysis_sha256 == repeated.analysis_sha256
    json.dumps(bundle.evolution.to_dict(), allow_nan=False, sort_keys=True)


def test_sample_identity_mismatch_is_rejected() -> None:
    bundle = build_bundle(tone())
    changed = bundle.samples.copy()
    changed[0] += 0.01
    with pytest.raises(ValueError, match="hash"):
        analyze_spectral_evolution(
            changed,
            bundle.sample_rate,
            bundle.spectral,
            bundle.harmonic,
        )


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"low_band_max_hz": 0.0}, "boundaries"),
        ({"low_mid_band_max_hz": 100.0}, "boundaries"),
        ({"mid_band_max_hz": 500.0}, "boundaries"),
        ({"harmonic_tolerance_cents": 0.0}, "positive"),
        ({"minimum_partial_power_ratio": 2.0}, "between 0 and 1"),
        ({"maximum_partials": 0}, "positive"),
    ],
)
def test_invalid_evolution_configuration_is_rejected(kwargs, match) -> None:
    bundle = build_bundle(tone())
    with pytest.raises(ValueError, match=match):
        analyze_spectral_evolution(
            bundle.samples,
            bundle.sample_rate,
            bundle.spectral,
            bundle.harmonic,
            **kwargs,
        )


def test_spectral_correlations_distinguish_identical_and_different_spans() -> None:
    first = tone(duration=0.5)
    second = tone((880.0,), (0.8,), duration=0.5)
    samples = np.concatenate((first, first, second))
    result = analyze_spectral_correlations(
        samples,
        16000,
        (
            SpectralSpan("a", 0, first.size),
            SpectralSpan("b", first.size, 2 * first.size),
            SpectralSpan("c", 2 * first.size, samples.size),
        ),
    )
    assert result.correlations[0].correlation == pytest.approx(1.0)
    assert result.correlations[1].distance > 0.5
    assert len(result.correlations) == 3


def test_spectral_correlation_span_validation() -> None:
    samples = tone()
    with pytest.raises(ValueError, match="two spans"):
        analyze_spectral_correlations(samples, 16000, (SpectralSpan("only", 0, samples.size),))
    with pytest.raises(ValueError, match="exceeds"):
        analyze_spectral_correlations(
            samples,
            16000,
            (SpectralSpan("a", 0, 100), SpectralSpan("b", 100, samples.size + 1)),
        )


def test_evolution_model_rejects_broken_aggregate_ratios() -> None:
    result = build_bundle(tone()).evolution
    with pytest.raises(ValueError, match="four-band"):
        replace(result, low_ratio=0.9)
