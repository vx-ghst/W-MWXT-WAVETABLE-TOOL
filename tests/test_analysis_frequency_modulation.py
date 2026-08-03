from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis.frequency_modulation import analyze_frequency_modulation


HASH = "a" * 64
PITCH_HASH = "b" * 64


def pitch_analysis(*, modulation_rate: float = 0.0, depth_cents: float = 0.0):
    times = np.arange(200, dtype=np.float64) * 0.01
    cents = depth_cents * np.sin(2.0 * np.pi * modulation_rate * times)
    frequencies = 440.0 * np.power(2.0, cents / 1200.0)
    frames = tuple(
        SimpleNamespace(
            center_seconds=float(time),
            frequency_hz=float(frequency),
            periodicity_score=0.95,
            voiced=True,
        )
        for time, frequency in zip(times, frequencies)
    )
    return SimpleNamespace(
        sample_rate=48000,
        sample_count=96000,
        sample_sha256=HASH,
        analysis_sha256=PITCH_HASH,
        frame_size=2048,
        hop_size=480,
        frames=frames,
        frequency_hz=440.0,
        voiced_active_ratio=1.0,
        periodicity_score=0.95,
    )


def test_detects_rapid_frequency_modulation() -> None:
    result = analyze_frequency_modulation(
        pitch_analysis(modulation_rate=8.0, depth_cents=40.0)
    )
    assert result.rapid_fm_detected is True
    assert result.modulation_rate_hz == pytest.approx(8.0, rel=0.15)
    assert result.modulation_depth_cents > 20.0
    assert result.rapid_fm_score > 0.5
    assert result.confidence > 0.8


def test_stable_pitch_is_not_rapid_fm() -> None:
    result = analyze_frequency_modulation(pitch_analysis())
    assert result.rapid_fm_detected is False
    assert result.rapid_fm_score == pytest.approx(0.0)
    assert result.modulation_rate_hz == pytest.approx(0.0)


def test_no_voiced_frames_is_explicit() -> None:
    source = pitch_analysis()
    source.frames = tuple()
    source.frequency_hz = None
    source.voiced_active_ratio = 0.0
    result = analyze_frequency_modulation(source)
    assert result.frames == ()
    assert result.confidence == 0.0
    assert "No voiced frame" in result.reason


def test_hash_and_json_are_deterministic_and_finite() -> None:
    first = analyze_frequency_modulation(
        pitch_analysis(modulation_rate=7.0, depth_cents=30.0)
    )
    second = analyze_frequency_modulation(
        pitch_analysis(modulation_rate=7.0, depth_cents=30.0)
    )
    assert first.analysis_sha256 == second.analysis_sha256
    rendered = json.dumps(first.to_dict(), allow_nan=False, sort_keys=True)
    assert "NaN" not in rendered
    assert "Infinity" not in rendered


def test_source_frame_indexes_are_preserved_when_voicing_has_gaps() -> None:
    source = pitch_analysis(modulation_rate=8.0, depth_cents=30.0)
    frames = list(source.frames)
    frames[3].voiced = False
    frames[7].voiced = False
    source.frames = tuple(frames)
    result = analyze_frequency_modulation(source)
    assert 3 not in tuple(frame.frame_index for frame in result.frames)
    assert 7 not in tuple(frame.frame_index for frame in result.frames)
    assert result.frames[3].frame_index == 4


def test_non_positive_rapid_fm_gates_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        analyze_frequency_modulation(pitch_analysis(), minimum_rate_hz=0.0)
    with pytest.raises(ValueError, match="positive"):
        analyze_frequency_modulation(pitch_analysis(), minimum_depth_cents=0.0)


def test_sparse_transient_frames_do_not_crash_base_pitch_analysis() -> None:
    from w_mwxt_wavetable_tool.analysis import analyze_signal

    sample_rate = 48000
    samples = np.zeros(sample_rate, dtype=np.float64)
    samples[::2400] = 1.0
    result = analyze_signal(samples, sample_rate, maximum_frequency_hz=3000.0)
    assert result.sample_count == samples.size
    assert 0.0 <= result.pitch_periodicity_analysis.periodicity_score <= 1.0
