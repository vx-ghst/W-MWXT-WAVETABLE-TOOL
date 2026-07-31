from __future__ import annotations

from hashlib import sha256
import math

import numpy as np
import numpy.typing as npt

from .framing import iter_frames, validate_mono_samples
from .models import PeriodicityClass, PitchFrameAnalysis, PitchPeriodicityAnalysis
from .pitch import describe_frequency
from ..audio import AudioSource
from ..errors import AnalysisError


def _sample_sha256(samples: npt.NDArray[np.float64]) -> str:
    canonical = samples.astype("<f8", copy=False).tobytes(order="C")
    return sha256(canonical).hexdigest()


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    if values.size == 0 or weights.size != values.size:
        raise AnalysisError("weighted median requires equal non-empty arrays")
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    sorted_weights = weights[order]
    total = float(np.sum(sorted_weights, dtype=np.float64))
    if total <= 0.0:
        return float(np.median(sorted_values))
    midpoint = total / 2.0
    index = int(np.searchsorted(np.cumsum(sorted_weights), midpoint, side="left"))
    return float(sorted_values[min(index, sorted_values.size - 1)])


def _autocorrelation_pitch(
    frame: npt.NDArray[np.float64],
    sample_rate: int,
    *,
    minimum_frequency_hz: float,
    maximum_frequency_hz: float,
) -> tuple[float | None, float | None, float]:
    centered = frame - float(np.mean(frame, dtype=np.float64))
    energy = float(np.dot(centered, centered))
    if energy <= 1e-24:
        return None, None, 0.0

    sample_count = int(centered.size)
    minimum_lag = max(1, int(math.floor(sample_rate / maximum_frequency_hz)))
    maximum_lag = min(
        sample_count - 2,
        int(math.ceil(sample_rate / minimum_frequency_hz)),
    )
    if maximum_lag < minimum_lag:
        return None, None, 0.0

    fft_size = 1 << (2 * sample_count - 1).bit_length()
    spectrum = np.fft.rfft(centered, n=fft_size)
    autocorrelation = np.fft.irfft(spectrum * np.conjugate(spectrum), n=fft_size)[
        :sample_count
    ]
    zero_lag = float(autocorrelation[0])
    if zero_lag <= 0.0:
        return None, None, 0.0

    lags = np.arange(minimum_lag, maximum_lag + 1, dtype=np.int64)
    overlap_correction = sample_count / (sample_count - lags)
    scores = np.asarray(
        autocorrelation[lags] / zero_lag * overlap_correction,
        dtype=np.float64,
    )
    scores = np.clip(scores, -1.0, 1.0)

    if scores.size >= 3:
        local_mask = np.zeros(scores.size, dtype=bool)
        local_mask[1:-1] = (scores[1:-1] > scores[:-2]) & (
            scores[1:-1] >= scores[2:]
        )
        local_indices = np.flatnonzero(local_mask)
    else:
        local_indices = np.empty(0, dtype=np.int64)

    if local_indices.size == 0:
        selected_index = int(np.argmax(scores))
    else:
        local_scores = scores[local_indices]
        best_local = float(np.max(local_scores))
        strong = local_indices[local_scores >= best_local * 0.90]
        selected_index = int(strong[0])

    selected_score = float(max(0.0, scores[selected_index]))
    selected_lag = float(lags[selected_index])

    if 0 < selected_index < scores.size - 1:
        left = float(scores[selected_index - 1])
        center = float(scores[selected_index])
        right = float(scores[selected_index + 1])
        denominator = left - 2.0 * center + right
        if abs(denominator) > 1e-15:
            offset = 0.5 * (left - right) / denominator
            selected_lag += float(np.clip(offset, -0.5, 0.5))

    if selected_lag <= 0.0:
        return None, None, selected_score
    frequency = float(sample_rate / selected_lag)
    if not minimum_frequency_hz <= frequency <= maximum_frequency_hz:
        return None, selected_lag, selected_score
    return frequency, selected_lag, selected_score


def _classification(
    *,
    active_frame_count: int,
    voiced_frame_count: int,
    voiced_active_ratio: float,
    periodicity_score: float,
    pitch_spread_cents: float | None,
    confidence_threshold: float,
) -> tuple[PeriodicityClass, str]:
    if active_frame_count == 0:
        return PeriodicityClass.SILENT, "No frame exceeded the active RMS threshold."
    if voiced_frame_count == 0 or periodicity_score < confidence_threshold:
        return (
            PeriodicityClass.APERIODIC,
            "No sufficiently confident periodic lag was sustained across active frames.",
        )
    if voiced_active_ratio < 0.5:
        return (
            PeriodicityClass.INTERMITTENT_PERIODIC,
            "Confident periodicity was present in fewer than half of the active frames.",
        )
    if pitch_spread_cents is not None and pitch_spread_cents <= 15.0:
        return (
            PeriodicityClass.STABLE_PERIODIC,
            "Periodic frames have a robust pitch spread of at most 15 cents.",
        )
    if pitch_spread_cents is not None and pitch_spread_cents <= 120.0:
        return (
            PeriodicityClass.QUASI_PERIODIC,
            "Periodic frames remain coherent but vary by more than 15 and at most 120 cents.",
        )
    return (
        PeriodicityClass.UNSTABLE_PERIODIC,
        "Periodic frames were detected, but their robust pitch spread exceeds 120 cents.",
    )


def analyze_pitch_periodicity(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    frame_size: int = 4096,
    hop_size: int = 1024,
    minimum_frequency_hz: float = 40.0,
    maximum_frequency_hz: float = 2000.0,
    active_rms_threshold: float = 1e-6,
    confidence_threshold: float = 0.60,
    reference_a4_hz: float = 440.0,
) -> PitchPeriodicityAnalysis:
    data = validate_mono_samples(samples)
    if sample_rate <= 0:
        raise AnalysisError("sample_rate must be positive")
    if frame_size <= 0 or hop_size <= 0:
        raise AnalysisError("frame_size and hop_size must be positive")
    if not math.isfinite(minimum_frequency_hz) or minimum_frequency_hz <= 0.0:
        raise AnalysisError("minimum_frequency_hz must be finite and positive")
    if not math.isfinite(maximum_frequency_hz) or maximum_frequency_hz <= 0.0:
        raise AnalysisError("maximum_frequency_hz must be finite and positive")
    if minimum_frequency_hz >= maximum_frequency_hz:
        raise AnalysisError("minimum_frequency_hz must be below maximum_frequency_hz")
    nyquist = sample_rate / 2.0
    if maximum_frequency_hz >= nyquist:
        raise AnalysisError("maximum_frequency_hz must be below the Nyquist frequency")
    if not math.isfinite(active_rms_threshold) or active_rms_threshold < 0.0:
        raise AnalysisError("active_rms_threshold must be finite and non-negative")
    if not math.isfinite(confidence_threshold) or not 0.0 <= confidence_threshold <= 1.0:
        raise AnalysisError("confidence_threshold must be between 0 and 1")
    if not math.isfinite(reference_a4_hz) or reference_a4_hz <= 0.0:
        raise AnalysisError("reference_a4_hz must be finite and positive")

    frames: list[PitchFrameAnalysis] = []
    for start, frame in iter_frames(data, frame_size=frame_size, hop_size=hop_size):
        rms = float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)))
        active = rms > active_rms_threshold
        frequency: float | None = None
        lag: float | None = None
        score = 0.0
        if active:
            frequency, lag, score = _autocorrelation_pitch(
                frame,
                sample_rate,
                minimum_frequency_hz=minimum_frequency_hz,
                maximum_frequency_hz=maximum_frequency_hz,
            )
        voiced = frequency is not None and score >= confidence_threshold
        if not voiced:
            frequency = None
            lag = None
        frames.append(
            PitchFrameAnalysis(
                start_sample=int(start),
                center_seconds=float((start + (frame.size - 1) / 2.0) / sample_rate),
                sample_count=int(frame.size),
                rms=rms,
                active=active,
                period_lag_samples=lag,
                frequency_hz=frequency,
                periodicity_score=score,
                voiced=voiced,
            )
        )

    active_frames = [frame for frame in frames if frame.active]
    voiced_frames = [frame for frame in frames if frame.voiced]
    active_count = len(active_frames)
    voiced_count = len(voiced_frames)
    active_ratio = float(active_count / len(frames))
    voiced_frame_ratio = float(voiced_count / len(frames))
    voiced_active_ratio = 0.0 if active_count == 0 else float(voiced_count / active_count)

    frequency_hz: float | None = None
    midi_note: float | None = None
    nearest_note: int | None = None
    note_name: str | None = None
    cents_deviation: float | None = None
    pitch_spread_cents: float | None = None
    pitch_stability = 0.0
    periodicity_score = 0.0

    if voiced_frames:
        frequencies = np.asarray(
            [frame.frequency_hz for frame in voiced_frames], dtype=np.float64
        )
        scores = np.asarray(
            [frame.periodicity_score for frame in voiced_frames], dtype=np.float64
        )
        weights = np.maximum(scores, np.finfo(np.float64).eps)
        frequency_hz = _weighted_median(frequencies, weights)
        periodicity_score = _weighted_median(scores, weights)
        midi_note, nearest_note, note_name, cents_deviation = describe_frequency(
            frequency_hz,
            reference_a4_hz=reference_a4_hz,
        )
        frame_midi = 69.0 + 12.0 * np.log2(frequencies / reference_a4_hz)
        absolute_cents = np.abs(100.0 * (frame_midi - midi_note))
        pitch_spread_cents = _weighted_median(absolute_cents, weights)
        pitch_stability = float(1.0 / (1.0 + pitch_spread_cents / 50.0))

    periodicity_class, reason = _classification(
        active_frame_count=active_count,
        voiced_frame_count=voiced_count,
        voiced_active_ratio=voiced_active_ratio,
        periodicity_score=periodicity_score,
        pitch_spread_cents=pitch_spread_cents,
        confidence_threshold=confidence_threshold,
    )
    quasi_periodicity_score = float(
        periodicity_score * voiced_active_ratio * pitch_stability
    )

    return PitchPeriodicityAnalysis(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=_sample_sha256(data),
        frame_size=int(frame_size),
        hop_size=int(hop_size),
        minimum_frequency_hz=float(minimum_frequency_hz),
        maximum_frequency_hz=float(maximum_frequency_hz),
        active_rms_threshold=float(active_rms_threshold),
        confidence_threshold=float(confidence_threshold),
        reference_a4_hz=float(reference_a4_hz),
        frames=tuple(frames),
        active_frame_count=active_count,
        active_frame_ratio=active_ratio,
        voiced_frame_count=voiced_count,
        voiced_frame_ratio=voiced_frame_ratio,
        voiced_active_ratio=voiced_active_ratio,
        frequency_hz=frequency_hz,
        midi_note=midi_note,
        nearest_midi_note=nearest_note,
        note_name=note_name,
        cents_deviation=cents_deviation,
        periodicity_score=periodicity_score,
        pitch_spread_cents=pitch_spread_cents,
        pitch_stability=pitch_stability,
        quasi_periodicity_score=quasi_periodicity_score,
        periodicity_class=periodicity_class,
        classification_reason=reason,
    )


def analyze_audio_source_pitch_periodicity(
    source: AudioSource,
    **kwargs: float | int,
) -> PitchPeriodicityAnalysis:
    return analyze_pitch_periodicity(
        source.mono_samples,
        source.metadata.sample_rate,
        **kwargs,
    )
