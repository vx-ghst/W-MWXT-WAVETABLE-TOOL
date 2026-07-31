from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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

class PeriodicityClass(str, Enum):
    SILENT = "silent"
    APERIODIC = "aperiodic"
    INTERMITTENT_PERIODIC = "intermittent_periodic"
    STABLE_PERIODIC = "stable_periodic"
    QUASI_PERIODIC = "quasi_periodic"
    UNSTABLE_PERIODIC = "unstable_periodic"


@dataclass(frozen=True, slots=True)
class PitchFrameAnalysis:
    start_sample: int
    center_seconds: float
    sample_count: int
    rms: float
    active: bool
    period_lag_samples: float | None
    frequency_hz: float | None
    periodicity_score: float
    voiced: bool

    def __post_init__(self) -> None:
        if self.start_sample < 0:
            raise ValueError("start_sample must not be negative")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        center = _require_finite(self.center_seconds, name="center_seconds")
        if center < 0.0:
            raise ValueError("center_seconds must not be negative")
        rms = _require_finite(self.rms, name="rms")
        if rms < 0.0:
            raise ValueError("rms must not be negative")
        _require_ratio(self.periodicity_score, name="periodicity_score")
        lag = _optional_finite(self.period_lag_samples, name="period_lag_samples")
        frequency = _optional_finite(self.frequency_hz, name="frequency_hz")
        if lag is not None and lag <= 0.0:
            raise ValueError("period_lag_samples must be positive when defined")
        if frequency is not None and frequency <= 0.0:
            raise ValueError("frequency_hz must be positive when defined")
        if self.voiced and (lag is None or frequency is None or not self.active):
            raise ValueError("voiced frames require active samples, lag, and frequency")
        if not self.voiced and (lag is not None or frequency is not None):
            raise ValueError("unvoiced frames must not expose lag or frequency")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_sample": self.start_sample,
            "center_seconds": self.center_seconds,
            "sample_count": self.sample_count,
            "rms": self.rms,
            "active": self.active,
            "period_lag_samples": self.period_lag_samples,
            "frequency_hz": self.frequency_hz,
            "periodicity_score": self.periodicity_score,
            "voiced": self.voiced,
        }


@dataclass(frozen=True, slots=True)
class PitchPeriodicityAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    frame_size: int
    hop_size: int
    minimum_frequency_hz: float
    maximum_frequency_hz: float
    active_rms_threshold: float
    confidence_threshold: float
    reference_a4_hz: float
    frames: tuple[PitchFrameAnalysis, ...]
    active_frame_count: int
    active_frame_ratio: float
    voiced_frame_count: int
    voiced_frame_ratio: float
    voiced_active_ratio: float
    frequency_hz: float | None
    midi_note: float | None
    nearest_midi_note: int | None
    note_name: str | None
    cents_deviation: float | None
    periodicity_score: float
    pitch_spread_cents: float | None
    pitch_stability: float
    quasi_periodicity_score: float
    periodicity_class: PeriodicityClass
    classification_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported pitch-periodicity schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if len(self.sample_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sample_sha256
        ):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if self.frame_size <= 0 or self.hop_size <= 0:
            raise ValueError("frame_size and hop_size must be positive")
        minimum = _require_finite(
            self.minimum_frequency_hz, name="minimum_frequency_hz"
        )
        maximum = _require_finite(
            self.maximum_frequency_hz, name="maximum_frequency_hz"
        )
        if minimum <= 0.0 or maximum <= minimum:
            raise ValueError("frequency bounds are invalid")
        if maximum >= self.sample_rate / 2.0:
            raise ValueError("maximum_frequency_hz must be below Nyquist")
        active_threshold = _require_finite(
            self.active_rms_threshold, name="active_rms_threshold"
        )
        if active_threshold < 0.0:
            raise ValueError("active_rms_threshold must not be negative")
        _require_ratio(self.confidence_threshold, name="confidence_threshold")
        reference = _require_finite(self.reference_a4_hz, name="reference_a4_hz")
        if reference <= 0.0:
            raise ValueError("reference_a4_hz must be positive")
        if not self.frames:
            raise ValueError("frames must not be empty")
        starts = tuple(frame.start_sample for frame in self.frames)
        if tuple(sorted(starts)) != starts:
            raise ValueError("frame starts must be sorted")
        if any(start >= self.sample_count for start in starts):
            raise ValueError("frame start is outside the signal")
        if not 0 <= self.active_frame_count <= len(self.frames):
            raise ValueError("active_frame_count is outside the frame range")
        if not 0 <= self.voiced_frame_count <= self.active_frame_count:
            raise ValueError("voiced_frame_count is outside the active-frame range")
        if self.active_frame_count != sum(frame.active for frame in self.frames):
            raise ValueError("active_frame_count is inconsistent")
        if self.voiced_frame_count != sum(frame.voiced for frame in self.frames):
            raise ValueError("voiced_frame_count is inconsistent")
        for name in (
            "active_frame_ratio",
            "voiced_frame_ratio",
            "voiced_active_ratio",
            "periodicity_score",
            "pitch_stability",
            "quasi_periodicity_score",
        ):
            _require_ratio(getattr(self, name), name=name)
        optional_values = (
            (self.frequency_hz, "frequency_hz"),
            (self.midi_note, "midi_note"),
            (self.cents_deviation, "cents_deviation"),
            (self.pitch_spread_cents, "pitch_spread_cents"),
        )
        for value, name in optional_values:
            checked = _optional_finite(value, name=name)
            if name in {"frequency_hz", "pitch_spread_cents"} and checked is not None and checked < 0.0:
                raise ValueError(f"{name} must not be negative")
        pitch_fields = (
            self.frequency_hz,
            self.midi_note,
            self.nearest_midi_note,
            self.note_name,
            self.cents_deviation,
            self.pitch_spread_cents,
        )
        if self.voiced_frame_count == 0:
            if any(value is not None for value in pitch_fields):
                raise ValueError("unvoiced analysis must not expose pitch fields")
        else:
            if any(value is None for value in pitch_fields):
                raise ValueError("voiced analysis requires all pitch fields")
            if self.frequency_hz is not None and not (
                self.minimum_frequency_hz <= self.frequency_hz <= self.maximum_frequency_hz
            ):
                raise ValueError("frequency_hz is outside the configured range")
            if self.cents_deviation is not None and not -50.0 <= self.cents_deviation <= 50.0:
                raise ValueError("cents_deviation must be between -50 and 50")
            if not self.note_name:
                raise ValueError("note_name must not be empty")
        if not isinstance(self.periodicity_class, PeriodicityClass):
            raise ValueError("periodicity_class must be a PeriodicityClass")
        if not self.classification_reason:
            raise ValueError("classification_reason must not be empty")

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "frame_size": self.frame_size,
            "hop_size": self.hop_size,
            "minimum_frequency_hz": self.minimum_frequency_hz,
            "maximum_frequency_hz": self.maximum_frequency_hz,
            "active_rms_threshold": self.active_rms_threshold,
            "confidence_threshold": self.confidence_threshold,
            "reference_a4_hz": self.reference_a4_hz,
            "frame_count": self.frame_count,
            "frames": [frame.to_dict() for frame in self.frames],
            "active_frame_count": self.active_frame_count,
            "active_frame_ratio": self.active_frame_ratio,
            "voiced_frame_count": self.voiced_frame_count,
            "voiced_frame_ratio": self.voiced_frame_ratio,
            "voiced_active_ratio": self.voiced_active_ratio,
            "frequency_hz": self.frequency_hz,
            "midi_note": self.midi_note,
            "nearest_midi_note": self.nearest_midi_note,
            "note_name": self.note_name,
            "cents_deviation": self.cents_deviation,
            "periodicity_score": self.periodicity_score,
            "pitch_spread_cents": self.pitch_spread_cents,
            "pitch_stability": self.pitch_stability,
            "quasi_periodicity_score": self.quasi_periodicity_score,
            "periodicity_class": self.periodicity_class.value,
            "classification_reason": self.classification_reason,
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

class PhaseContinuityClass(str, Enum):
    UNAVAILABLE = "unavailable"
    STABLE = "stable"
    VARIABLE = "variable"
    DISCONTINUOUS = "discontinuous"


class PitchMotionClass(str, Enum):
    UNVOICED = "unvoiced"
    INSUFFICIENT = "insufficient"
    STABLE = "stable"
    GLIDE_UP = "glide_up"
    GLIDE_DOWN = "glide_down"
    VIBRATO = "vibrato"
    STEPPED = "stepped"
    IRREGULAR = "irregular"


@dataclass(frozen=True, slots=True)
class PhaseFrameAnalysis:
    frame_index: int
    start_sample: int
    center_seconds: float
    sample_count: int
    voiced: bool
    frequency_hz: float | None
    phase_radians: float | None
    projection_strength: float

    def __post_init__(self) -> None:
        if self.frame_index < 0 or self.start_sample < 0:
            raise ValueError("frame_index and start_sample must not be negative")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        center = _require_finite(self.center_seconds, name="center_seconds")
        if center < 0.0:
            raise ValueError("center_seconds must not be negative")
        frequency = _optional_finite(self.frequency_hz, name="frequency_hz")
        phase = _optional_finite(self.phase_radians, name="phase_radians")
        _require_ratio(self.projection_strength, name="projection_strength")
        if self.voiced:
            if frequency is None or phase is None:
                raise ValueError("voiced phase frames require frequency and phase")
            if frequency <= 0.0:
                raise ValueError("frequency_hz must be positive")
            if not -math.pi <= phase <= math.pi:
                raise ValueError("phase_radians must be wrapped to [-pi, pi]")
        elif frequency is not None or phase is not None:
            raise ValueError("unvoiced phase frames must not expose frequency or phase")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "start_sample": self.start_sample,
            "center_seconds": self.center_seconds,
            "sample_count": self.sample_count,
            "voiced": self.voiced,
            "frequency_hz": self.frequency_hz,
            "phase_radians": self.phase_radians,
            "projection_strength": self.projection_strength,
        }


@dataclass(frozen=True, slots=True)
class PhaseTransitionAnalysis:
    from_frame_index: int
    to_frame_index: int
    delta_seconds: float
    phase_error_radians: float
    phase_error_degrees: float
    discontinuity: bool

    def __post_init__(self) -> None:
        if self.from_frame_index < 0 or self.to_frame_index <= self.from_frame_index:
            raise ValueError("phase transition frame indexes are invalid")
        delta = _require_finite(self.delta_seconds, name="delta_seconds")
        if delta <= 0.0:
            raise ValueError("delta_seconds must be positive")
        radians = _require_finite(self.phase_error_radians, name="phase_error_radians")
        degrees = _require_finite(self.phase_error_degrees, name="phase_error_degrees")
        if not -math.pi <= radians <= math.pi:
            raise ValueError("phase_error_radians must be wrapped to [-pi, pi]")
        if not -180.0 <= degrees <= 180.0:
            raise ValueError("phase_error_degrees must be between -180 and 180")
        if not math.isclose(degrees, math.degrees(radians), abs_tol=1e-9):
            raise ValueError("phase error degree and radian values are inconsistent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_frame_index": self.from_frame_index,
            "to_frame_index": self.to_frame_index,
            "delta_seconds": self.delta_seconds,
            "phase_error_radians": self.phase_error_radians,
            "phase_error_degrees": self.phase_error_degrees,
            "discontinuity": self.discontinuity,
        }


@dataclass(frozen=True, slots=True)
class PhaseMotionAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    frame_size: int
    hop_size: int
    phase_discontinuity_threshold_degrees: float
    stable_pitch_threshold_cents: float
    glide_slope_threshold_cents_per_second: float
    stepped_pitch_threshold_cents: float
    frames: tuple[PhaseFrameAnalysis, ...]
    phase_transitions: tuple[PhaseTransitionAnalysis, ...]
    phase_frame_count: int
    phase_transition_count: int
    median_phase_error_degrees: float | None
    phase_error_p95_degrees: float | None
    maximum_phase_error_degrees: float | None
    phase_stability: float
    discontinuity_count: int
    discontinuity_ratio: float
    phase_continuity_class: PhaseContinuityClass
    phase_classification_reason: str
    pitch_transition_count: int
    pitch_excursion_cents: float | None
    median_pitch_step_cents: float | None
    maximum_pitch_step_cents: float | None
    pitch_slope_cents_per_second: float | None
    direction_consistency: float
    reversal_count: int
    reversal_rate: float
    pitch_motion_class: PitchMotionClass
    pitch_motion_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported phase-motion schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if len(self.sample_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sample_sha256
        ):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if self.frame_size <= 0 or self.hop_size <= 0:
            raise ValueError("frame_size and hop_size must be positive")
        for name in (
            "phase_discontinuity_threshold_degrees",
            "stable_pitch_threshold_cents",
            "glide_slope_threshold_cents_per_second",
            "stepped_pitch_threshold_cents",
        ):
            value = _require_finite(getattr(self, name), name=name)
            if value <= 0.0:
                raise ValueError(f"{name} must be positive")
        if not self.frames:
            raise ValueError("frames must not be empty")
        if tuple(frame.frame_index for frame in self.frames) != tuple(range(len(self.frames))):
            raise ValueError("phase frame indexes must be contiguous from zero")
        if tuple(sorted(frame.start_sample for frame in self.frames)) != tuple(
            frame.start_sample for frame in self.frames
        ):
            raise ValueError("phase frame starts must be sorted")
        if self.phase_frame_count != sum(frame.voiced for frame in self.frames):
            raise ValueError("phase_frame_count is inconsistent")
        if self.phase_transition_count != len(self.phase_transitions):
            raise ValueError("phase_transition_count is inconsistent")
        if not 0 <= self.discontinuity_count <= self.phase_transition_count:
            raise ValueError("discontinuity_count is outside the transition range")
        if self.discontinuity_count != sum(
            transition.discontinuity for transition in self.phase_transitions
        ):
            raise ValueError("discontinuity_count is inconsistent")
        _require_ratio(self.phase_stability, name="phase_stability")
        _require_ratio(self.discontinuity_ratio, name="discontinuity_ratio")
        _require_ratio(self.direction_consistency, name="direction_consistency")
        _require_ratio(self.reversal_rate, name="reversal_rate")
        for name in (
            "median_phase_error_degrees",
            "phase_error_p95_degrees",
            "maximum_phase_error_degrees",
            "pitch_excursion_cents",
            "median_pitch_step_cents",
            "maximum_pitch_step_cents",
        ):
            value = _optional_finite(getattr(self, name), name=name)
            if value is not None and value < 0.0:
                raise ValueError(f"{name} must not be negative")
        _optional_finite(
            self.pitch_slope_cents_per_second,
            name="pitch_slope_cents_per_second",
        )
        if self.pitch_transition_count < 0:
            raise ValueError("pitch_transition_count must not be negative")
        if self.reversal_count < 0:
            raise ValueError("reversal_count must not be negative")
        if not isinstance(self.phase_continuity_class, PhaseContinuityClass):
            raise ValueError("phase_continuity_class must be a PhaseContinuityClass")
        if not isinstance(self.pitch_motion_class, PitchMotionClass):
            raise ValueError("pitch_motion_class must be a PitchMotionClass")
        if not self.phase_classification_reason or not self.pitch_motion_reason:
            raise ValueError("classification reasons must not be empty")
        if self.phase_transition_count == 0:
            if any(
                value is not None
                for value in (
                    self.median_phase_error_degrees,
                    self.phase_error_p95_degrees,
                    self.maximum_phase_error_degrees,
                )
            ):
                raise ValueError("phase error aggregates require transitions")
        else:
            if any(
                value is None
                for value in (
                    self.median_phase_error_degrees,
                    self.phase_error_p95_degrees,
                    self.maximum_phase_error_degrees,
                )
            ):
                raise ValueError("phase transitions require phase error aggregates")

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "frame_size": self.frame_size,
            "hop_size": self.hop_size,
            "phase_discontinuity_threshold_degrees": self.phase_discontinuity_threshold_degrees,
            "stable_pitch_threshold_cents": self.stable_pitch_threshold_cents,
            "glide_slope_threshold_cents_per_second": self.glide_slope_threshold_cents_per_second,
            "stepped_pitch_threshold_cents": self.stepped_pitch_threshold_cents,
            "frame_count": self.frame_count,
            "frames": [frame.to_dict() for frame in self.frames],
            "phase_transitions": [
                transition.to_dict() for transition in self.phase_transitions
            ],
            "phase_frame_count": self.phase_frame_count,
            "phase_transition_count": self.phase_transition_count,
            "median_phase_error_degrees": self.median_phase_error_degrees,
            "phase_error_p95_degrees": self.phase_error_p95_degrees,
            "maximum_phase_error_degrees": self.maximum_phase_error_degrees,
            "phase_stability": self.phase_stability,
            "discontinuity_count": self.discontinuity_count,
            "discontinuity_ratio": self.discontinuity_ratio,
            "phase_continuity_class": self.phase_continuity_class.value,
            "phase_classification_reason": self.phase_classification_reason,
            "pitch_transition_count": self.pitch_transition_count,
            "pitch_excursion_cents": self.pitch_excursion_cents,
            "median_pitch_step_cents": self.median_pitch_step_cents,
            "maximum_pitch_step_cents": self.maximum_pitch_step_cents,
            "pitch_slope_cents_per_second": self.pitch_slope_cents_per_second,
            "direction_consistency": self.direction_consistency,
            "reversal_count": self.reversal_count,
            "reversal_rate": self.reversal_rate,
            "pitch_motion_class": self.pitch_motion_class.value,
            "pitch_motion_reason": self.pitch_motion_reason,
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


class NoiseClass(str, Enum):
    SILENT = "silent"
    PRISTINE = "pristine"
    SIGNAL_DOMINATED = "signal_dominated"
    MIXED = "mixed"
    NOISE_DOMINATED = "noise_dominated"


@dataclass(frozen=True, slots=True)
class NoiseFrameAnalysis:
    frame_index: int
    start_sample: int
    center_seconds: float
    sample_count: int
    rms: float
    residual_rms: float
    voiced_periodic: bool
    period_lag_samples: float | None
    candidate_method: str

    def __post_init__(self) -> None:
        if self.frame_index < 0 or self.start_sample < 0:
            raise ValueError("frame_index and start_sample must not be negative")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        center = _require_finite(self.center_seconds, name="center_seconds")
        if center < 0.0:
            raise ValueError("center_seconds must not be negative")
        for name in ("rms", "residual_rms"):
            value = _require_finite(getattr(self, name), name=name)
            if value < 0.0:
                raise ValueError(f"{name} must not be negative")
        lag = _optional_finite(self.period_lag_samples, name="period_lag_samples")
        if self.voiced_periodic:
            if lag is None or lag <= 0.0:
                raise ValueError("voiced periodic frames require a positive lag")
            if self.candidate_method != "periodic_residual":
                raise ValueError("voiced periodic frames require periodic_residual method")
        elif lag is not None:
            raise ValueError("non-periodic frames must not expose a period lag")
        if self.candidate_method not in {"periodic_residual", "frame_rms"}:
            raise ValueError("candidate_method is unsupported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "start_sample": self.start_sample,
            "center_seconds": self.center_seconds,
            "sample_count": self.sample_count,
            "rms": self.rms,
            "residual_rms": self.residual_rms,
            "voiced_periodic": self.voiced_periodic,
            "period_lag_samples": self.period_lag_samples,
            "candidate_method": self.candidate_method,
        }


@dataclass(frozen=True, slots=True)
class NoiseAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    frame_size: int
    hop_size: int
    lower_quantile: float
    silence_threshold: float
    minimum_noise_rms: float
    frames: tuple[NoiseFrameAnalysis, ...]
    signal_rms: float
    signal_rms_dbfs: float | None
    noise_floor_rms: float
    noise_floor_dbfs: float | None
    snr_db: float | None
    periodic_residual_frame_count: int
    lower_quantile_frame_count: int
    noise_stationarity: float
    noise_class: NoiseClass
    classification_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported noise-analysis schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if len(self.sample_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sample_sha256
        ):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if self.frame_size <= 0 or self.hop_size <= 0:
            raise ValueError("frame_size and hop_size must be positive")
        lower = _require_finite(self.lower_quantile, name="lower_quantile")
        if not 0.0 < lower <= 1.0:
            raise ValueError("lower_quantile must be in (0, 1]")
        for name in ("silence_threshold", "minimum_noise_rms"):
            value = _require_finite(getattr(self, name), name=name)
            if value < 0.0:
                raise ValueError(f"{name} must not be negative")
        if not self.frames:
            raise ValueError("noise frames must not be empty")
        if tuple(frame.frame_index for frame in self.frames) != tuple(range(len(self.frames))):
            raise ValueError("noise frame indexes must be contiguous from zero")
        if tuple(sorted(frame.start_sample for frame in self.frames)) != tuple(
            frame.start_sample for frame in self.frames
        ):
            raise ValueError("noise frame starts must be sorted")
        for name in ("signal_rms", "noise_floor_rms"):
            value = _require_finite(getattr(self, name), name=name)
            if value < 0.0:
                raise ValueError(f"{name} must not be negative")
        _optional_finite(self.signal_rms_dbfs, name="signal_rms_dbfs")
        _optional_finite(self.noise_floor_dbfs, name="noise_floor_dbfs")
        snr = _optional_finite(self.snr_db, name="snr_db")
        if snr is not None and snr < 0.0:
            raise ValueError("snr_db must not be negative")
        if not 0 <= self.periodic_residual_frame_count <= len(self.frames):
            raise ValueError("periodic_residual_frame_count is outside frame range")
        if self.periodic_residual_frame_count != sum(
            frame.voiced_periodic for frame in self.frames
        ):
            raise ValueError("periodic_residual_frame_count is inconsistent")
        if not 1 <= self.lower_quantile_frame_count <= len(self.frames):
            raise ValueError("lower_quantile_frame_count is outside frame range")
        _require_ratio(self.noise_stationarity, name="noise_stationarity")
        if not isinstance(self.noise_class, NoiseClass):
            raise ValueError("noise_class must be a NoiseClass")
        if not self.classification_reason:
            raise ValueError("classification_reason must not be empty")

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "frame_size": self.frame_size,
            "hop_size": self.hop_size,
            "lower_quantile": self.lower_quantile,
            "silence_threshold": self.silence_threshold,
            "minimum_noise_rms": self.minimum_noise_rms,
            "frame_count": self.frame_count,
            "frames": [frame.to_dict() for frame in self.frames],
            "signal_rms": self.signal_rms,
            "signal_rms_dbfs": self.signal_rms_dbfs,
            "noise_floor_rms": self.noise_floor_rms,
            "noise_floor_dbfs": self.noise_floor_dbfs,
            "snr_db": self.snr_db,
            "periodic_residual_frame_count": self.periodic_residual_frame_count,
            "lower_quantile_frame_count": self.lower_quantile_frame_count,
            "noise_stationarity": self.noise_stationarity,
            "noise_class": self.noise_class.value,
            "classification_reason": self.classification_reason,
        }

    @property
    def analysis_sha256(self) -> str:
        rendered = json.dumps(
            self._content_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return sha256(rendered).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


class TransientChangeClass(str, Enum):
    SILENT = "silent"
    STEADY = "steady"
    SPARSE_TRANSIENTS = "sparse_transients"
    TRANSIENT_RICH = "transient_rich"
    CHANGING = "changing"


@dataclass(frozen=True, slots=True)
class TransientFrameAnalysis:
    frame_index: int
    start_sample: int
    center_seconds: float
    sample_count: int
    rms: float
    rms_dbfs: float | None
    energy_change_db: float
    spectral_flux: float
    onset_strength: float

    def __post_init__(self) -> None:
        if self.frame_index < 0 or self.start_sample < 0:
            raise ValueError("frame_index and start_sample must not be negative")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        center = _require_finite(self.center_seconds, name="center_seconds")
        if center < 0.0:
            raise ValueError("center_seconds must not be negative")
        rms = _require_finite(self.rms, name="rms")
        if rms < 0.0:
            raise ValueError("rms must not be negative")
        _optional_finite(self.rms_dbfs, name="rms_dbfs")
        _require_finite(self.energy_change_db, name="energy_change_db")
        flux = _require_finite(self.spectral_flux, name="spectral_flux")
        onset = _require_finite(self.onset_strength, name="onset_strength")
        if flux < 0.0 or onset < 0.0:
            raise ValueError("spectral_flux and onset_strength must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "start_sample": self.start_sample,
            "center_seconds": self.center_seconds,
            "sample_count": self.sample_count,
            "rms": self.rms,
            "rms_dbfs": self.rms_dbfs,
            "energy_change_db": self.energy_change_db,
            "spectral_flux": self.spectral_flux,
            "onset_strength": self.onset_strength,
        }


@dataclass(frozen=True, slots=True)
class TransientEvent:
    frame_index: int
    sample_index: int
    time_seconds: float
    strength: float
    energy_change_db: float
    spectral_flux: float

    def __post_init__(self) -> None:
        if self.frame_index < 0 or self.sample_index < 0:
            raise ValueError("transient indexes must not be negative")
        time = _require_finite(self.time_seconds, name="time_seconds")
        if time < 0.0:
            raise ValueError("time_seconds must not be negative")
        for name in ("strength", "spectral_flux"):
            value = _require_finite(getattr(self, name), name=name)
            if value < 0.0:
                raise ValueError(f"{name} must not be negative")
        _require_finite(self.energy_change_db, name="energy_change_db")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "sample_index": self.sample_index,
            "time_seconds": self.time_seconds,
            "strength": self.strength,
            "energy_change_db": self.energy_change_db,
            "spectral_flux": self.spectral_flux,
        }


@dataclass(frozen=True, slots=True)
class ChangePointEvent:
    frame_index: int
    sample_index: int
    time_seconds: float
    score: float
    energy_change_db: float
    spectral_flux: float
    kind: str

    def __post_init__(self) -> None:
        if self.frame_index < 0 or self.sample_index < 0:
            raise ValueError("change-point indexes must not be negative")
        time = _require_finite(self.time_seconds, name="time_seconds")
        if time < 0.0:
            raise ValueError("time_seconds must not be negative")
        score = _require_finite(self.score, name="score")
        flux = _require_finite(self.spectral_flux, name="spectral_flux")
        if score < 0.0 or flux < 0.0:
            raise ValueError("score and spectral_flux must not be negative")
        _require_finite(self.energy_change_db, name="energy_change_db")
        if self.kind not in {"energy", "spectral", "energy_and_spectral"}:
            raise ValueError("change-point kind is unsupported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "sample_index": self.sample_index,
            "time_seconds": self.time_seconds,
            "score": self.score,
            "energy_change_db": self.energy_change_db,
            "spectral_flux": self.spectral_flux,
            "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class TransientChangeAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    frame_size: int
    hop_size: int
    sensitivity: float
    minimum_onset_strength: float
    change_energy_threshold_db: float
    change_spectral_flux_threshold: float
    minimum_event_separation_ms: float
    frames: tuple[TransientFrameAnalysis, ...]
    adaptive_onset_threshold: float
    transients: tuple[TransientEvent, ...]
    change_points: tuple[ChangePointEvent, ...]
    transient_count: int
    change_point_count: int
    transient_density_per_second: float
    median_transient_interval_seconds: float | None
    maximum_onset_strength: float
    change_ratio: float
    transient_change_class: TransientChangeClass
    classification_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported transient-change schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if len(self.sample_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sample_sha256
        ):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if self.frame_size <= 0 or self.hop_size <= 0:
            raise ValueError("frame_size and hop_size must be positive")
        for name in (
            "sensitivity",
            "minimum_onset_strength",
            "change_energy_threshold_db",
            "change_spectral_flux_threshold",
            "minimum_event_separation_ms",
        ):
            value = _require_finite(getattr(self, name), name=name)
            if value < 0.0:
                raise ValueError(f"{name} must not be negative")
        if self.sensitivity <= 0.0 or self.change_energy_threshold_db <= 0.0:
            raise ValueError("sensitivity and change_energy_threshold_db must be positive")
        if self.change_spectral_flux_threshold > 1.0:
            raise ValueError("change_spectral_flux_threshold must not exceed one")
        if not self.frames:
            raise ValueError("transient frames must not be empty")
        if tuple(frame.frame_index for frame in self.frames) != tuple(range(len(self.frames))):
            raise ValueError("transient frame indexes must be contiguous from zero")
        if self.transient_count != len(self.transients):
            raise ValueError("transient_count is inconsistent")
        if self.change_point_count != len(self.change_points):
            raise ValueError("change_point_count is inconsistent")
        for name in (
            "adaptive_onset_threshold",
            "transient_density_per_second",
            "maximum_onset_strength",
        ):
            value = _require_finite(getattr(self, name), name=name)
            if value < 0.0:
                raise ValueError(f"{name} must not be negative")
        interval = _optional_finite(
            self.median_transient_interval_seconds,
            name="median_transient_interval_seconds",
        )
        if interval is not None and interval <= 0.0:
            raise ValueError("median_transient_interval_seconds must be positive")
        _require_ratio(self.change_ratio, name="change_ratio")
        if not isinstance(self.transient_change_class, TransientChangeClass):
            raise ValueError("transient_change_class must be a TransientChangeClass")
        if not self.classification_reason:
            raise ValueError("classification_reason must not be empty")

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "frame_size": self.frame_size,
            "hop_size": self.hop_size,
            "sensitivity": self.sensitivity,
            "minimum_onset_strength": self.minimum_onset_strength,
            "change_energy_threshold_db": self.change_energy_threshold_db,
            "change_spectral_flux_threshold": self.change_spectral_flux_threshold,
            "minimum_event_separation_ms": self.minimum_event_separation_ms,
            "frame_count": self.frame_count,
            "frames": [frame.to_dict() for frame in self.frames],
            "adaptive_onset_threshold": self.adaptive_onset_threshold,
            "transients": [event.to_dict() for event in self.transients],
            "change_points": [event.to_dict() for event in self.change_points],
            "transient_count": self.transient_count,
            "change_point_count": self.change_point_count,
            "transient_density_per_second": self.transient_density_per_second,
            "median_transient_interval_seconds": self.median_transient_interval_seconds,
            "maximum_onset_strength": self.maximum_onset_strength,
            "change_ratio": self.change_ratio,
            "transient_change_class": self.transient_change_class.value,
            "classification_reason": self.classification_reason,
        }

    @property
    def analysis_sha256(self) -> str:
        rendered = json.dumps(
            self._content_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return sha256(rendered).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result
