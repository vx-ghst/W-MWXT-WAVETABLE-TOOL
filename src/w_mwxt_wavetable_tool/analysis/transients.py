
from __future__ import annotations

from hashlib import sha256
import math

import numpy as np
import numpy.typing as npt

from .framing import iter_frames, validate_mono_samples
from .models import (
    ChangePointEvent,
    TransientChangeAnalysis,
    TransientChangeClass,
    TransientEvent,
    TransientFrameAnalysis,
)
from ..audio import AudioSource
from ..errors import AnalysisError


def _sample_sha256(samples: npt.NDArray[np.float64]) -> str:
    canonical = samples.astype("<f8", copy=False).tobytes(order="C")
    return sha256(canonical).hexdigest()


def _dbfs(value: float) -> float | None:
    if value <= 0.0:
        return None
    return float(20.0 * math.log10(value))


def _normalized_spectrum(frame: np.ndarray) -> np.ndarray:
    if frame.size == 1:
        return np.zeros(1, dtype=np.float64)
    centered = frame - float(np.mean(frame, dtype=np.float64))
    window = np.hanning(frame.size)
    magnitude = np.abs(np.fft.rfft(centered * window))
    total = float(np.sum(magnitude, dtype=np.float64))
    if total <= 1e-24:
        return np.zeros_like(magnitude, dtype=np.float64)
    return np.asarray(magnitude / total, dtype=np.float64)


def _median(values: np.ndarray) -> float:
    ordered = np.sort(np.asarray(values, dtype=np.float64), kind="stable")
    count = ordered.size
    middle = count // 2
    if count % 2:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2.0)


def _select_separated(candidates: list[int], strengths: np.ndarray, minimum_frames: int) -> list[int]:
    if not candidates:
        return []
    ranked = sorted(candidates, key=lambda index: (-float(strengths[index]), index))
    selected: list[int] = []
    for index in ranked:
        if all(abs(index - existing) >= minimum_frames for existing in selected):
            selected.append(index)
    return sorted(selected)


def _classification(
    *,
    signal_peak: float,
    silence_threshold: float,
    transient_count: int,
    transient_density: float,
    change_ratio: float,
) -> tuple[TransientChangeClass, str]:
    if signal_peak <= silence_threshold:
        return TransientChangeClass.SILENT, "The complete signal is below the configured silence threshold."
    if change_ratio >= 0.10:
        return TransientChangeClass.CHANGING, "At least ten percent of frame transitions exceed a change threshold."
    if transient_count == 0:
        return TransientChangeClass.STEADY, "No adaptive onset peak exceeded the configured threshold."
    if transient_density >= 4.0:
        return TransientChangeClass.TRANSIENT_RICH, "The detected transient density is at least four events per second."
    return TransientChangeClass.SPARSE_TRANSIENTS, "One or more isolated transient events were detected."


def analyze_transients(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    frame_size: int = 1024,
    hop_size: int = 256,
    sensitivity: float = 6.0,
    minimum_onset_strength: float = 1.0,
    change_energy_threshold_db: float = 6.0,
    change_spectral_flux_threshold: float = 0.35,
    minimum_event_separation_ms: float = 20.0,
    silence_threshold: float = 1e-12,
    rms_floor: float = 1e-12,
) -> TransientChangeAnalysis:
    data = validate_mono_samples(samples)
    if sample_rate <= 0:
        raise AnalysisError("sample_rate must be positive")
    if frame_size <= 0 or hop_size <= 0:
        raise AnalysisError("frame_size and hop_size must be positive")
    numeric_parameters = {
        "sensitivity": sensitivity,
        "minimum_onset_strength": minimum_onset_strength,
        "change_energy_threshold_db": change_energy_threshold_db,
        "change_spectral_flux_threshold": change_spectral_flux_threshold,
        "minimum_event_separation_ms": minimum_event_separation_ms,
        "silence_threshold": silence_threshold,
        "rms_floor": rms_floor,
    }
    if any(not math.isfinite(float(value)) for value in numeric_parameters.values()):
        raise AnalysisError("transient-analysis parameters must be finite")
    if sensitivity <= 0.0:
        raise AnalysisError("sensitivity must be positive")
    if minimum_onset_strength < 0.0 or minimum_event_separation_ms < 0.0:
        raise AnalysisError("onset and separation thresholds must not be negative")
    if change_energy_threshold_db <= 0.0:
        raise AnalysisError("change_energy_threshold_db must be positive")
    if not 0.0 <= change_spectral_flux_threshold <= 1.0:
        raise AnalysisError("change_spectral_flux_threshold must be between zero and one")
    if silence_threshold < 0.0 or rms_floor <= 0.0:
        raise AnalysisError("silence_threshold must not be negative and rms_floor must be positive")

    framed = iter_frames(data, frame_size=frame_size, hop_size=hop_size)
    starts: list[int] = []
    centers: list[float] = []
    rms_values: list[float] = []
    spectra: list[np.ndarray] = []
    for start, frame in framed:
        starts.append(start)
        centers.append(float((start + (frame.size - 1) / 2.0) / sample_rate))
        rms_values.append(float(np.sqrt(np.mean(np.square(frame), dtype=np.float64))))
        spectra.append(_normalized_spectrum(frame))

    rms_array = np.asarray(rms_values, dtype=np.float64)
    db_array = 20.0 * np.log10(np.maximum(rms_array, rms_floor))
    energy_changes = np.zeros(rms_array.size, dtype=np.float64)
    fluxes = np.zeros(rms_array.size, dtype=np.float64)
    onset = np.zeros(rms_array.size, dtype=np.float64)
    for index in range(1, rms_array.size):
        energy_changes[index] = float(db_array[index] - db_array[index - 1])
        previous = spectra[index - 1]
        current = spectra[index]
        common = min(previous.size, current.size)
        positive = np.maximum(0.0, current[:common] - previous[:common])
        fluxes[index] = float(min(1.0, np.sum(positive, dtype=np.float64)))
        onset[index] = float(
            max(0.0, energy_changes[index]) / change_energy_threshold_db
            + fluxes[index] / max(change_spectral_flux_threshold, 1e-12)
        )

    median_onset = _median(onset)
    mad = _median(np.abs(onset - median_onset))
    adaptive_threshold = float(max(minimum_onset_strength, median_onset + sensitivity * 1.4826 * mad))

    local_candidates: list[int] = []
    for index in range(1, onset.size):
        left = onset[index - 1]
        right = onset[index + 1] if index + 1 < onset.size else -1.0
        if onset[index] >= adaptive_threshold and onset[index] > left and onset[index] >= right:
            local_candidates.append(index)
    minimum_frames = max(1, int(math.ceil((minimum_event_separation_ms / 1000.0) * sample_rate / hop_size)))
    selected = _select_separated(local_candidates, onset, minimum_frames)

    transient_events = tuple(
        TransientEvent(
            frame_index=index,
            sample_index=min(data.size - 1, int(round(centers[index] * sample_rate))),
            time_seconds=centers[index],
            strength=float(onset[index]),
            energy_change_db=float(energy_changes[index]),
            spectral_flux=float(fluxes[index]),
        )
        for index in selected
    )

    change_events: list[ChangePointEvent] = []
    for index in range(1, onset.size):
        energy_hit = abs(float(energy_changes[index])) >= change_energy_threshold_db
        spectral_hit = float(fluxes[index]) >= change_spectral_flux_threshold
        if not energy_hit and not spectral_hit:
            continue
        kind = "energy_and_spectral" if energy_hit and spectral_hit else ("energy" if energy_hit else "spectral")
        score = float(
            abs(energy_changes[index]) / change_energy_threshold_db
            + fluxes[index] / max(change_spectral_flux_threshold, 1e-12)
        )
        change_events.append(
            ChangePointEvent(
                frame_index=index,
                sample_index=min(data.size - 1, int(round(centers[index] * sample_rate))),
                time_seconds=centers[index],
                score=score,
                energy_change_db=float(energy_changes[index]),
                spectral_flux=float(fluxes[index]),
                kind=kind,
            )
        )

    frame_models = tuple(
        TransientFrameAnalysis(
            frame_index=index,
            start_sample=starts[index],
            center_seconds=centers[index],
            sample_count=min(frame_size, data.size - starts[index]),
            rms=float(rms_array[index]),
            rms_dbfs=_dbfs(float(rms_array[index])),
            energy_change_db=float(energy_changes[index]),
            spectral_flux=float(fluxes[index]),
            onset_strength=float(onset[index]),
        )
        for index in range(rms_array.size)
    )

    duration = float(data.size / sample_rate)
    density = float(len(transient_events) / duration)
    if len(transient_events) < 2:
        median_interval = None
    else:
        intervals = np.diff(np.asarray([event.time_seconds for event in transient_events], dtype=np.float64))
        median_interval = _median(intervals)
    change_ratio = float(len(change_events) / max(1, rms_array.size - 1))
    transient_class, reason = _classification(
        signal_peak=float(np.max(np.abs(data))),
        silence_threshold=silence_threshold,
        transient_count=len(transient_events),
        transient_density=density,
        change_ratio=change_ratio,
    )
    return TransientChangeAnalysis(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=_sample_sha256(data),
        frame_size=int(frame_size),
        hop_size=int(hop_size),
        sensitivity=float(sensitivity),
        minimum_onset_strength=float(minimum_onset_strength),
        change_energy_threshold_db=float(change_energy_threshold_db),
        change_spectral_flux_threshold=float(change_spectral_flux_threshold),
        minimum_event_separation_ms=float(minimum_event_separation_ms),
        frames=frame_models,
        adaptive_onset_threshold=adaptive_threshold,
        transients=transient_events,
        change_points=tuple(change_events),
        transient_count=len(transient_events),
        change_point_count=len(change_events),
        transient_density_per_second=density,
        median_transient_interval_seconds=median_interval,
        maximum_onset_strength=float(np.max(onset)),
        change_ratio=change_ratio,
        transient_change_class=transient_class,
        classification_reason=reason,
    )


def analyze_audio_source_transients(source: AudioSource, **kwargs: float | int) -> TransientChangeAnalysis:
    return analyze_transients(source.mono_samples, source.metadata.sample_rate, **kwargs)
