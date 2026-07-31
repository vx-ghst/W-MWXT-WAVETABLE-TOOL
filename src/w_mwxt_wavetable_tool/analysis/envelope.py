from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from .framing import iter_frames, validate_mono_samples
from .models import EnvelopeAnalysis
from ..errors import AnalysisError


def analyze_envelope(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    frame_size: int = 2048,
    hop_size: int = 512,
    active_threshold: float = 1e-8,
) -> EnvelopeAnalysis:
    data = validate_mono_samples(samples)
    if sample_rate <= 0:
        raise AnalysisError("sample_rate must be positive")
    if frame_size <= 0 or hop_size <= 0:
        raise AnalysisError("frame_size and hop_size must be positive")
    if active_threshold < 0.0:
        raise AnalysisError("active_threshold must not be negative")

    framed = iter_frames(data, frame_size=frame_size, hop_size=hop_size)
    starts: list[int] = []
    centers: list[float] = []
    rms_values: list[float] = []
    peak_values: list[float] = []
    for start, frame in framed:
        starts.append(start)
        centers.append(float((start + (frame.size - 1) / 2.0) / sample_rate))
        rms_values.append(
            float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)))
        )
        peak_values.append(float(np.max(np.abs(frame))))

    rms_array = np.asarray(rms_values, dtype=np.float64)
    mean_rms = float(np.mean(rms_array, dtype=np.float64))
    standard_deviation = float(np.std(rms_array, dtype=np.float64))
    coefficient = None if mean_rms <= active_threshold else float(standard_deviation / mean_rms)
    amplitude_stability = 1.0 if coefficient is None else float(1.0 / (1.0 + coefficient))
    active = rms_array > active_threshold
    active_count = int(np.count_nonzero(active))
    active_ratio = float(active_count / rms_array.size)

    active_values = rms_array[active]
    if active_values.size < 2:
        dynamic_range_db = None
    else:
        minimum_active = float(np.min(active_values))
        maximum_active = float(np.max(active_values))
        dynamic_range_db = (
            None
            if minimum_active <= 0.0
            else float(20.0 * math.log10(maximum_active / minimum_active))
        )

    return EnvelopeAnalysis(
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        frame_size=int(frame_size),
        hop_size=int(hop_size),
        frame_starts=tuple(starts),
        frame_center_seconds=tuple(centers),
        frame_rms=tuple(rms_values),
        frame_peak=tuple(peak_values),
        mean_rms=mean_rms,
        standard_deviation_rms=standard_deviation,
        coefficient_of_variation=coefficient,
        amplitude_stability=amplitude_stability,
        minimum_frame_rms=float(np.min(rms_array)),
        maximum_frame_rms=float(np.max(rms_array)),
        active_frame_count=active_count,
        active_frame_ratio=active_ratio,
        envelope_dynamic_range_db=dynamic_range_db,
    )
