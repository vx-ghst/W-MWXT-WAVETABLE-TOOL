from __future__ import annotations

import json

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis.beating import analyze_beating


def tone_pair(first: float, second: float | None = None) -> tuple[np.ndarray, int]:
    sample_rate = 16000
    time = np.arange(sample_rate * 2, dtype=np.float64) / sample_rate
    samples = 0.5 * np.sin(2.0 * np.pi * first * time)
    if second is not None:
        samples += 0.4 * np.sin(2.0 * np.pi * second * time)
    return samples, sample_rate


def test_detects_two_close_fundamentals_and_beat_rate() -> None:
    samples, sample_rate = tone_pair(220.0, 223.0)
    result = analyze_beating(samples, sample_rate)
    assert result.close_fundamentals_detected is True
    assert result.primary_frequency_hz == pytest.approx(220.0, abs=0.1)
    assert result.secondary_frequency_hz == pytest.approx(223.0, abs=0.1)
    assert result.beat_rate_hz == pytest.approx(3.0, abs=0.15)
    assert result.detune_cents > 20.0
    assert result.unison_detected is True


def test_single_tone_has_no_close_secondary() -> None:
    samples, sample_rate = tone_pair(220.0)
    result = analyze_beating(samples, sample_rate)
    assert result.close_fundamentals_detected is False
    assert result.secondary_frequency_hz is None
    assert result.beat_rate_hz == 0.0


def test_wider_detune_is_not_unison() -> None:
    samples, sample_rate = tone_pair(220.0, 228.0)
    result = analyze_beating(samples, sample_rate, maximum_detune_cents=80.0)
    assert result.close_fundamentals_detected is True
    assert result.unison_detected is False


def test_hash_and_json_are_deterministic_and_finite() -> None:
    samples, sample_rate = tone_pair(330.0, 334.0)
    first = analyze_beating(samples, sample_rate)
    second = analyze_beating(samples, sample_rate)
    assert first.analysis_sha256 == second.analysis_sha256
    json.dumps(first.to_dict(), allow_nan=False, sort_keys=True)


def test_invalid_analysis_window_is_rejected() -> None:
    samples, sample_rate = tone_pair(220.0, 223.0)
    with pytest.raises(Exception, match="maximum_samples"):
        analyze_beating(samples, sample_rate, maximum_samples=0)
