from __future__ import annotations

from hashlib import sha256

import numpy as np
import numpy.typing as npt

from .envelope import analyze_envelope
from .framing import validate_mono_samples
from .levels import analyze_levels
from .models import TimeDomainAnalysis
from ..audio import AudioSource


def _sample_sha256(samples: npt.NDArray[np.float64]) -> str:
    canonical = samples.astype("<f8", copy=False).tobytes(order="C")
    return sha256(canonical).hexdigest()


def analyze_time_domain(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    frame_size: int = 2048,
    hop_size: int = 512,
    clipping_threshold: float = 1.0,
    near_clip_threshold: float = 0.98,
    silence_threshold: float = 1e-12,
    dc_threshold: float = 1e-4,
    active_threshold: float = 1e-8,
) -> TimeDomainAnalysis:
    data = validate_mono_samples(samples)
    levels = analyze_levels(
        data,
        clipping_threshold=clipping_threshold,
        near_clip_threshold=near_clip_threshold,
        silence_threshold=silence_threshold,
        dc_threshold=dc_threshold,
    )
    envelope = analyze_envelope(
        data,
        sample_rate,
        frame_size=frame_size,
        hop_size=hop_size,
        active_threshold=active_threshold,
    )
    return TimeDomainAnalysis(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=_sample_sha256(data),
        levels=levels,
        envelope=envelope,
    )


def analyze_audio_source(
    source: AudioSource,
    *,
    frame_size: int = 2048,
    hop_size: int = 512,
    clipping_threshold: float = 1.0,
    near_clip_threshold: float = 0.98,
    silence_threshold: float = 1e-12,
    dc_threshold: float = 1e-4,
    active_threshold: float = 1e-8,
) -> TimeDomainAnalysis:
    return analyze_time_domain(
        source.mono_samples,
        source.metadata.sample_rate,
        frame_size=frame_size,
        hop_size=hop_size,
        clipping_threshold=clipping_threshold,
        near_clip_threshold=near_clip_threshold,
        silence_threshold=silence_threshold,
        dc_threshold=dc_threshold,
        active_threshold=active_threshold,
    )
