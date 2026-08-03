from __future__ import annotations

import dataclasses
import json
import math

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    WAVETABLE_METRICS_SCHEMA_VERSION,
    WavePairDistance,
    WaveShapeMetrics,
    WavetableContractError,
    analyze_wave_shape,
    compare_wave_shapes,
)

from v8b_helpers import candidate, sine, square


@pytest.mark.parametrize(
    "samples,message",
    [
        ((0,) * 63, "exactly 64"),
        ((0,) * 65, "exactly 64"),
        ((0,) * 63 + (True,), "integer"),
        ((0,) * 63 + (1.5,), "integer"),
        ((0,) * 63 + (-128,), "-127..127"),
        ((0,) * 63 + (128,), "-127..127"),
    ],
)
def test_analyze_wave_shape_rejects_invalid_samples(samples, message):
    with pytest.raises(WavetableContractError, match=message):
        analyze_wave_shape(samples)


def test_zero_wave_metrics_are_finite_and_zero_banded():
    result = analyze_wave_shape((0,) * 64)
    assert result.schema_version == WAVETABLE_METRICS_SCHEMA_VERSION
    assert result.rms == 0.0
    assert result.peak == 0.0
    assert result.crest_factor == 0.0
    assert result.low_band_ratio == 0.0
    assert result.mid_band_ratio == 0.0
    assert result.high_band_ratio == 0.0
    assert result.polarity_balance == 1.0


@pytest.mark.parametrize("harmonic", [1, 2, 4, 8, 16])
def test_sine_metrics_are_bounded(harmonic):
    result = analyze_wave_shape(sine(110, harmonic))
    assert 0.0 < result.rms <= 1.0
    assert 0.0 < result.peak <= 1.0
    assert result.crest_factor >= 1.0
    assert math.isclose(
        result.low_band_ratio + result.mid_band_ratio + result.high_band_ratio,
        1.0,
        abs_tol=1e-9,
    )
    assert 0.0 <= result.complexity <= 1.0


def test_higher_harmonic_moves_spectral_centroid_upward():
    low = analyze_wave_shape(sine(100, 1))
    high = analyze_wave_shape(sine(100, 12))
    assert high.spectral_centroid > low.spectral_centroid
    assert high.high_band_ratio > low.high_band_ratio


def test_square_is_more_complex_than_fundamental_sine():
    sine_result = analyze_wave_shape(sine(100, 1))
    square_result = analyze_wave_shape(square(100, 32))
    assert square_result.complexity > sine_result.complexity
    assert square_result.high_band_ratio > sine_result.high_band_ratio


def test_candidate_and_raw_samples_have_identical_metrics():
    samples = sine(95, 3)
    item = candidate("candidate-a", samples, source_index=0)
    assert analyze_wave_shape(item) == analyze_wave_shape(samples)


def test_metrics_hash_and_dict_are_deterministic():
    first = analyze_wave_shape(sine(97, 5, 0.2))
    second = analyze_wave_shape(sine(97, 5, 0.2))
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256
    assert len(first.analysis_sha256) == 64
    assert json.dumps(first.to_dict(), sort_keys=True, allow_nan=False)


def test_metrics_are_frozen():
    result = analyze_wave_shape(sine())
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.rms = 0.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "field,value",
    [
        ("rms", -0.1),
        ("peak", 1.1),
        ("complexity", float("nan")),
        ("crest_factor", -1.0),
        ("dc_offset", 2.0),
    ],
)
def test_wave_shape_model_rejects_invalid_values(field, value):
    base = analyze_wave_shape(sine()).to_dict()
    base[field] = value
    with pytest.raises(WavetableContractError):
        WaveShapeMetrics(**base)


def test_wave_shape_model_rejects_non_unit_band_sum():
    base = analyze_wave_shape(sine()).to_dict()
    base.update(low_band_ratio=0.5, mid_band_ratio=0.5, high_band_ratio=0.5)
    with pytest.raises(WavetableContractError, match="sum to one"):
        WaveShapeMetrics(**base)


def test_identical_wave_pair_is_exact():
    samples = sine(100, 2)
    result = compare_wave_shapes(samples, samples)
    assert result.exact_match is True
    assert result.polarity_equivalent is False
    assert result.waveform_distance == 0.0
    assert result.perceptual_distance == 0.0
    assert result.correlation == 1.0


def test_opposite_polarity_is_explicitly_equivalent():
    left = sine(100, 3)
    right = tuple(-value for value in left)
    result = compare_wave_shapes(left, right)
    assert result.exact_match is False
    assert result.polarity_equivalent is True
    assert result.inverted_waveform_distance == 0.0
    assert result.correlation == -1.0
    assert result.perceptual_distance == 0.0


def test_pair_distance_is_symmetric_except_order_labels_do_not_exist():
    left = sine(100, 1)
    right = square(100, 20)
    forward = compare_wave_shapes(left, right)
    reverse = compare_wave_shapes(right, left)
    assert forward == reverse
    assert forward.analysis_sha256 == reverse.analysis_sha256


@pytest.mark.parametrize("field", [
    "waveform_distance",
    "inverted_waveform_distance",
    "maximum_sample_distance",
    "absolute_correlation",
    "spectral_distance",
    "feature_distance",
    "perceptual_distance",
])
def test_pair_distance_fields_are_bounded(field):
    result = compare_wave_shapes(sine(110, 1), square(90, 19))
    assert 0.0 <= getattr(result, field) <= 1.0


def test_distinct_waves_have_nonzero_distance():
    result = compare_wave_shapes(sine(110, 1), square(90, 19))
    assert not result.exact_match
    assert not result.polarity_equivalent
    assert result.perceptual_distance > 0.0
    assert result.spectral_distance > 0.0


def test_near_wave_has_less_distance_than_distant_wave():
    base = sine(100, 2)
    near = tuple(max(-127, min(127, value + (1 if index % 11 == 0 else 0))) for index, value in enumerate(base))
    distant = square(100, 21)
    assert compare_wave_shapes(base, near).perceptual_distance < compare_wave_shapes(base, distant).perceptual_distance


@pytest.mark.parametrize("samples", [sine(100, 1), sine(80, 7), square(90, 15), tuple(range(-32, 32))])
def test_metric_rounding_is_stable(samples):
    result = analyze_wave_shape(samples)
    for value in result.to_dict().values():
        if isinstance(value, float):
            assert value == round(value, 12)


def test_pair_model_rejects_mutually_exclusive_flags():
    base = compare_wave_shapes(sine(), sine()).to_dict()
    base["exact_match"] = True
    base["polarity_equivalent"] = True
    with pytest.raises(WavetableContractError, match="mutually exclusive"):
        WavePairDistance(**base)


@pytest.mark.parametrize("field,value", [("correlation", 2.0), ("perceptual_distance", -0.1), ("spectral_distance", float("inf"))])
def test_pair_model_rejects_invalid_values(field, value):
    base = compare_wave_shapes(sine(), square()).to_dict()
    base[field] = value
    with pytest.raises(WavetableContractError):
        WavePairDistance(**base)


def test_deterministic_pseudorandom_wave_corpus_is_finite_and_symmetric():
    import random

    generator = random.Random(801)
    waves = [tuple(generator.randint(-127, 127) for _ in range(64)) for _ in range(24)]
    for wave in waves:
        metrics = analyze_wave_shape(wave)
        assert all(math.isfinite(value) for value in metrics.to_dict().values() if isinstance(value, float))
    for left, right in zip(waves, waves[1:]):
        forward = compare_wave_shapes(left, right)
        reverse = compare_wave_shapes(right, left)
        assert forward == reverse
