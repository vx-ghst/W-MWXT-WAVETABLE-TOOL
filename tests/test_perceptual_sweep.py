from __future__ import annotations

from dataclasses import replace

import pytest

from v8c_helpers import build_bundle, deterministic_noise, tone
from w_mwxt_wavetable_tool.perceptual.sweep import analyze_sweep_continuity


def test_single_state_sweep_is_continuous() -> None:
    vector = build_bundle(tone()).perceptual
    result = analyze_sweep_continuity((vector,))
    assert result.transitions == ()
    assert result.continuity_score == 1.0
    assert result.discontinuity_count == 0


def test_small_monotonic_steps_are_more_continuous_than_large_jump() -> None:
    base = build_bundle(tone()).perceptual
    step1 = replace(base, brightness=min(1.0, base.brightness + 0.05))
    step2 = replace(base, brightness=min(1.0, base.brightness + 0.10))
    smooth = analyze_sweep_continuity((base, step1, step2))
    noise = build_bundle(deterministic_noise()).perceptual
    jumped = analyze_sweep_continuity((base, noise))
    assert smooth.continuity_score > jumped.continuity_score
    assert jumped.maximum_distance > smooth.maximum_distance


def test_discontinuity_threshold_is_explicit() -> None:
    base = build_bundle(tone()).perceptual
    changed = replace(base, brightness=1.0 - base.brightness)
    strict = analyze_sweep_continuity((base, changed), discontinuity_threshold=0.01)
    permissive = analyze_sweep_continuity((base, changed), discontinuity_threshold=1.0)
    assert strict.discontinuity_count == 1
    assert permissive.discontinuity_count == 0


def test_sweep_hash_is_deterministic() -> None:
    base = build_bundle(tone()).perceptual
    changed = replace(base, density=min(1.0, base.density + 0.1))
    first = analyze_sweep_continuity((base, changed))
    second = analyze_sweep_continuity((base, changed))
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256


@pytest.mark.parametrize("threshold", (-0.1, 1.1, float("nan")))
def test_invalid_discontinuity_threshold_is_rejected(threshold: float) -> None:
    vector = build_bundle(tone()).perceptual
    with pytest.raises(ValueError, match="between 0 and 1"):
        analyze_sweep_continuity((vector,), discontinuity_threshold=threshold)


def test_empty_sweep_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        analyze_sweep_continuity(())
