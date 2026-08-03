from __future__ import annotations

import json

import numpy as np

from w_mwxt_wavetable_tool.analysis.saturation import analyze_saturation


def test_clean_sine_is_not_saturated() -> None:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    samples = 0.5 * np.sin(2.0 * np.pi * 220.0 * time)
    result = analyze_saturation(samples, sample_rate, frame_size=512, hop_size=128)
    assert result.saturation_detected is False
    assert result.maximum_saturation_score < 0.35


def test_clipped_wave_is_detected() -> None:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    samples = np.clip(2.5 * np.sin(2.0 * np.pi * 220.0 * time), -1.0, 1.0)
    result = analyze_saturation(samples, sample_rate, frame_size=512, hop_size=128)
    assert result.saturation_detected is True
    assert result.maximum_saturation_score >= 0.35
    assert result.saturated_frame_ratio > 0.5


def test_time_varying_saturation_is_reported() -> None:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    clean = 0.25 * np.sin(2.0 * np.pi * 220.0 * time[: sample_rate // 2])
    clipped = np.clip(
        3.0 * np.sin(2.0 * np.pi * 220.0 * time[: sample_rate // 2]),
        -1.0,
        1.0,
    )
    result = analyze_saturation(
        np.concatenate((clean, clipped)),
        sample_rate,
        frame_size=512,
        hop_size=128,
    )
    assert result.saturation_variation > 0.1
    assert min(frame.saturation_score for frame in result.frames) < max(
        frame.saturation_score for frame in result.frames
    )


def test_asymmetry_and_serialization_are_finite() -> None:
    samples = np.array([0.0, 1.0, 1.0, 0.25, -0.1, -0.1] * 100, dtype=np.float64)
    result = analyze_saturation(samples, 8000, frame_size=128, hop_size=64)
    assert result.global_asymmetry > 0.0
    json.dumps(result.to_dict(), allow_nan=False, sort_keys=True)


def test_silence_has_zero_saturation_score() -> None:
    result = analyze_saturation(np.zeros(4096), 16000, frame_size=512, hop_size=128)
    assert result.maximum_saturation_score == 0.0
    assert result.saturation_detected is False


def test_detection_threshold_is_part_of_the_hash_contract() -> None:
    samples = np.linspace(-0.5, 0.5, 4096)
    low = analyze_saturation(samples, 16000, detection_threshold=0.20)
    high = analyze_saturation(samples, 16000, detection_threshold=0.40)
    assert low.analysis_sha256 != high.analysis_sha256
    assert low.detection_threshold == 0.20
    assert high.detection_threshold == 0.40
