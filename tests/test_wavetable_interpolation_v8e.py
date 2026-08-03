from __future__ import annotations

from dataclasses import FrozenInstanceError
import math

import pytest

from v8e_transition_helpers import ALL_INTERPOLATION_METHODS, smooth_candidates

from w_mwxt_wavetable_tool.wavetable import (
    GenerationMethod,
    InterpolationPolicy,
    ProgressionCurve,
    WavetableContractError,
    interpolate_xt_wave,
    progression_value,
    select_interpolation_method,
)


@pytest.mark.parametrize("method", ALL_INTERPOLATION_METHODS)
def test_each_interpolation_family_is_deterministic(method):
    left, right = smooth_candidates(2)
    policy = InterpolationPolicy(method_priority=(method,))
    first = interpolate_xt_wave(left, right, 0.375, method, policy)
    second = interpolate_xt_wave(left, right, 0.375, method, policy)
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256


@pytest.mark.parametrize("method", ALL_INTERPOLATION_METHODS)
def test_each_interpolation_family_stays_xt_safe(method):
    left, right = smooth_candidates(2)
    result = interpolate_xt_wave(
        left,
        right,
        0.5,
        method,
        InterpolationPolicy(method_priority=(method,)),
    )
    assert len(result.stored_samples) == 64
    assert min(result.stored_samples) >= -127
    assert max(result.stored_samples) <= 127
    assert -128 not in result.stored_samples


@pytest.mark.parametrize("method", ALL_INTERPOLATION_METHODS)
def test_each_interpolation_family_preserves_exact_endpoints(method):
    left, right = smooth_candidates(2)
    policy = InterpolationPolicy(method_priority=(method,))
    at_left = interpolate_xt_wave(left, right, 0.0, method, policy)
    at_right = interpolate_xt_wave(left, right, 1.0, method, policy)
    assert at_left.stored_samples == left.stored_samples
    assert at_right.stored_samples == right.stored_samples


@pytest.mark.parametrize("curve", tuple(ProgressionCurve))
def test_progression_curves_preserve_boundaries(curve):
    assert progression_value(0.0, curve, 0.4) == 0.0
    assert progression_value(1.0, curve, 0.4) == 1.0


@pytest.mark.parametrize("curve", tuple(ProgressionCurve))
def test_progression_curves_are_monotonic(curve):
    values = tuple(progression_value(index / 20.0, curve, 0.65) for index in range(21))
    assert values == tuple(sorted(values))


def test_adaptive_progression_changes_with_complexity():
    low = progression_value(0.4, ProgressionCurve.ADAPTIVE, 0.0)
    high = progression_value(0.4, ProgressionCurve.ADAPTIVE, 1.0)
    assert low != high


def test_adaptive_method_selection_returns_enabled_method():
    left, right = smooth_candidates(2)
    enabled = (
        GenerationMethod.WAVEFORM_INTERPOLATION,
        GenerationMethod.SPECTRAL_INTERPOLATION,
    )
    result = select_interpolation_method(left, right, 0.5, enabled)
    assert result.method in enabled


def test_non_adaptive_method_selection_uses_priority_head():
    left, right = smooth_candidates(2)
    policy = InterpolationPolicy(
        method_priority=(
            GenerationMethod.HARMONIC_INTERPOLATION,
            GenerationMethod.WAVEFORM_INTERPOLATION,
        ),
        adaptive_method_selection=False,
    )
    result = select_interpolation_method(
        left,
        right,
        0.5,
        policy.method_priority,
        policy,
    )
    assert result.method is GenerationMethod.HARMONIC_INTERPOLATION



def test_polarity_protection_is_explicit_in_evidence():
    left, right = smooth_candidates(2)
    method = GenerationMethod.PHASE_AWARE_INTERPOLATION
    protected = interpolate_xt_wave(
        left,
        right,
        0.5,
        method,
        InterpolationPolicy(method_priority=(method,), protect_polarity=True),
    )
    unprotected = interpolate_xt_wave(
        left,
        right,
        0.5,
        method,
        InterpolationPolicy(method_priority=(method,), protect_polarity=False),
    )
    assert any("global polarity" in item for item in protected.evidence)
    assert not any("global polarity" in item for item in unprotected.evidence)

def test_interpolated_metrics_remain_bounded():
    left, right = smooth_candidates(2)
    result = select_interpolation_method(
        left,
        right,
        0.5,
        ALL_INTERPOLATION_METHODS,
    )
    for name in (
        "quality_score",
        "usefulness_score",
        "stability_score",
        "harmonic_richness",
        "brightness",
        "bass_power",
        "source_fidelity",
        "xt_compatibility",
        "perceptual_novelty",
    ):
        assert 0.0 <= getattr(result.metrics, name) <= 1.0


def test_interpolation_evidence_is_non_empty():
    left, right = smooth_candidates(2)
    result = select_interpolation_method(
        left,
        right,
        0.5,
        ALL_INTERPOLATION_METHODS,
    )
    assert result.evidence
    assert result.reason
    assert len(result.stored_samples_sha256) == 64


def test_interpolation_models_are_frozen():
    left, right = smooth_candidates(2)
    result = select_interpolation_method(
        left,
        right,
        0.5,
        ALL_INTERPOLATION_METHODS,
    )
    with pytest.raises(FrozenInstanceError):
        result.progress = 0.25


def test_interpolation_rejects_same_candidate_twice():
    left = smooth_candidates(1)[0]
    with pytest.raises(WavetableContractError):
        interpolate_xt_wave(
            left,
            left,
            0.5,
            GenerationMethod.WAVEFORM_INTERPOLATION,
        )


@pytest.mark.parametrize("progress", (-0.1, 1.1, math.inf, math.nan))
def test_interpolation_rejects_invalid_progress(progress):
    left, right = smooth_candidates(2)
    with pytest.raises(WavetableContractError):
        interpolate_xt_wave(
            left,
            right,
            progress,
            GenerationMethod.WAVEFORM_INTERPOLATION,
        )


def test_interpolation_rejects_method_outside_policy():
    left, right = smooth_candidates(2)
    policy = InterpolationPolicy(
        method_priority=(GenerationMethod.WAVEFORM_INTERPOLATION,)
    )
    with pytest.raises(WavetableContractError):
        interpolate_xt_wave(
            left,
            right,
            0.5,
            GenerationMethod.SPECTRAL_INTERPOLATION,
            policy,
        )


def test_method_selection_rejects_empty_allowed_methods():
    left, right = smooth_candidates(2)
    with pytest.raises(WavetableContractError):
        select_interpolation_method(left, right, 0.5, ())


def test_policy_rejects_duplicate_methods():
    with pytest.raises(WavetableContractError):
        InterpolationPolicy(
            method_priority=(
                GenerationMethod.WAVEFORM_INTERPOLATION,
                GenerationMethod.WAVEFORM_INTERPOLATION,
            )
        )
