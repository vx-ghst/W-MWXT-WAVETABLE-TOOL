from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from .framing import validate_mono_samples
from .models import LevelAnalysis
from ..errors import AnalysisError


def _dbfs(value: float) -> float | None:
    if value <= 0.0:
        return None
    return float(20.0 * math.log10(value))


def analyze_levels(
    samples: npt.ArrayLike,
    *,
    clipping_threshold: float = 1.0,
    near_clip_threshold: float = 0.98,
    silence_threshold: float = 1e-12,
    dc_threshold: float = 1e-4,
    flat_derivative_tolerance: float = 1e-7,
    saturation_probability_threshold: float = 0.5,
) -> LevelAnalysis:
    data = validate_mono_samples(samples)
    if clipping_threshold <= 0.0:
        raise AnalysisError("clipping_threshold must be positive")
    if not 0.0 < near_clip_threshold <= clipping_threshold:
        raise AnalysisError(
            "near_clip_threshold must be positive and not exceed clipping_threshold"
        )
    if silence_threshold < 0.0 or dc_threshold < 0.0:
        raise AnalysisError("silence_threshold and dc_threshold must not be negative")
    if flat_derivative_tolerance < 0.0:
        raise AnalysisError("flat_derivative_tolerance must not be negative")
    if not 0.0 <= saturation_probability_threshold <= 1.0:
        raise AnalysisError(
            "saturation_probability_threshold must be between 0 and 1"
        )

    sample_count = int(data.size)
    minimum = float(np.min(data))
    maximum = float(np.max(data))
    positive_peak = max(0.0, maximum)
    negative_peak = max(0.0, -minimum)
    peak_absolute = max(positive_peak, negative_peak)
    rms = float(np.sqrt(np.mean(np.square(data), dtype=np.float64)))
    mean = float(np.mean(data, dtype=np.float64))
    is_silent = peak_absolute <= silence_threshold
    has_dc_offset = abs(mean) > dc_threshold

    crest_factor = None if rms <= silence_threshold else float(peak_absolute / rms)
    crest_factor_db = _dbfs(crest_factor) if crest_factor is not None else None

    absolute = np.abs(data)
    clipped_mask = absolute >= clipping_threshold
    near_clip_mask = absolute >= near_clip_threshold
    clipped_count = int(np.count_nonzero(clipped_mask))
    near_clip_count = int(np.count_nonzero(near_clip_mask))

    flat_extreme_count = 0
    if sample_count >= 2:
        derivative = np.abs(np.diff(data))
        flat_pairs = derivative <= flat_derivative_tolerance
        extreme_pairs = near_clip_mask[:-1] & near_clip_mask[1:]
        pair_indices = np.flatnonzero(flat_pairs & extreme_pairs)
        if pair_indices.size:
            flat_samples = np.zeros(sample_count, dtype=bool)
            flat_samples[pair_indices] = True
            flat_samples[pair_indices + 1] = True
            flat_extreme_count = int(np.count_nonzero(flat_samples))

    clipped_ratio = float(clipped_count / sample_count)
    near_clip_ratio = float(near_clip_count / sample_count)
    flat_extreme_ratio = float(flat_extreme_count / sample_count)

    clipping_component = min(1.0, clipped_ratio / 0.001)
    flat_component = min(1.0, flat_extreme_ratio / 0.005)
    saturation_likelihood = float(max(clipping_component, flat_component))
    saturation_probable = saturation_likelihood >= saturation_probability_threshold
    if clipped_count:
        saturation_reason = (
            "Samples reached or exceeded the configured clipping threshold."
        )
    elif flat_extreme_count:
        saturation_reason = (
            "Repeated near-extreme samples with near-zero slope suggest flat limiting."
        )
    else:
        saturation_reason = (
            "No threshold clipping or repeated flat near-extreme region was detected."
        )

    peak_sum = positive_peak + negative_peak
    peak_asymmetry = (
        0.0 if peak_sum <= silence_threshold else float((positive_peak - negative_peak) / peak_sum)
    )

    return LevelAnalysis(
        sample_count=sample_count,
        minimum=minimum,
        maximum=maximum,
        positive_peak=positive_peak,
        negative_peak=negative_peak,
        peak_absolute=peak_absolute,
        peak_dbfs=_dbfs(peak_absolute),
        rms=rms,
        rms_dbfs=_dbfs(rms),
        crest_factor=crest_factor,
        crest_factor_db=crest_factor_db,
        mean=mean,
        dc_offset=mean,
        is_silent=is_silent,
        has_dc_offset=has_dc_offset,
        clipping_threshold=float(clipping_threshold),
        clipped_sample_count=clipped_count,
        clipped_sample_ratio=clipped_ratio,
        is_clipped=clipped_count > 0,
        near_clip_threshold=float(near_clip_threshold),
        near_clip_sample_count=near_clip_count,
        near_clip_sample_ratio=near_clip_ratio,
        flat_extreme_sample_count=flat_extreme_count,
        flat_extreme_sample_ratio=flat_extreme_ratio,
        saturation_likelihood=saturation_likelihood,
        saturation_probable=saturation_probable,
        saturation_reason=saturation_reason,
        peak_asymmetry=peak_asymmetry,
    )
