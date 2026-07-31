from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any
import json
import math


def _require_finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _optional_finite(value: float | None, *, name: str) -> float | None:
    if value is None:
        return None
    return _require_finite(value, name=name)


def _require_ratio(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


@dataclass(frozen=True, slots=True)
class LevelAnalysis:
    sample_count: int
    minimum: float
    maximum: float
    positive_peak: float
    negative_peak: float
    peak_absolute: float
    peak_dbfs: float | None
    rms: float
    rms_dbfs: float | None
    crest_factor: float | None
    crest_factor_db: float | None
    mean: float
    dc_offset: float
    is_silent: bool
    has_dc_offset: bool
    clipping_threshold: float
    clipped_sample_count: int
    clipped_sample_ratio: float
    is_clipped: bool
    near_clip_threshold: float
    near_clip_sample_count: int
    near_clip_sample_ratio: float
    flat_extreme_sample_count: int
    flat_extreme_sample_ratio: float
    saturation_likelihood: float
    saturation_probable: bool
    saturation_reason: str
    peak_asymmetry: float

    def __post_init__(self) -> None:
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        for name in (
            "minimum",
            "maximum",
            "positive_peak",
            "negative_peak",
            "peak_absolute",
            "rms",
            "mean",
            "dc_offset",
            "clipping_threshold",
            "near_clip_threshold",
            "peak_asymmetry",
        ):
            _require_finite(getattr(self, name), name=name)
        _optional_finite(self.peak_dbfs, name="peak_dbfs")
        _optional_finite(self.rms_dbfs, name="rms_dbfs")
        _optional_finite(self.crest_factor, name="crest_factor")
        _optional_finite(self.crest_factor_db, name="crest_factor_db")
        for name in (
            "clipped_sample_ratio",
            "near_clip_sample_ratio",
            "flat_extreme_sample_ratio",
            "saturation_likelihood",
        ):
            _require_ratio(getattr(self, name), name=name)
        for name in (
            "clipped_sample_count",
            "near_clip_sample_count",
            "flat_extreme_sample_count",
        ):
            value = getattr(self, name)
            if value < 0 or value > self.sample_count:
                raise ValueError(f"{name} is outside the sample-count range")
        if self.clipping_threshold <= 0.0:
            raise ValueError("clipping_threshold must be positive")
        if not 0.0 < self.near_clip_threshold <= self.clipping_threshold:
            raise ValueError(
                "near_clip_threshold must be positive and not exceed clipping_threshold"
            )
        if not -1.0 <= self.peak_asymmetry <= 1.0:
            raise ValueError("peak_asymmetry must be between -1 and 1")
        if not self.saturation_reason:
            raise ValueError("saturation_reason must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "positive_peak": self.positive_peak,
            "negative_peak": self.negative_peak,
            "peak_absolute": self.peak_absolute,
            "peak_dbfs": self.peak_dbfs,
            "rms": self.rms,
            "rms_dbfs": self.rms_dbfs,
            "crest_factor": self.crest_factor,
            "crest_factor_db": self.crest_factor_db,
            "mean": self.mean,
            "dc_offset": self.dc_offset,
            "is_silent": self.is_silent,
            "has_dc_offset": self.has_dc_offset,
            "clipping_threshold": self.clipping_threshold,
            "clipped_sample_count": self.clipped_sample_count,
            "clipped_sample_ratio": self.clipped_sample_ratio,
            "is_clipped": self.is_clipped,
            "near_clip_threshold": self.near_clip_threshold,
            "near_clip_sample_count": self.near_clip_sample_count,
            "near_clip_sample_ratio": self.near_clip_sample_ratio,
            "flat_extreme_sample_count": self.flat_extreme_sample_count,
            "flat_extreme_sample_ratio": self.flat_extreme_sample_ratio,
            "saturation_likelihood": self.saturation_likelihood,
            "saturation_probable": self.saturation_probable,
            "saturation_reason": self.saturation_reason,
            "peak_asymmetry": self.peak_asymmetry,
        }


@dataclass(frozen=True, slots=True)
class EnvelopeAnalysis:
    sample_rate: int
    sample_count: int
    frame_size: int
    hop_size: int
    frame_starts: tuple[int, ...]
    frame_center_seconds: tuple[float, ...]
    frame_rms: tuple[float, ...]
    frame_peak: tuple[float, ...]
    mean_rms: float
    standard_deviation_rms: float
    coefficient_of_variation: float | None
    amplitude_stability: float
    minimum_frame_rms: float
    maximum_frame_rms: float
    active_frame_count: int
    active_frame_ratio: float
    envelope_dynamic_range_db: float | None

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if self.frame_size <= 0 or self.hop_size <= 0:
            raise ValueError("frame_size and hop_size must be positive")
        lengths = {
            len(self.frame_starts),
            len(self.frame_center_seconds),
            len(self.frame_rms),
            len(self.frame_peak),
        }
        if len(lengths) != 1 or not self.frame_starts:
            raise ValueError("envelope frame fields must have one equal non-zero length")
        if any(start < 0 or start >= self.sample_count for start in self.frame_starts):
            raise ValueError("frame_starts contain an invalid sample index")
        if tuple(sorted(self.frame_starts)) != self.frame_starts:
            raise ValueError("frame_starts must be sorted")
        for index, value in enumerate(self.frame_center_seconds):
            _require_finite(value, name=f"frame_center_seconds[{index}]")
            if value < 0.0:
                raise ValueError("frame center time must not be negative")
        for field_name in ("frame_rms", "frame_peak"):
            for index, value in enumerate(getattr(self, field_name)):
                _require_finite(value, name=f"{field_name}[{index}]")
                if value < 0.0:
                    raise ValueError(f"{field_name} values must not be negative")
        for name in (
            "mean_rms",
            "standard_deviation_rms",
            "minimum_frame_rms",
            "maximum_frame_rms",
        ):
            value = _require_finite(getattr(self, name), name=name)
            if value < 0.0:
                raise ValueError(f"{name} must not be negative")
        coefficient = _optional_finite(
            self.coefficient_of_variation, name="coefficient_of_variation"
        )
        if coefficient is not None and coefficient < 0.0:
            raise ValueError("coefficient_of_variation must not be negative")
        _require_ratio(self.amplitude_stability, name="amplitude_stability")
        _require_ratio(self.active_frame_ratio, name="active_frame_ratio")
        dynamic_range = _optional_finite(
            self.envelope_dynamic_range_db, name="envelope_dynamic_range_db"
        )
        if dynamic_range is not None and dynamic_range < 0.0:
            raise ValueError("envelope_dynamic_range_db must not be negative")
        if not 0 <= self.active_frame_count <= len(self.frame_starts):
            raise ValueError("active_frame_count is outside the frame-count range")

    @property
    def frame_count(self) -> int:
        return len(self.frame_starts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "frame_size": self.frame_size,
            "hop_size": self.hop_size,
            "frame_count": self.frame_count,
            "frame_starts": list(self.frame_starts),
            "frame_center_seconds": list(self.frame_center_seconds),
            "frame_rms": list(self.frame_rms),
            "frame_peak": list(self.frame_peak),
            "mean_rms": self.mean_rms,
            "standard_deviation_rms": self.standard_deviation_rms,
            "coefficient_of_variation": self.coefficient_of_variation,
            "amplitude_stability": self.amplitude_stability,
            "minimum_frame_rms": self.minimum_frame_rms,
            "maximum_frame_rms": self.maximum_frame_rms,
            "active_frame_count": self.active_frame_count,
            "active_frame_ratio": self.active_frame_ratio,
            "envelope_dynamic_range_db": self.envelope_dynamic_range_db,
        }


@dataclass(frozen=True, slots=True)
class TimeDomainAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    levels: LevelAnalysis
    envelope: EnvelopeAnalysis

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported time-domain analysis schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if len(self.sample_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sample_sha256
        ):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if self.levels.sample_count != self.sample_count:
            raise ValueError("level-analysis sample count is inconsistent")
        if self.envelope.sample_count != self.sample_count:
            raise ValueError("envelope-analysis sample count is inconsistent")
        if self.envelope.sample_rate != self.sample_rate:
            raise ValueError("envelope-analysis sample rate is inconsistent")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "levels": self.levels.to_dict(),
            "envelope": self.envelope.to_dict(),
        }

    @property
    def analysis_sha256(self) -> str:
        rendered = json.dumps(
            self._content_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(rendered).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result
