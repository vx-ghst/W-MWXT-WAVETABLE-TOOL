from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from .measurements import channel_rms, stereo_correlation
from .models import MonoConversionReport, MonoPolicy, MonoStrategy
from .mono_scoring import score_mono_candidates, select_best_candidate
from ..errors import InvalidAudioDataError


def convert_to_mono(
    samples: npt.NDArray[np.float64],
    *,
    policy: MonoPolicy | str = MonoPolicy.AUTO,
    sample_rate: int | None = None,
    silence_threshold: float = 1e-12,
    identical_tolerance: float = 1e-12,
    antiphase_threshold: float = -0.95,
    auto_periodicity_threshold: float = 0.60,
    auto_periodicity_margin: float = 0.08,
) -> tuple[npt.NDArray[np.float64], MonoConversionReport]:
    try:
        selected_policy = MonoPolicy(policy)
    except ValueError as exc:
        raise InvalidAudioDataError(f"Unknown mono policy: {policy!r}") from exc

    for name, value in (
        ("silence_threshold", silence_threshold),
        ("identical_tolerance", identical_tolerance),
        ("auto_periodicity_threshold", auto_periodicity_threshold),
        ("auto_periodicity_margin", auto_periodicity_margin),
    ):
        if not math.isfinite(value) or value < 0.0:
            raise InvalidAudioDataError(f"{name} must be finite and non-negative")
    if not math.isfinite(antiphase_threshold) or not -1.0 <= antiphase_threshold <= 1.0:
        raise InvalidAudioDataError("antiphase_threshold must be between -1 and 1")
    if auto_periodicity_threshold > 1.0 or auto_periodicity_margin > 1.0:
        raise InvalidAudioDataError(
            "auto periodicity threshold and margin must not exceed one"
        )
    if sample_rate is not None and sample_rate <= 0:
        raise InvalidAudioDataError("sample_rate must be positive when provided")

    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 2 or data.shape[0] == 0 or data.shape[1] == 0:
        raise InvalidAudioDataError(
            "Mono conversion expects a non-empty frames-by-channels array"
        )
    if not bool(np.all(np.isfinite(data))):
        raise InvalidAudioDataError("Mono conversion requires finite samples")

    rms_values = channel_rms(data)
    correlation = stereo_correlation(data)
    channels = data.shape[1]

    if channels == 1:
        mono = data[:, 0].copy()
        report = MonoConversionReport(
            policy=selected_policy,
            strategy=MonoStrategy.MONO_PASSTHROUGH,
            source_channels=1,
            selected_channel=0,
            channel_rms=rms_values,
            stereo_correlation=None,
            reason="The source is already mono.",
        )
        return mono, report

    if selected_policy is MonoPolicy.FIRST_CHANNEL:
        return _selected_channel(
            data,
            selected_policy,
            MonoStrategy.FIRST_CHANNEL,
            0,
            rms_values,
            correlation,
            "Explicit first-channel compatibility policy.",
        )

    if selected_policy is MonoPolicy.LEFT:
        return _selected_channel(
            data,
            selected_policy,
            MonoStrategy.LEFT,
            0,
            rms_values,
            correlation,
            "Explicit left-channel policy.",
        )

    if selected_policy is MonoPolicy.RIGHT:
        if channels < 2:
            raise InvalidAudioDataError("Right-channel policy requires at least two channels")
        return _selected_channel(
            data,
            selected_policy,
            MonoStrategy.RIGHT,
            1,
            rms_values,
            correlation,
            "Explicit right-channel policy.",
        )

    dominant = int(np.argmax(np.asarray(rms_values, dtype=np.float64)))
    if selected_policy is MonoPolicy.DOMINANT_CHANNEL:
        return _selected_channel(
            data,
            selected_policy,
            MonoStrategy.DOMINANT_CHANNEL,
            dominant,
            rms_values,
            correlation,
            "Explicit dominant-channel policy selected the channel with the highest RMS.",
        )

    if selected_policy is MonoPolicy.SUM:
        return _sum(
            data,
            selected_policy,
            rms_values,
            correlation,
            "Explicit arithmetic-sum policy; no level normalization was applied.",
        )

    if selected_policy is MonoPolicy.AVERAGE:
        return _average(
            data,
            selected_policy,
            rms_values,
            correlation,
            "Explicit arithmetic-average policy.",
        )

    if selected_policy is MonoPolicy.MID:
        if channels != 2:
            raise InvalidAudioDataError("Mid policy requires exactly two channels")
        return _mid(
            data,
            selected_policy,
            rms_values,
            correlation,
            "Explicit stereo Mid policy, computed as (left + right) / 2.",
        )

    if selected_policy is MonoPolicy.BEST_PERIODICITY:
        if sample_rate is None:
            raise InvalidAudioDataError(
                "Best-periodicity policy requires an explicit sample_rate"
            )
        return _best_periodicity(
            data,
            selected_policy,
            sample_rate,
            rms_values,
            correlation,
            MonoStrategy.BEST_PERIODICITY,
            "Explicit best-periodicity policy",
        )

    # AUTO policy preserves the established safety gates before optional scoring.
    max_rms = max(rms_values)
    active_threshold = max(silence_threshold, max_rms * 1e-9)
    active_channels = [
        index for index, value in enumerate(rms_values) if value > active_threshold
    ]

    if len(active_channels) == 1:
        selected = active_channels[0]
        return _selected_channel(
            data,
            selected_policy,
            MonoStrategy.SILENT_CHANNEL_REMOVED,
            selected,
            rms_values,
            correlation,
            "Only one channel contains non-silent material.",
        )

    reference = data[:, 0]
    if all(
        np.max(np.abs(data[:, index] - reference)) <= identical_tolerance
        for index in range(1, channels)
    ):
        return _average(
            data,
            selected_policy,
            rms_values,
            correlation,
            "All channels are identical within the configured tolerance.",
            strategy=MonoStrategy.IDENTICAL_CHANNELS,
        )

    if channels == 2 and correlation is not None and correlation <= antiphase_threshold:
        lower = min(rms_values)
        upper = max(rms_values)
        comparable_levels = upper == 0.0 or lower / upper >= 0.5
        if comparable_levels:
            return _selected_channel(
                data,
                selected_policy,
                MonoStrategy.ANTIPHASE_CHANNEL_SELECTED,
                dominant,
                rms_values,
                correlation,
                "Strong anti-phase correlation would cause destructive averaging; "
                "the higher-RMS channel was selected deterministically.",
            )

    if sample_rate is not None:
        best_result = _best_periodicity(
            data,
            selected_policy,
            sample_rate,
            rms_values,
            correlation,
            MonoStrategy.AUTO_BEST_PERIODICITY,
            "Automatic periodicity comparison",
            minimum_score=auto_periodicity_threshold,
            minimum_margin=auto_periodicity_margin,
            allow_fallback=True,
        )
        if best_result is not None:
            return best_result

    return _average(
        data,
        selected_policy,
        rms_values,
        correlation,
        "General multichannel source converted by arithmetic average.",
    )


def _candidate_arrays(
    data: npt.NDArray[np.float64],
) -> tuple[tuple[str, npt.NDArray[np.float64]], ...]:
    candidates: list[tuple[str, npt.NDArray[np.float64]]] = []
    for index in range(data.shape[1]):
        candidates.append((f"channel_{index}", data[:, index]))
    if data.shape[1] == 2:
        candidates.append(("mid", np.mean(data[:, :2], axis=1, dtype=np.float64)))
    else:
        candidates.append(("average", np.mean(data, axis=1, dtype=np.float64)))
    return tuple(candidates)


def _best_periodicity(
    data: npt.NDArray[np.float64],
    policy: MonoPolicy,
    sample_rate: int,
    rms_values: tuple[float, ...],
    correlation: float | None,
    strategy: MonoStrategy,
    reason_prefix: str,
    *,
    minimum_score: float = 0.0,
    minimum_margin: float = 0.0,
    allow_fallback: bool = False,
) -> tuple[npt.NDArray[np.float64], MonoConversionReport] | None:
    candidates = _candidate_arrays(data)
    scores = score_mono_candidates(candidates, sample_rate)
    best, margin = select_best_candidate(scores)
    if allow_fallback and (
        best.periodicity_score < minimum_score or margin < minimum_margin
    ):
        return None

    candidate_map = {name: samples for name, samples in candidates}
    mono = np.ascontiguousarray(candidate_map[best.name], dtype=np.float64).copy()
    selected_channel: int | None = None
    if best.name.startswith("channel_"):
        selected_channel = int(best.name.split("_", 1)[1])
    rendered_scores = ", ".join(
        f"{item.name}={item.periodicity_score:.6f}" for item in scores
    )
    reason = (
        f"{reason_prefix} selected {best.name} with periodicity "
        f"{best.periodicity_score:.6f} and margin {margin:.6f}; "
        f"candidates: {rendered_scores}."
    )
    return mono, MonoConversionReport(
        policy=policy,
        strategy=strategy,
        source_channels=data.shape[1],
        selected_channel=selected_channel,
        channel_rms=rms_values,
        stereo_correlation=correlation,
        reason=reason,
        selected_candidate=best.name,
        candidate_periodicity_scores=tuple(
            (item.name, item.periodicity_score) for item in scores
        ),
        periodicity_margin=margin,
    )


def _selected_channel(
    data: npt.NDArray[np.float64],
    policy: MonoPolicy,
    strategy: MonoStrategy,
    selected: int,
    rms_values: tuple[float, ...],
    correlation: float | None,
    reason: str,
) -> tuple[npt.NDArray[np.float64], MonoConversionReport]:
    mono = np.ascontiguousarray(data[:, selected], dtype=np.float64).copy()
    report = MonoConversionReport(
        policy=policy,
        strategy=strategy,
        source_channels=data.shape[1],
        selected_channel=selected,
        channel_rms=rms_values,
        stereo_correlation=correlation,
        reason=reason,
    )
    return mono, report


def _sum(
    data: npt.NDArray[np.float64],
    policy: MonoPolicy,
    rms_values: tuple[float, ...],
    correlation: float | None,
    reason: str,
) -> tuple[npt.NDArray[np.float64], MonoConversionReport]:
    mono = np.sum(data, axis=1, dtype=np.float64)
    mono = np.ascontiguousarray(mono, dtype=np.float64)
    report = MonoConversionReport(
        policy=policy,
        strategy=MonoStrategy.SUM,
        source_channels=data.shape[1],
        selected_channel=None,
        channel_rms=rms_values,
        stereo_correlation=correlation,
        reason=reason,
    )
    return mono, report


def _mid(
    data: npt.NDArray[np.float64],
    policy: MonoPolicy,
    rms_values: tuple[float, ...],
    correlation: float | None,
    reason: str,
) -> tuple[npt.NDArray[np.float64], MonoConversionReport]:
    mono = np.mean(data[:, :2], axis=1, dtype=np.float64)
    mono = np.ascontiguousarray(mono, dtype=np.float64)
    report = MonoConversionReport(
        policy=policy,
        strategy=MonoStrategy.MID,
        source_channels=data.shape[1],
        selected_channel=None,
        channel_rms=rms_values,
        stereo_correlation=correlation,
        reason=reason,
    )
    return mono, report


def _average(
    data: npt.NDArray[np.float64],
    policy: MonoPolicy,
    rms_values: tuple[float, ...],
    correlation: float | None,
    reason: str,
    *,
    strategy: MonoStrategy = MonoStrategy.AVERAGE,
) -> tuple[npt.NDArray[np.float64], MonoConversionReport]:
    mono = np.mean(data, axis=1, dtype=np.float64)
    mono = np.ascontiguousarray(mono, dtype=np.float64)
    report = MonoConversionReport(
        policy=policy,
        strategy=strategy,
        source_channels=data.shape[1],
        selected_channel=None,
        channel_rms=rms_values,
        stereo_correlation=correlation,
        reason=reason,
    )
    return mono, report
