from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import numpy.typing as npt

from ..errors import InvalidAudioDataError


@dataclass(frozen=True, slots=True)
class MonoCandidateScore:
    name: str
    periodicity_score: float
    rms: float
    peak_absolute: float

    def __post_init__(self) -> None:
        if not self.name or self.name.strip() != self.name:
            raise ValueError("name must be a non-empty normalized string")
        for field_name in ("periodicity_score", "rms", "peak_absolute"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")
            if value < 0.0:
                raise ValueError(f"{field_name} must not be negative")
        if self.periodicity_score > 1.0:
            raise ValueError("periodicity_score must not exceed one")

    def to_dict(self) -> dict[str, float | str]:
        return {
            "name": self.name,
            "periodicity_score": self.periodicity_score,
            "rms": self.rms,
            "peak_absolute": self.peak_absolute,
        }


def periodicity_score(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    minimum_frequency_hz: float = 35.0,
    maximum_frequency_hz: float = 2500.0,
    maximum_samples: int = 65536,
) -> float:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 1 or data.size == 0:
        raise InvalidAudioDataError("Periodicity scoring expects non-empty mono samples")
    if not bool(np.all(np.isfinite(data))):
        raise InvalidAudioDataError("Periodicity scoring requires finite samples")
    if sample_rate <= 0:
        raise InvalidAudioDataError("sample_rate must be positive")
    if not math.isfinite(minimum_frequency_hz) or minimum_frequency_hz <= 0.0:
        raise InvalidAudioDataError("minimum_frequency_hz must be finite and positive")
    if not math.isfinite(maximum_frequency_hz) or maximum_frequency_hz <= minimum_frequency_hz:
        raise InvalidAudioDataError(
            "maximum_frequency_hz must be finite and above minimum_frequency_hz"
        )
    nyquist = sample_rate / 2.0
    if minimum_frequency_hz >= nyquist:
        raise InvalidAudioDataError(
            "minimum_frequency_hz must be below Nyquist"
        )
    if maximum_frequency_hz >= nyquist:
        maximum_frequency_hz = math.nextafter(nyquist, 0.0)
    if maximum_samples <= 0:
        raise InvalidAudioDataError("maximum_samples must be positive")

    if data.size > maximum_samples:
        start = (data.size - maximum_samples) // 2
        data = data[start : start + maximum_samples]

    centered = data - float(np.mean(data, dtype=np.float64))
    energy = float(np.dot(centered, centered))
    if energy <= 1e-24:
        return 0.0

    minimum_lag = max(1, int(math.floor(sample_rate / maximum_frequency_hz)))
    maximum_lag = min(
        centered.size - 2,
        int(math.ceil(sample_rate / minimum_frequency_hz)),
    )
    if maximum_lag < minimum_lag:
        return 0.0

    fft_size = 1 << (2 * int(centered.size) - 1).bit_length()
    spectrum = np.fft.rfft(centered, n=fft_size)
    autocorrelation = np.fft.irfft(
        spectrum * np.conjugate(spectrum),
        n=fft_size,
    )[: centered.size]
    zero_lag = float(autocorrelation[0])
    if zero_lag <= 0.0:
        return 0.0

    lags = np.arange(minimum_lag, maximum_lag + 1, dtype=np.int64)
    overlap = centered.size / (centered.size - lags)
    scores = np.asarray(
        autocorrelation[lags] / zero_lag * overlap,
        dtype=np.float64,
    )
    scores = np.clip(scores, 0.0, 1.0)
    if scores.size == 0:
        return 0.0

    if scores.size >= 3:
        local = np.zeros(scores.size, dtype=bool)
        local[1:-1] = (scores[1:-1] > scores[:-2]) & (scores[1:-1] >= scores[2:])
        local_scores = scores[local]
        best = float(np.max(local_scores)) if local_scores.size else float(np.max(scores))
    else:
        best = float(np.max(scores))

    rms = float(np.sqrt(np.mean(np.square(data), dtype=np.float64)))
    activity = float(min(1.0, rms / 1e-4))
    return float(min(1.0, max(0.0, best * activity)))


def score_mono_candidates(
    candidates: tuple[tuple[str, npt.NDArray[np.float64]], ...],
    sample_rate: int,
) -> tuple[MonoCandidateScore, ...]:
    if not candidates:
        raise InvalidAudioDataError("At least one mono candidate is required")
    names = tuple(name for name, _ in candidates)
    if any(not name or name.strip() != name for name in names):
        raise InvalidAudioDataError("Mono candidate names must be normalized")
    if len(set(names)) != len(names):
        raise InvalidAudioDataError("Mono candidate names must be unique")
    result: list[MonoCandidateScore] = []
    for name, samples in candidates:
        data = np.asarray(samples, dtype=np.float64)
        if data.ndim != 1 or data.size == 0:
            raise InvalidAudioDataError(f"Mono candidate {name!r} is invalid")
        rms = float(np.sqrt(np.mean(np.square(data), dtype=np.float64)))
        peak = float(np.max(np.abs(data)))
        result.append(
            MonoCandidateScore(
                name=name,
                periodicity_score=periodicity_score(data, sample_rate),
                rms=rms,
                peak_absolute=peak,
            )
        )
    return tuple(result)


def select_best_candidate(
    scores: tuple[MonoCandidateScore, ...],
) -> tuple[MonoCandidateScore, float]:
    if not scores:
        raise InvalidAudioDataError("At least one mono candidate score is required")
    ranked = sorted(
        enumerate(scores),
        key=lambda item: (
            -item[1].periodicity_score,
            -item[1].rms,
            item[0],
        ),
    )
    best = ranked[0][1]
    second_score = ranked[1][1].periodicity_score if len(ranked) > 1 else 0.0
    margin = float(max(0.0, best.periodicity_score - second_score))
    return best, margin
