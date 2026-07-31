from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .measurements import channel_rms, stereo_correlation
from .models import MonoConversionReport, MonoPolicy, MonoStrategy
from ..errors import InvalidAudioDataError


def convert_to_mono(
    samples: npt.NDArray[np.float64],
    *,
    policy: MonoPolicy | str = MonoPolicy.AUTO,
    silence_threshold: float = 1e-12,
    identical_tolerance: float = 1e-12,
    antiphase_threshold: float = -0.95,
) -> tuple[npt.NDArray[np.float64], MonoConversionReport]:
    try:
        selected_policy = MonoPolicy(policy)
    except ValueError as exc:
        raise InvalidAudioDataError(f"Unknown mono policy: {policy!r}") from exc

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
            "Explicit first-channel policy.",
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

    if selected_policy is MonoPolicy.AVERAGE:
        return _average(
            data,
            selected_policy,
            rms_values,
            correlation,
            "Explicit arithmetic-average policy.",
        )

    # AUTO policy.
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

    return _average(
        data,
        selected_policy,
        rms_values,
        correlation,
        "General multichannel source converted by arithmetic average.",
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
