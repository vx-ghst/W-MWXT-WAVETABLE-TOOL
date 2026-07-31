from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .models import AudioMeasurements


def channel_rms(samples: npt.NDArray[np.float64]) -> tuple[float, ...]:
    if samples.ndim != 2:
        raise ValueError("channel_rms expects a frames-by-channels array")
    if samples.shape[0] == 0:
        return tuple(0.0 for _ in range(samples.shape[1]))
    values = np.sqrt(np.mean(np.square(samples), axis=0, dtype=np.float64))
    return tuple(float(value) for value in values)


def stereo_correlation(samples: npt.NDArray[np.float64]) -> float | None:
    if samples.ndim != 2 or samples.shape[1] != 2:
        return None
    left = samples[:, 0]
    right = samples[:, 1]
    if left.size == 0:
        return None
    left_centered = left - np.mean(left, dtype=np.float64)
    right_centered = right - np.mean(right, dtype=np.float64)
    denominator = float(
        np.sqrt(
            np.dot(left_centered, left_centered)
            * np.dot(right_centered, right_centered)
        )
    )
    if denominator == 0.0:
        return None
    value = float(np.dot(left_centered, right_centered) / denominator)
    return max(-1.0, min(1.0, value))


def measure_mono(
    samples: npt.NDArray[np.float64],
    *,
    silence_threshold: float = 1e-12,
    dc_threshold: float = 1e-4,
) -> AudioMeasurements:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 1:
        raise ValueError("measure_mono expects a one-dimensional array")
    if data.size == 0:
        raise ValueError("Cannot measure empty audio")
    all_finite = bool(np.all(np.isfinite(data)))
    if not all_finite:
        raise ValueError("Cannot measure audio containing NaN or infinity")
    minimum = float(np.min(data))
    maximum = float(np.max(data))
    peak = float(np.max(np.abs(data)))
    rms = float(np.sqrt(np.mean(np.square(data), dtype=np.float64)))
    mean = float(np.mean(data, dtype=np.float64))
    return AudioMeasurements(
        sample_count=int(data.size),
        minimum=minimum,
        maximum=maximum,
        peak_absolute=peak,
        rms=rms,
        mean=mean,
        dc_offset=mean,
        is_silent=peak <= silence_threshold,
        has_dc_offset=abs(mean) > dc_threshold,
        all_finite=True,
    )
