from __future__ import annotations

import numpy as np

from w_mwxt_wavetable_tool.repair import RepairContext


def sine_wave(
    harmonic: int = 1,
    *,
    amplitude: float = 0.8,
    sample_count: int = 128,
    phase: float = 0.0,
) -> np.ndarray:
    indexes = np.arange(sample_count, dtype=np.float64)
    return amplitude * np.sin(
        2.0 * np.pi * harmonic * indexes / sample_count + phase
    )


def harmonic_wave(*, sample_count: int = 128) -> np.ndarray:
    indexes = np.arange(sample_count, dtype=np.float64)
    return (
        0.72 * np.sin(2.0 * np.pi * indexes / sample_count)
        + 0.20 * np.sin(4.0 * np.pi * indexes / sample_count)
        + 0.08 * np.sin(6.0 * np.pi * indexes / sample_count)
    )


def clipped_wave() -> np.ndarray:
    result = harmonic_wave()
    result[18:24] = 1.0
    result[74:78] = -1.0
    return result


def noisy_wave() -> np.ndarray:
    rng = np.random.default_rng(20260803)
    result = 0.45 * sine_wave() + rng.normal(0.0, 0.16, 128)
    peak = float(np.max(np.abs(result)))
    return np.asarray(result / max(1.0, peak / 0.95), dtype=np.float64)


def weak_fundamental_wave() -> np.ndarray:
    indexes = np.arange(128, dtype=np.float64)
    return (
        0.02 * np.sin(2.0 * np.pi * indexes / 128)
        + 0.75 * np.sin(4.0 * np.pi * indexes / 128)
        + 0.12 * np.sin(6.0 * np.pi * indexes / 128)
    )


def high_harmonic_wave() -> np.ndarray:
    indexes = np.arange(128, dtype=np.float64)
    result = (
        0.35 * np.sin(2.0 * np.pi * indexes / 128)
        + 0.30 * np.sin(2.0 * np.pi * 18.0 * indexes / 128)
        + 0.25 * np.sin(2.0 * np.pi * 27.0 * indexes / 128)
    )
    return result / max(1.0, float(np.max(np.abs(result))) / 0.9)


def defective_context(
    *,
    reference: np.ndarray | None = None,
    previous: np.ndarray | None = None,
    following: np.ndarray | None = None,
) -> RepairContext:
    return RepairContext(
        expected_sample_count=128,
        detected_pitch_hz=102.0,
        expected_pitch_hz=110.0,
        reference_samples=(
            None if reference is None else tuple(float(value) for value in reference)
        ),
        previous_samples=(
            None if previous is None else tuple(float(value) for value in previous)
        ),
        next_samples=(
            None if following is None else tuple(float(value) for value in following)
        ),
        target_rms=0.55,
        aliasing_risk=0.45,
        safe_harmonic_limit=12,
        tonal_expected=True,
        source_label="fixture",
    )
