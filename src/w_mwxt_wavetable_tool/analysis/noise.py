
from __future__ import annotations

from hashlib import sha256
import math

import numpy as np
import numpy.typing as npt

from .framing import validate_mono_samples
from .models import NoiseAnalysis, NoiseClass, NoiseFrameAnalysis, PitchPeriodicityAnalysis
from .periodicity import analyze_pitch_periodicity
from ..audio import AudioSource
from ..errors import AnalysisError


def _sample_sha256(samples: npt.NDArray[np.float64]) -> str:
    canonical = samples.astype("<f8", copy=False).tobytes(order="C")
    return sha256(canonical).hexdigest()


def _dbfs(value: float) -> float | None:
    if value <= 0.0:
        return None
    return float(20.0 * math.log10(value))


def _linear_quantile(values: np.ndarray, quantile: float) -> float:
    ordered = np.sort(np.asarray(values, dtype=np.float64), kind="stable")
    if ordered.size == 1:
        return float(ordered[0])
    position = quantile * (ordered.size - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    fraction = position - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def _periodic_residual_rms(frame: np.ndarray, lag: float) -> float:
    start = int(math.ceil(lag))
    if start >= frame.size - 1:
        return float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)))
    indexes = np.arange(start, frame.size, dtype=np.float64)
    source_positions = indexes - lag
    source = np.interp(source_positions, np.arange(frame.size, dtype=np.float64), frame)
    residual = frame[start:] - source
    if residual.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(residual), dtype=np.float64)) / math.sqrt(2.0))


def _classification(signal_rms: float, noise_floor_rms: float, snr_db: float | None, silence_threshold: float, minimum_noise_rms: float) -> tuple[NoiseClass, str]:
    if signal_rms <= silence_threshold:
        return NoiseClass.SILENT, "The complete signal is below the configured silence threshold."
    if noise_floor_rms <= minimum_noise_rms:
        return NoiseClass.PRISTINE, "The deterministic residual estimate is at or below the configured minimum noise floor."
    assert snr_db is not None
    if snr_db >= 40.0:
        return NoiseClass.PRISTINE, "The estimated signal-to-noise ratio is at least 40 dB."
    if snr_db >= 20.0:
        return NoiseClass.SIGNAL_DOMINATED, "The estimated signal-to-noise ratio is at least 20 dB."
    if snr_db >= 6.0:
        return NoiseClass.MIXED, "Signal and estimated background noise are both materially present."
    return NoiseClass.NOISE_DOMINATED, "The estimated signal-to-noise ratio is below 6 dB."


def analyze_noise(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    pitch_periodicity: PitchPeriodicityAnalysis | None = None,
    frame_size: int = 4096,
    hop_size: int = 1024,
    minimum_frequency_hz: float = 40.0,
    maximum_frequency_hz: float = 2000.0,
    confidence_threshold: float = 0.60,
    lower_quantile: float = 0.20,
    silence_threshold: float = 1e-12,
    minimum_noise_rms: float = 1e-12,
) -> NoiseAnalysis:
    data = validate_mono_samples(samples)
    if sample_rate <= 0:
        raise AnalysisError("sample_rate must be positive")
    if frame_size <= 0 or hop_size <= 0:
        raise AnalysisError("frame_size and hop_size must be positive")
    if not 0.0 < lower_quantile <= 1.0:
        raise AnalysisError("lower_quantile must be in (0, 1]")
    if silence_threshold < 0.0 or minimum_noise_rms < 0.0:
        raise AnalysisError("noise thresholds must not be negative")

    pitch = pitch_periodicity
    if pitch is None:
        pitch = analyze_pitch_periodicity(
            data,
            sample_rate,
            frame_size=frame_size,
            hop_size=hop_size,
            minimum_frequency_hz=minimum_frequency_hz,
            maximum_frequency_hz=maximum_frequency_hz,
            confidence_threshold=confidence_threshold,
        )
    if pitch.sample_rate != sample_rate or pitch.sample_count != data.size:
        raise AnalysisError("precomputed pitch analysis does not match the signal shape")
    if pitch.sample_sha256 != _sample_sha256(data):
        raise AnalysisError("precomputed pitch analysis does not match the signal fingerprint")

    noise_frames: list[NoiseFrameAnalysis] = []
    candidates: list[float] = []
    for index, pitch_frame in enumerate(pitch.frames):
        start = pitch_frame.start_sample
        stop = min(start + pitch_frame.sample_count, data.size)
        frame = data[start:stop]
        rms = float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)))
        voiced_periodic = bool(
            pitch_frame.voiced and pitch_frame.period_lag_samples is not None
        )
        if voiced_periodic:
            lag = float(pitch_frame.period_lag_samples)
            residual_rms = _periodic_residual_rms(frame, lag)
            method = "periodic_residual"
        else:
            lag = None
            residual_rms = rms
            method = "frame_rms"
        candidates.append(residual_rms)
        noise_frames.append(
            NoiseFrameAnalysis(
                frame_index=index,
                start_sample=start,
                center_seconds=pitch_frame.center_seconds,
                sample_count=int(frame.size),
                rms=rms,
                residual_rms=residual_rms,
                voiced_periodic=voiced_periodic,
                period_lag_samples=lag,
                candidate_method=method,
            )
        )

    candidate_array = np.asarray(candidates, dtype=np.float64)
    noise_floor_rms = _linear_quantile(candidate_array, lower_quantile)
    signal_rms = float(np.sqrt(np.mean(np.square(data), dtype=np.float64)))
    signal_rms_dbfs = _dbfs(signal_rms)
    noise_floor_dbfs = _dbfs(noise_floor_rms)
    if signal_rms <= silence_threshold or noise_floor_rms <= minimum_noise_rms:
        snr_db = None
    else:
        snr_db = float(max(0.0, 20.0 * math.log10(signal_rms / noise_floor_rms)))

    ordered = np.sort(candidate_array, kind="stable")
    lower_count = max(1, int(math.ceil(lower_quantile * ordered.size)))
    lower_values = ordered[:lower_count]
    lower_mean = float(np.mean(lower_values, dtype=np.float64))
    lower_std = float(np.std(lower_values, dtype=np.float64))
    if lower_mean <= minimum_noise_rms:
        stationarity = 1.0
    else:
        stationarity = float(1.0 / (1.0 + lower_std / lower_mean))

    noise_class, reason = _classification(
        signal_rms,
        noise_floor_rms,
        snr_db,
        silence_threshold,
        minimum_noise_rms,
    )
    return NoiseAnalysis(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=_sample_sha256(data),
        frame_size=pitch.frame_size,
        hop_size=pitch.hop_size,
        lower_quantile=float(lower_quantile),
        silence_threshold=float(silence_threshold),
        minimum_noise_rms=float(minimum_noise_rms),
        frames=tuple(noise_frames),
        signal_rms=signal_rms,
        signal_rms_dbfs=signal_rms_dbfs,
        noise_floor_rms=noise_floor_rms,
        noise_floor_dbfs=noise_floor_dbfs,
        snr_db=snr_db,
        periodic_residual_frame_count=sum(frame.voiced_periodic for frame in noise_frames),
        lower_quantile_frame_count=lower_count,
        noise_stationarity=stationarity,
        noise_class=noise_class,
        classification_reason=reason,
    )


def analyze_audio_source_noise(
    source: AudioSource,
    *,
    pitch_periodicity: PitchPeriodicityAnalysis | None = None,
    **kwargs: float | int,
) -> NoiseAnalysis:
    return analyze_noise(
        source.mono_samples,
        source.metadata.sample_rate,
        pitch_periodicity=pitch_periodicity,
        **kwargs,
    )
