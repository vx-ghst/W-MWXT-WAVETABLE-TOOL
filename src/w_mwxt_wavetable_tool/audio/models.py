from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt


FloatArray = npt.NDArray[np.float64]


class AudioContainerFormat(str, Enum):
    WAV = "wav"
    AIFF = "aiff"
    FLAC = "flac"


class MonoPolicy(str, Enum):
    AUTO = "auto"
    SUM = "sum"
    AVERAGE = "average"
    LEFT = "left"
    RIGHT = "right"
    MID = "mid"
    BEST_PERIODICITY = "best_periodicity"
    FIRST_CHANNEL = "first_channel"
    DOMINANT_CHANNEL = "dominant_channel"


class MonoStrategy(str, Enum):
    MONO_PASSTHROUGH = "mono_passthrough"
    IDENTICAL_CHANNELS = "identical_channels"
    SILENT_CHANNEL_REMOVED = "silent_channel_removed"
    ANTIPHASE_CHANNEL_SELECTED = "antiphase_channel_selected"
    SUM = "sum"
    AVERAGE = "average"
    LEFT = "left"
    RIGHT = "right"
    MID = "mid"
    BEST_PERIODICITY = "best_periodicity"
    AUTO_BEST_PERIODICITY = "auto_best_periodicity"
    FIRST_CHANNEL = "first_channel"
    DOMINANT_CHANNEL = "dominant_channel"


class InvalidSamplePolicy(str, Enum):
    REJECT = "reject"
    ZERO = "zero"


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    source_path: Path
    container: AudioContainerFormat
    libsndfile_format: str
    subtype: str
    endian: str
    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float
    source_bytes: int
    source_mtime_ns: int
    source_sha256: str
    source_extension: str
    extension_matches_container: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "container": self.container.value,
            "libsndfile_format": self.libsndfile_format,
            "subtype": self.subtype,
            "endian": self.endian,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "frames": self.frames,
            "duration_seconds": self.duration_seconds,
            "source_bytes": self.source_bytes,
            "source_mtime_ns": self.source_mtime_ns,
            "source_sha256": self.source_sha256,
            "source_extension": self.source_extension,
            "extension_matches_container": self.extension_matches_container,
        }


@dataclass(frozen=True, slots=True)
class AudioMeasurements:
    sample_count: int
    minimum: float
    maximum: float
    peak_absolute: float
    rms: float
    mean: float
    dc_offset: float
    is_silent: bool
    has_dc_offset: bool
    all_finite: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "peak_absolute": self.peak_absolute,
            "rms": self.rms,
            "mean": self.mean,
            "dc_offset": self.dc_offset,
            "is_silent": self.is_silent,
            "has_dc_offset": self.has_dc_offset,
            "all_finite": self.all_finite,
        }


@dataclass(frozen=True, slots=True)
class MonoConversionReport:
    policy: MonoPolicy
    strategy: MonoStrategy
    source_channels: int
    selected_channel: int | None
    channel_rms: tuple[float, ...]
    stereo_correlation: float | None
    reason: str
    selected_candidate: str | None = None
    candidate_periodicity_scores: tuple[tuple[str, float], ...] = ()
    periodicity_margin: float | None = None

    def __post_init__(self) -> None:
        if self.source_channels <= 0:
            raise ValueError("source_channels must be positive")
        if len(self.channel_rms) != self.source_channels:
            raise ValueError("channel_rms must contain one value per source channel")
        for index, value in enumerate(self.channel_rms):
            checked = float(value)
            if not np.isfinite(checked) or checked < 0.0:
                raise ValueError(f"channel_rms[{index}] must be finite and non-negative")
        if self.selected_channel is not None and not (
            0 <= self.selected_channel < self.source_channels
        ):
            raise ValueError("selected_channel is outside the source channel range")
        if self.stereo_correlation is not None:
            correlation = float(self.stereo_correlation)
            if not np.isfinite(correlation) or not -1.0 <= correlation <= 1.0:
                raise ValueError("stereo_correlation must be finite and between -1 and 1")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")
        candidate_names = tuple(name for name, _ in self.candidate_periodicity_scores)
        if len(set(candidate_names)) != len(candidate_names):
            raise ValueError("candidate periodicity score names must be unique")
        for name, value in self.candidate_periodicity_scores:
            if not name or name.strip() != name:
                raise ValueError("candidate periodicity score names must be normalized")
            score = float(value)
            if not np.isfinite(score) or not 0.0 <= score <= 1.0:
                raise ValueError("candidate periodicity scores must be finite ratios")
        if self.candidate_periodicity_scores:
            if self.selected_candidate not in candidate_names:
                raise ValueError("selected_candidate must name a scored candidate")
            if self.periodicity_margin is None:
                raise ValueError("scored mono selection requires periodicity_margin")
        elif self.selected_candidate is not None or self.periodicity_margin is not None:
            raise ValueError("unscored mono selection cannot expose periodicity metadata")
        if self.periodicity_margin is not None:
            margin = float(self.periodicity_margin)
            if not np.isfinite(margin) or not 0.0 <= margin <= 1.0:
                raise ValueError("periodicity_margin must be a finite ratio")

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.value,
            "strategy": self.strategy.value,
            "source_channels": self.source_channels,
            "selected_channel": self.selected_channel,
            "channel_rms": list(self.channel_rms),
            "stereo_correlation": self.stereo_correlation,
            "reason": self.reason,
            "selected_candidate": self.selected_candidate,
            "candidate_periodicity_scores": [
                {"name": name, "periodicity_score": score}
                for name, score in self.candidate_periodicity_scores
            ],
            "periodicity_margin": self.periodicity_margin,
        }


@dataclass(frozen=True, slots=True)
class AudioSource:
    metadata: AudioMetadata
    mono_samples: FloatArray
    measurements: AudioMeasurements
    mono_conversion: MonoConversionReport

    def __post_init__(self) -> None:
        samples = np.asarray(self.mono_samples, dtype=np.float64)
        if samples.ndim != 1:
            raise ValueError("AudioSource mono_samples must be one-dimensional")
        if samples.size != self.metadata.frames:
            raise ValueError(
                "AudioSource sample count does not match metadata frames: "
                f"{samples.size} != {self.metadata.frames}"
            )
        if not np.all(np.isfinite(samples)):
            raise ValueError("AudioSource mono_samples must contain finite values only")
        samples = np.ascontiguousarray(samples, dtype=np.float64).copy()
        samples.setflags(write=False)
        object.__setattr__(self, "mono_samples", samples)

    @property
    def sample_sha256(self) -> str:
        canonical = self.mono_samples.astype("<f8", copy=False).tobytes(order="C")
        return sha256(canonical).hexdigest()

    @property
    def state_sha256(self) -> str:
        payload = (
            f"{self.metadata.source_sha256}\n"
            f"{self.metadata.sample_rate}\n"
            f"{self.metadata.frames}\n"
            f"{self.mono_conversion.policy.value}\n"
            f"{self.mono_conversion.strategy.value}\n"
            f"{self.sample_sha256}\n"
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    def to_summary(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "mono_conversion": self.mono_conversion.to_dict(),
            "measurements": self.measurements.to_dict(),
            "sample_dtype": str(self.mono_samples.dtype),
            "sample_sha256": self.sample_sha256,
            "state_sha256": self.state_sha256,
        }
