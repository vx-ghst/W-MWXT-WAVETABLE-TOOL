from __future__ import annotations

import numpy as np
import numpy.typing as npt

from ..errors import AnalysisError


FloatArray = npt.NDArray[np.float64]


def validate_mono_samples(samples: npt.ArrayLike) -> FloatArray:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 1 or data.size == 0:
        raise AnalysisError("Analysis expects a non-empty one-dimensional mono signal")
    if not bool(np.all(np.isfinite(data))):
        raise AnalysisError("Analysis requires finite samples")
    return np.ascontiguousarray(data, dtype=np.float64)


def frame_starts(sample_count: int, *, frame_size: int, hop_size: int) -> tuple[int, ...]:
    if sample_count <= 0:
        raise AnalysisError("sample_count must be positive")
    if frame_size <= 0 or hop_size <= 0:
        raise AnalysisError("frame_size and hop_size must be positive")
    if sample_count <= frame_size:
        return (0,)
    last_start = sample_count - frame_size
    starts = list(range(0, last_start + 1, hop_size))
    if starts[-1] != last_start:
        starts.append(last_start)
    return tuple(starts)


def iter_frames(
    samples: FloatArray,
    *,
    frame_size: int,
    hop_size: int,
) -> tuple[tuple[int, FloatArray], ...]:
    starts = frame_starts(samples.size, frame_size=frame_size, hop_size=hop_size)
    frames: list[tuple[int, FloatArray]] = []
    for start in starts:
        stop = min(start + frame_size, samples.size)
        frames.append((start, samples[start:stop]))
    return tuple(frames)
