from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence
import wave

import numpy as np
import numpy.typing as npt

from ..errors import AnalysisError
from ..version import __version__
from .projection import (
    SOURCE_SAMPLE_COUNT,
    STORED_SAMPLE_COUNT,
    XT_SAMPLE_MAX,
    XT_SAMPLE_MIN,
    reconstruct_xt_native,
)

TRAJECTORY_QC_SCHEMA_VERSION = 1
DEFAULT_STEM = "CODE_V7_D_XT_TRAJECTORY_QC"
DEFAULT_SWEEP_FILE_NAME = "CODE_V7_D_XT_TRAJECTORY_SWEEP.wav"
DEFAULT_STEPPED_FILE_NAME = "CODE_V7_D_XT_TRAJECTORY_STEPPED.wav"
DEFAULT_BASELINE_SWEEP_FILE_NAME = "CODE_V7_D_XT_PRESERVE_PHASE_BASELINE_SWEEP.wav"
_EPSILON = 1.0e-12


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


def _require_hash(value: str, *, name: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise AnalysisError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _require_finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise AnalysisError(f"{name} must be finite")
    return result


def _require_non_negative(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if result < 0.0:
        raise AnalysisError(f"{name} must not be negative")
    return result


def _require_positive(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if result <= 0.0:
        raise AnalysisError(f"{name} must be positive")
    return result


def _require_ratio(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise AnalysisError(f"{name} must be between 0 and 1")
    return result


def _round_half_away_from_zero(values: npt.NDArray[np.float64]) -> npt.NDArray[np.int64]:
    magnitudes = np.floor(np.abs(values) + 0.5)
    return np.asarray(np.copysign(magnitudes, values), dtype=np.int64)


def _validated_stored(values: Sequence[int], *, name: str) -> tuple[int, ...]:
    result = tuple(int(value) for value in values)
    if len(result) != STORED_SAMPLE_COUNT:
        raise AnalysisError(f"{name} must contain exactly {STORED_SAMPLE_COUNT} values")
    if any(value < XT_SAMPLE_MIN or value > XT_SAMPLE_MAX for value in result):
        raise AnalysisError(f"{name} must stay in [{XT_SAMPLE_MIN}, {XT_SAMPLE_MAX}]")
    if -128 in result:
        raise AnalysisError(f"{name} contains forbidden -128")
    return result


def _normalized_spectrum(stored: Sequence[int]) -> npt.NDArray[np.float64]:
    reconstructed = np.asarray(reconstruct_xt_native(stored), dtype=np.float64) / XT_SAMPLE_MAX
    magnitudes = np.abs(np.fft.rfft(reconstructed))[1:]
    norm = float(np.linalg.norm(magnitudes))
    if norm <= _EPSILON:
        return np.zeros_like(magnitudes, dtype=np.float64)
    return np.asarray(magnitudes / norm, dtype=np.float64)


def _time_distance(left: Sequence[int], right: Sequence[int]) -> float:
    left_array = np.asarray(left, dtype=np.float64) / XT_SAMPLE_MAX
    right_array = np.asarray(right, dtype=np.float64) / XT_SAMPLE_MAX
    rmse = float(np.sqrt(np.mean(np.square(left_array - right_array), dtype=np.float64)))
    return float(np.clip(rmse / 2.0, 0.0, 1.0))


def _spectral_distance(left: Sequence[int], right: Sequence[int]) -> float:
    left_spectrum = _normalized_spectrum(left)
    right_spectrum = _normalized_spectrum(right)
    denominator = float(np.linalg.norm(left_spectrum) * np.linalg.norm(right_spectrum))
    if denominator <= _EPSILON:
        return 0.0 if np.allclose(left_spectrum, right_spectrum, atol=1.0e-12, rtol=0.0) else 1.0
    similarity = float(np.clip(np.dot(left_spectrum, right_spectrum) / denominator, 0.0, 1.0))
    return 1.0 - similarity


def _combined_distance(
    left: Sequence[int],
    right: Sequence[int],
    *,
    time_weight: float,
    spectral_weight: float,
) -> tuple[float, float, float]:
    time = _time_distance(left, right)
    spectral = _spectral_distance(left, right)
    combined = time_weight * time + spectral_weight * spectral
    return time, spectral, float(combined)


def _time_curvature(left: Sequence[int], center: Sequence[int], right: Sequence[int]) -> float:
    left_array = np.asarray(left, dtype=np.float64) / XT_SAMPLE_MAX
    center_array = np.asarray(center, dtype=np.float64) / XT_SAMPLE_MAX
    right_array = np.asarray(right, dtype=np.float64) / XT_SAMPLE_MAX
    second_difference = right_array - 2.0 * center_array + left_array
    rmse = float(np.sqrt(np.mean(np.square(second_difference), dtype=np.float64)))
    return float(np.clip(rmse / 4.0, 0.0, 1.0))


def _spectral_curvature(left: Sequence[int], center: Sequence[int], right: Sequence[int]) -> float:
    left_spectrum = _normalized_spectrum(left)
    center_spectrum = _normalized_spectrum(center)
    right_spectrum = _normalized_spectrum(right)
    reference = 0.5 * (left_spectrum + right_spectrum)
    norm = float(np.linalg.norm(reference))
    if norm > _EPSILON:
        reference = reference / norm
    difference = center_spectrum - reference
    return float(np.clip(np.sqrt(np.mean(np.square(difference), dtype=np.float64)), 0.0, 1.0))


def _robust_threshold(
    values: Sequence[float],
    *,
    absolute_minimum: float,
    median_multiplier: float,
    mad_multiplier: float,
) -> tuple[float, float, float]:
    array = np.asarray(tuple(float(value) for value in values), dtype=np.float64)
    if array.size == 0:
        raise AnalysisError("Cannot calculate a robust threshold from an empty sequence")
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))
    robust_sigma = 1.4826 * mad
    threshold = max(
        absolute_minimum,
        median * median_multiplier,
        median + mad_multiplier * robust_sigma,
    )
    return float(threshold), median, mad


def _interpolate_stored(left: Sequence[int], right: Sequence[int], alpha: float) -> tuple[int, ...]:
    blend = _require_ratio(alpha, name="blend_fraction")
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    quantized = _round_half_away_from_zero((1.0 - blend) * left_array + blend * right_array)
    quantized = np.clip(quantized, XT_SAMPLE_MIN, XT_SAMPLE_MAX)
    return tuple(int(value) for value in quantized)


def _validated_hashed_document(document: Mapping[str, Any], *, expected_schema_name: str) -> str:
    recorded = str(document.get("analysis_sha256", ""))
    _require_hash(recorded, name=f"{expected_schema_name}.analysis_sha256")
    content = dict(document)
    del content["analysis_sha256"]
    calculated = _canonical_sha256(content)
    if calculated != recorded:
        raise AnalysisError(
            f"{expected_schema_name} analysis_sha256 mismatch: "
            f"recorded={recorded}, calculated={calculated}"
        )
    return recorded


def _read_json(path: str | Path) -> Mapping[str, Any]:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Unable to read JSON document {source}: {exc}") from exc
    if not isinstance(document, Mapping):
        raise AnalysisError(f"JSON document {source} must contain an object at its root")
    return document


def _slot_anchor_numbers(document: Mapping[str, Any]) -> set[int]:
    values = document.get("anchor_slot_numbers")
    if not isinstance(values, list):
        raise AnalysisError("trajectory anchor_slot_numbers must be a list")
    return {int(value) for value in values}


def _validate_trajectory_document(document: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    analysis_hash = _validated_hashed_document(document, expected_schema_name="trajectory")
    if int(document.get("schema_version", 0)) != 1:
        raise AnalysisError("CODE V7-D requires CODE V7-C trajectory schema version 1")
    slots = document.get("slots")
    anchors = document.get("anchors")
    if not isinstance(slots, list) or len(slots) != 61:
        raise AnalysisError("CODE V7-D requires exactly 61 trajectory slots")
    if not isinstance(anchors, list) or len(anchors) < 2:
        raise AnalysisError("trajectory anchors must contain at least two entries")
    if int(document.get("slot_count", 0)) != len(slots):
        raise AnalysisError("trajectory slot_count is inconsistent")
    if int(document.get("anchor_count", 0)) != len(anchors):
        raise AnalysisError("trajectory anchor_count is inconsistent")
    if document.get("duplicate_adjacent_slot_pairs") not in ([], tuple()):
        raise AnalysisError("CODE V7-D requires a trajectory without adjacent duplicate slots")
    boundaries = document.get("boundaries")
    if not isinstance(boundaries, Mapping) or boundaries.get("generates_sysex") is not False:
        raise AnalysisError("trajectory boundary must explicitly disable SysEx generation")

    anchor_slot_numbers = _slot_anchor_numbers(document)
    if len(anchor_slot_numbers) != len(anchors):
        raise AnalysisError("trajectory anchor slot count is inconsistent")

    previous_stored: tuple[int, ...] | None = None
    for expected_number, slot in enumerate(slots, start=1):
        if not isinstance(slot, Mapping):
            raise AnalysisError("trajectory slots must be JSON objects")
        if int(slot.get("slot_number", 0)) != expected_number:
            raise AnalysisError("trajectory slot numbers must be contiguous from 1 to 61")
        stored = _validated_stored(slot.get("stored_samples", ()), name=f"slot {expected_number} stored_samples")
        reconstructed = tuple(int(value) for value in slot.get("reconstructed_samples", ()))
        if reconstructed != reconstruct_xt_native(stored):
            raise AnalysisError(f"slot {expected_number} reverse-negate reconstruction is invalid")
        kind = str(slot.get("kind", ""))
        if expected_number in anchor_slot_numbers and kind != "anchor":
            raise AnalysisError(f"slot {expected_number} must be an anchor")
        if expected_number not in anchor_slot_numbers and kind != "interpolated":
            raise AnalysisError(f"slot {expected_number} must be interpolated")
        if previous_stored == stored:
            raise AnalysisError(f"adjacent slots {expected_number - 1} and {expected_number} are identical")
        previous_stored = stored

    for expected_index, anchor in enumerate(anchors):
        if not isinstance(anchor, Mapping):
            raise AnalysisError("trajectory anchors must be JSON objects")
        if int(anchor.get("anchor_index", -1)) != expected_index:
            raise AnalysisError("trajectory anchor indexes must be contiguous from zero")
        if int(anchor.get("source_wave_index", -1)) != expected_index:
            raise AnalysisError("trajectory source wave order must be preserved")
        _validated_stored(anchor.get("stored_samples", ()), name=f"anchor {expected_index} stored_samples")
    return analysis_hash, slots, anchors


def _validate_projection_document(
    document: Mapping[str, Any],
    *,
    expected_hash: str,
    expected_wave_count: int,
) -> list[Mapping[str, Any]]:
    analysis_hash = _validated_hashed_document(document, expected_schema_name="projection")
    if analysis_hash != expected_hash:
        raise AnalysisError(
            "projection report does not match trajectory source_projection_set_sha256"
        )
    if int(document.get("schema_version", 0)) != 1:
        raise AnalysisError("CODE V7-D requires CODE V7-B projection schema version 1")
    waves = document.get("waves")
    if not isinstance(waves, list) or len(waves) != expected_wave_count:
        raise AnalysisError("projection wave count does not match trajectory anchor count")
    for expected_index, projected in enumerate(waves):
        if not isinstance(projected, Mapping):
            raise AnalysisError("projection waves must be JSON objects")
        if int(projected.get("index", -1)) != expected_index:
            raise AnalysisError("projection wave indexes must be contiguous from zero")
        _validated_stored(
            projected.get("stored_samples", ()),
            name=f"projection wave {expected_index} stored_samples",
        )
    return waves


class XtTrajectoryQcStatus(str, Enum):
    PASS = "pass"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class XtTrajectoryQcConfig:
    time_weight: float = 0.70
    spectral_weight: float = 0.30
    jump_absolute_minimum: float = 0.020
    jump_median_multiplier: float = 2.50
    jump_mad_multiplier: float = 6.00
    curvature_absolute_minimum: float = 0.015
    curvature_median_multiplier: float = 3.00
    curvature_mad_multiplier: float = 6.00
    sample_rate: int = 48_000
    preview_frequency_hz: float = 110.0
    sweep_duration_seconds: float = 12.0
    stepped_slot_duration_seconds: float = 0.10
    transition_fraction: float = 0.20
    fade_duration_seconds: float = 0.02
    preview_peak: float = 0.80

    def __post_init__(self) -> None:
        weights = (
            _require_non_negative(self.time_weight, name="time_weight"),
            _require_non_negative(self.spectral_weight, name="spectral_weight"),
        )
        if not math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise AnalysisError("time_weight and spectral_weight must sum exactly to 1.0")
        for name in (
            "jump_absolute_minimum",
            "jump_median_multiplier",
            "jump_mad_multiplier",
            "curvature_absolute_minimum",
            "curvature_median_multiplier",
            "curvature_mad_multiplier",
        ):
            _require_non_negative(getattr(self, name), name=name)
        if self.sample_rate < 8_000 or self.sample_rate > 384_000:
            raise AnalysisError("sample_rate must be between 8000 and 384000")
        _require_positive(self.preview_frequency_hz, name="preview_frequency_hz")
        if self.preview_frequency_hz >= self.sample_rate / 4.0:
            raise AnalysisError("preview_frequency_hz is too high for the selected sample rate")
        _require_positive(self.sweep_duration_seconds, name="sweep_duration_seconds")
        _require_positive(
            self.stepped_slot_duration_seconds,
            name="stepped_slot_duration_seconds",
        )
        _require_ratio(self.transition_fraction, name="transition_fraction")
        _require_non_negative(self.fade_duration_seconds, name="fade_duration_seconds")
        peak = _require_positive(self.preview_peak, name="preview_peak")
        if peak > 1.0:
            raise AnalysisError("preview_peak must not exceed 1.0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_weight": self.time_weight,
            "spectral_weight": self.spectral_weight,
            "jump_absolute_minimum": self.jump_absolute_minimum,
            "jump_median_multiplier": self.jump_median_multiplier,
            "jump_mad_multiplier": self.jump_mad_multiplier,
            "curvature_absolute_minimum": self.curvature_absolute_minimum,
            "curvature_median_multiplier": self.curvature_median_multiplier,
            "curvature_mad_multiplier": self.curvature_mad_multiplier,
            "sample_rate": self.sample_rate,
            "preview_frequency_hz": self.preview_frequency_hz,
            "sweep_duration_seconds": self.sweep_duration_seconds,
            "stepped_slot_duration_seconds": self.stepped_slot_duration_seconds,
            "transition_fraction": self.transition_fraction,
            "fade_duration_seconds": self.fade_duration_seconds,
            "preview_peak": self.preview_peak,
        }


@dataclass(frozen=True, slots=True)
class XtAdjacentSlotAudit:
    pair_index: int
    left_slot_number: int
    right_slot_number: int
    time_distance: float
    spectral_distance: float
    combined_distance: float
    touches_anchor: bool
    touches_phase_changed_anchor: bool
    flagged_jump: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_index": self.pair_index,
            "left_slot_number": self.left_slot_number,
            "right_slot_number": self.right_slot_number,
            "time_distance": self.time_distance,
            "spectral_distance": self.spectral_distance,
            "combined_distance": self.combined_distance,
            "touches_anchor": self.touches_anchor,
            "touches_phase_changed_anchor": self.touches_phase_changed_anchor,
            "flagged_jump": self.flagged_jump,
        }


@dataclass(frozen=True, slots=True)
class XtCurvatureAudit:
    center_slot_number: int
    time_curvature: float
    spectral_curvature: float
    combined_curvature: float
    touches_anchor: bool
    touches_phase_changed_anchor: bool
    flagged_curvature: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "center_slot_number": self.center_slot_number,
            "time_curvature": self.time_curvature,
            "spectral_curvature": self.spectral_curvature,
            "combined_curvature": self.combined_curvature,
            "touches_anchor": self.touches_anchor,
            "touches_phase_changed_anchor": self.touches_phase_changed_anchor,
            "flagged_curvature": self.flagged_curvature,
        }


@dataclass(frozen=True, slots=True)
class XtPhaseNeighborhoodAudit:
    anchor_index: int
    source_wave_index: int
    slot_number: int
    original_phase_rotation_samples: int
    selected_phase_rotation_samples: int
    circular_shift_samples: int
    objective_increase: float
    local_maximum_combined_distance: float
    local_mean_combined_distance: float
    flagged_neighbor_pair_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_index": self.anchor_index,
            "source_wave_index": self.source_wave_index,
            "slot_number": self.slot_number,
            "original_phase_rotation_samples": self.original_phase_rotation_samples,
            "selected_phase_rotation_samples": self.selected_phase_rotation_samples,
            "circular_shift_samples": self.circular_shift_samples,
            "objective_increase": self.objective_increase,
            "local_maximum_combined_distance": self.local_maximum_combined_distance,
            "local_mean_combined_distance": self.local_mean_combined_distance,
            "flagged_neighbor_pair_count": self.flagged_neighbor_pair_count,
        }


@dataclass(frozen=True, slots=True)
class XtBaselineComparison:
    source_projection_set_sha256: str
    changed_anchor_count: int
    optimized_adjacent_mean: float
    optimized_adjacent_maximum: float
    baseline_adjacent_mean: float
    baseline_adjacent_maximum: float
    mean_improvement: float
    maximum_improvement: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_projection_set_sha256": self.source_projection_set_sha256,
            "changed_anchor_count": self.changed_anchor_count,
            "optimized_adjacent_mean": self.optimized_adjacent_mean,
            "optimized_adjacent_maximum": self.optimized_adjacent_maximum,
            "baseline_adjacent_mean": self.baseline_adjacent_mean,
            "baseline_adjacent_maximum": self.baseline_adjacent_maximum,
            "mean_improvement": self.mean_improvement,
            "maximum_improvement": self.maximum_improvement,
        }


@dataclass(frozen=True, slots=True)
class XtPreviewArtifact:
    kind: str
    file_name: str
    sample_rate: int
    sample_count: int
    channel_count: int
    sample_format: str
    duration_seconds: float
    sha256: str

    def __post_init__(self) -> None:
        if not self.kind or not self.file_name:
            raise AnalysisError("preview kind and file_name must not be empty")
        if self.sample_rate <= 0 or self.sample_count <= 0 or self.channel_count != 1:
            raise AnalysisError("preview technical properties are invalid")
        _require_positive(self.duration_seconds, name="preview duration_seconds")
        _require_hash(self.sha256, name="preview sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "file_name": self.file_name,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "channel_count": self.channel_count,
            "sample_format": self.sample_format,
            "duration_seconds": self.duration_seconds,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class XtTrajectoryQcAnalysis:
    schema_version: int
    tool_version: str
    source_trajectory_sha256: str
    source_projection_set_sha256: str
    config: XtTrajectoryQcConfig
    status: XtTrajectoryQcStatus
    jump_threshold: float
    jump_median: float
    jump_mad: float
    curvature_threshold: float
    curvature_median: float
    curvature_mad: float
    adjacent_pairs: tuple[XtAdjacentSlotAudit, ...]
    curvatures: tuple[XtCurvatureAudit, ...]
    phase_neighborhoods: tuple[XtPhaseNeighborhoodAudit, ...]
    baseline_comparison: XtBaselineComparison | None
    previews: tuple[XtPreviewArtifact, ...]
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != TRAJECTORY_QC_SCHEMA_VERSION:
            raise AnalysisError("Unsupported XT trajectory QC schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise AnalysisError("tool_version must be a normalized non-empty string")
        _require_hash(self.source_trajectory_sha256, name="source_trajectory_sha256")
        _require_hash(self.source_projection_set_sha256, name="source_projection_set_sha256")
        if not isinstance(self.status, XtTrajectoryQcStatus):
            raise AnalysisError("status must be an XtTrajectoryQcStatus")
        for name in (
            "jump_threshold",
            "jump_median",
            "jump_mad",
            "curvature_threshold",
            "curvature_median",
            "curvature_mad",
        ):
            _require_non_negative(getattr(self, name), name=name)
        if len(self.adjacent_pairs) != 60:
            raise AnalysisError("trajectory QC requires exactly 60 adjacent slot pairs")
        if len(self.curvatures) != 59:
            raise AnalysisError("trajectory QC requires exactly 59 interior curvature measurements")
        if not self.previews:
            raise AnalysisError("trajectory QC requires at least one deterministic preview")
        if not self.decision_reason:
            raise AnalysisError("decision_reason must not be empty")

    @property
    def flagged_jump_count(self) -> int:
        return sum(item.flagged_jump for item in self.adjacent_pairs)

    @property
    def flagged_curvature_count(self) -> int:
        return sum(item.flagged_curvature for item in self.curvatures)

    @property
    def maximum_adjacent_distance(self) -> float:
        return max(item.combined_distance for item in self.adjacent_pairs)

    @property
    def mean_adjacent_distance(self) -> float:
        return float(
            np.mean(
                np.asarray(
                    [item.combined_distance for item in self.adjacent_pairs],
                    dtype=np.float64,
                ),
                dtype=np.float64,
            )
        )

    @property
    def maximum_curvature(self) -> float:
        return max(item.combined_curvature for item in self.curvatures)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "source_trajectory_sha256": self.source_trajectory_sha256,
            "source_projection_set_sha256": self.source_projection_set_sha256,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "jump_threshold": self.jump_threshold,
            "jump_median": self.jump_median,
            "jump_mad": self.jump_mad,
            "curvature_threshold": self.curvature_threshold,
            "curvature_median": self.curvature_median,
            "curvature_mad": self.curvature_mad,
            "flagged_jump_count": self.flagged_jump_count,
            "flagged_curvature_count": self.flagged_curvature_count,
            "maximum_adjacent_distance": self.maximum_adjacent_distance,
            "mean_adjacent_distance": self.mean_adjacent_distance,
            "maximum_curvature": self.maximum_curvature,
            "adjacent_pairs": [item.to_dict() for item in self.adjacent_pairs],
            "curvatures": [item.to_dict() for item in self.curvatures],
            "phase_neighborhoods": [item.to_dict() for item in self.phase_neighborhoods],
            "baseline_comparison": (
                None if self.baseline_comparison is None else self.baseline_comparison.to_dict()
            ),
            "previews": [preview.to_dict() for preview in self.previews],
            "decision_reason": self.decision_reason,
            "boundaries": {
                "modifies_trajectory_slots": False,
                "generates_sysex": False,
                "allocates_hardware_user_waves": False,
                "writes_user_wavetable": False,
                "allows_negative_128": False,
                "preview_only": True,
            },
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# CODE V7-D — XT trajectory QC and deterministic audition",
            "",
            f"- Analysis SHA-256: `{self.analysis_sha256}`",
            f"- Source V7-C trajectory: `{self.source_trajectory_sha256}`",
            f"- Status: `{self.status.value}`",
            f"- Flagged adjacent jumps: `{self.flagged_jump_count}`",
            f"- Flagged curvature points: `{self.flagged_curvature_count}`",
            f"- Maximum adjacent distance: `{self.maximum_adjacent_distance:.12g}`",
            f"- Mean adjacent distance: `{self.mean_adjacent_distance:.12g}`",
            f"- Maximum curvature: `{self.maximum_curvature:.12g}`",
            "- SysEx generation: `no`",
            "- V7-C slot modification: `no`",
            "",
            "## Strongest adjacent transitions",
            "",
            "| Slots | Time | Spectral | Combined | Phase-change neighborhood | Flagged |",
            "|---:|---:|---:|---:|:---:|:---:|",
        ]
        strongest = sorted(
            self.adjacent_pairs,
            key=lambda item: (-item.combined_distance, item.pair_index),
        )[:10]
        for item in strongest:
            lines.append(
                f"| {item.left_slot_number}→{item.right_slot_number} | "
                f"{item.time_distance:.12g} | {item.spectral_distance:.12g} | "
                f"{item.combined_distance:.12g} | "
                f"{'yes' if item.touches_phase_changed_anchor else 'no'} | "
                f"{'yes' if item.flagged_jump else 'no'} |"
            )
        lines.extend(
            [
                "",
                "## Phase-changed anchors",
                "",
                "| Anchor | Slot | Shift | Objective increase | Local maximum | Flagged neighbors |",
                "|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for item in self.phase_neighborhoods:
            lines.append(
                f"| {item.anchor_index} | {item.slot_number} | "
                f"{item.circular_shift_samples} | {item.objective_increase:.12g} | "
                f"{item.local_maximum_combined_distance:.12g} | "
                f"{item.flagged_neighbor_pair_count} |"
            )
        if self.baseline_comparison is not None:
            comparison = self.baseline_comparison
            lines.extend(
                [
                    "",
                    "## Preserve-phase baseline comparison",
                    "",
                    f"- Changed anchors: `{comparison.changed_anchor_count}`",
                    f"- Optimized adjacent mean: `{comparison.optimized_adjacent_mean:.12g}`",
                    f"- Preserve-phase adjacent mean: `{comparison.baseline_adjacent_mean:.12g}`",
                    f"- Mean improvement: `{comparison.mean_improvement:.12g}`",
                    f"- Optimized adjacent maximum: `{comparison.optimized_adjacent_maximum:.12g}`",
                    f"- Preserve-phase adjacent maximum: `{comparison.baseline_adjacent_maximum:.12g}`",
                    f"- Maximum improvement: `{comparison.maximum_improvement:.12g}`",
                ]
            )
        lines.extend(
            [
                "",
                "## Deterministic previews",
                "",
                "| Kind | File | Rate | Duration | SHA-256 |",
                "|---|---|---:|---:|---|",
            ]
        )
        for preview in self.previews:
            lines.append(
                f"| {preview.kind} | `{preview.file_name}` | {preview.sample_rate} | "
                f"{preview.duration_seconds:.6f} s | `{preview.sha256}` |"
            )
        lines.extend(
            [
                "",
                "## Listening checklist",
                "",
                "Listen for abrupt timbral jumps, polarity-like half-cycle flips, clicks, "
                "unexpected loudness pumping, and regions that appear frozen or duplicated. "
                "The sweep is a mathematical preview and is not a bit-exact emulation of the "
                "Microwave XT oscillator or its analogue output stage.",
                "",
                "## Boundary",
                "",
                "CODE V7-D audits and renders the accepted V7-C trajectory. It does not change "
                "the 61 slots, allocate hardware memory, append the three fixed XT waves, build "
                "WAVD/WCTD messages, or transmit SysEx.",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class XtTrajectoryQcBuild:
    analysis: XtTrajectoryQcAnalysis
    preview_payloads: tuple[tuple[str, bytes], ...]

    def __post_init__(self) -> None:
        expected = {preview.file_name: preview.sha256 for preview in self.analysis.previews}
        actual_names = {name for name, _ in self.preview_payloads}
        if actual_names != set(expected):
            raise AnalysisError("preview payload names do not match analysis preview metadata")
        for name, payload in self.preview_payloads:
            if sha256(payload).hexdigest() != expected[name]:
                raise AnalysisError(f"preview payload hash mismatch for {name}")

    def write(
        self,
        directory: str | Path,
        *,
        stem: str = DEFAULT_STEM,
    ) -> tuple[Path, Path, tuple[Path, ...]]:
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        json_path = destination / f"{stem}.analysis.json"
        markdown_path = destination / f"{stem}.analysis.md"
        json_path.write_text(self.analysis.to_json(), encoding="utf-8", newline="\n")
        markdown_path.write_text(self.analysis.to_markdown(), encoding="utf-8", newline="\n")
        preview_paths: list[Path] = []
        for name, payload in self.preview_payloads:
            path = destination / name
            path.write_bytes(payload)
            preview_paths.append(path)
        return json_path, markdown_path, tuple(preview_paths)


def _lookup_wave(waveform: npt.NDArray[np.float64], phase: float) -> float:
    position = (phase % 1.0) * SOURCE_SAMPLE_COUNT
    left = int(math.floor(position)) % SOURCE_SAMPLE_COUNT
    fraction = position - math.floor(position)
    right = (left + 1) % SOURCE_SAMPLE_COUNT
    return float((1.0 - fraction) * waveform[left] + fraction * waveform[right])


def _fade_envelope(sample_count: int, fade_samples: int) -> npt.NDArray[np.float64]:
    envelope = np.ones(sample_count, dtype=np.float64)
    if fade_samples <= 0:
        return envelope
    fade = min(fade_samples, sample_count // 2)
    if fade <= 0:
        return envelope
    ramp = np.arange(fade, dtype=np.float64) / float(fade)
    envelope[:fade] = ramp
    envelope[-fade:] = ramp[::-1]
    return envelope


def _normalize_preview(samples: npt.NDArray[np.float64], peak: float) -> npt.NDArray[np.float64]:
    maximum = float(np.max(np.abs(samples)))
    if maximum <= _EPSILON:
        raise AnalysisError("preview renderer produced silence")
    return np.asarray(samples * (peak / maximum), dtype=np.float64)


def _pcm16_wav_bytes(samples: npt.NDArray[np.float64], sample_rate: int) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    integers = _round_half_away_from_zero(clipped * 32767.0)
    integers = np.clip(integers, -32767, 32767).astype("<i2", copy=False)
    payload = integers.tobytes(order="C")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.setnframes(int(integers.size))
        writer.writeframes(payload)
    return buffer.getvalue()


def _render_sweep(
    slots: Sequence[Sequence[int]],
    *,
    config: XtTrajectoryQcConfig,
) -> npt.NDArray[np.float64]:
    waveforms = tuple(
        np.asarray(reconstruct_xt_native(stored), dtype=np.float64) / XT_SAMPLE_MAX
        for stored in slots
    )
    sample_count = max(2, int(round(config.sample_rate * config.sweep_duration_seconds)))
    output = np.empty(sample_count, dtype=np.float64)
    phase = 0.0
    phase_step = config.preview_frequency_hz / config.sample_rate
    maximum_position = len(waveforms) - 1
    for sample_index in range(sample_count):
        position = maximum_position * sample_index / (sample_count - 1)
        left_index = min(int(math.floor(position)), maximum_position)
        right_index = min(left_index + 1, maximum_position)
        alpha = position - left_index
        left_value = _lookup_wave(waveforms[left_index], phase)
        right_value = _lookup_wave(waveforms[right_index], phase)
        output[sample_index] = (1.0 - alpha) * left_value + alpha * right_value
        phase = (phase + phase_step) % 1.0
    fade_samples = int(round(config.fade_duration_seconds * config.sample_rate))
    output *= _fade_envelope(sample_count, fade_samples)
    return _normalize_preview(output, config.preview_peak)


def _render_stepped(
    slots: Sequence[Sequence[int]],
    *,
    config: XtTrajectoryQcConfig,
) -> npt.NDArray[np.float64]:
    waveforms = tuple(
        np.asarray(reconstruct_xt_native(stored), dtype=np.float64) / XT_SAMPLE_MAX
        for stored in slots
    )
    samples_per_slot = max(
        2,
        int(round(config.sample_rate * config.stepped_slot_duration_seconds)),
    )
    total_samples = samples_per_slot * len(waveforms)
    transition_samples = int(round(samples_per_slot * config.transition_fraction))
    transition_samples = min(max(0, transition_samples), samples_per_slot - 1)
    output = np.empty(total_samples, dtype=np.float64)
    phase = 0.0
    phase_step = config.preview_frequency_hz / config.sample_rate
    for slot_index, waveform in enumerate(waveforms):
        next_waveform = waveforms[min(slot_index + 1, len(waveforms) - 1)]
        for local_index in range(samples_per_slot):
            if transition_samples > 0 and local_index >= samples_per_slot - transition_samples:
                alpha = (
                    local_index - (samples_per_slot - transition_samples)
                ) / float(transition_samples)
            else:
                alpha = 0.0
            value = (1.0 - alpha) * _lookup_wave(waveform, phase) + alpha * _lookup_wave(next_waveform, phase)
            output[slot_index * samples_per_slot + local_index] = value
            phase = (phase + phase_step) % 1.0
    fade_samples = int(round(config.fade_duration_seconds * config.sample_rate))
    output *= _fade_envelope(total_samples, fade_samples)
    return _normalize_preview(output, config.preview_peak)


def _preview_artifact(
    *,
    kind: str,
    file_name: str,
    samples: npt.NDArray[np.float64],
    sample_rate: int,
) -> tuple[XtPreviewArtifact, bytes]:
    payload = _pcm16_wav_bytes(samples, sample_rate)
    artifact = XtPreviewArtifact(
        kind=kind,
        file_name=file_name,
        sample_rate=sample_rate,
        sample_count=int(samples.size),
        channel_count=1,
        sample_format="PCM_16",
        duration_seconds=float(samples.size / sample_rate),
        sha256=sha256(payload).hexdigest(),
    )
    return artifact, payload


def _build_baseline_slots(
    slots: Sequence[Mapping[str, Any]],
    projected_waves: Sequence[Mapping[str, Any]],
) -> tuple[tuple[int, ...], ...]:
    anchors = tuple(
        _validated_stored(wave.get("stored_samples", ()), name=f"baseline anchor {index}")
        for index, wave in enumerate(projected_waves)
    )
    result: list[tuple[int, ...]] = []
    for slot in slots:
        left_index = int(slot.get("left_anchor_index", -1))
        right_index = int(slot.get("right_anchor_index", -1))
        if left_index not in range(len(anchors)) or right_index not in range(len(anchors)):
            raise AnalysisError("trajectory slot anchor index is outside projection range")
        if str(slot.get("kind", "")) == "anchor":
            result.append(anchors[left_index])
        else:
            result.append(
                _interpolate_stored(
                    anchors[left_index],
                    anchors[right_index],
                    float(slot.get("blend_fraction", -1.0)),
                )
            )
    return tuple(result)


def _distance_series(
    stored_slots: Sequence[Sequence[int]],
    *,
    config: XtTrajectoryQcConfig,
) -> tuple[float, ...]:
    return tuple(
        _combined_distance(
            left,
            right,
            time_weight=config.time_weight,
            spectral_weight=config.spectral_weight,
        )[2]
        for left, right in zip(stored_slots, stored_slots[1:])
    )


def analyze_xt_trajectory_qc_documents(
    trajectory_document: Mapping[str, Any],
    *,
    projection_document: Mapping[str, Any] | None = None,
    config: XtTrajectoryQcConfig | None = None,
    tool_version: str = __version__,
) -> XtTrajectoryQcBuild:
    selected_config = XtTrajectoryQcConfig() if config is None else config
    trajectory_hash, slots, anchors = _validate_trajectory_document(trajectory_document)
    source_projection_hash = str(trajectory_document.get("source_projection_set_sha256", ""))
    _require_hash(source_projection_hash, name="source_projection_set_sha256")

    stored_slots = tuple(
        _validated_stored(slot.get("stored_samples", ()), name=f"slot {index + 1}")
        for index, slot in enumerate(slots)
    )
    anchor_slot_numbers = tuple(int(value) for value in trajectory_document["anchor_slot_numbers"])
    anchor_slot_set = set(anchor_slot_numbers)
    changed_anchor_slot_set = {
        anchor_slot_numbers[index]
        for index, anchor in enumerate(anchors)
        if int(anchor.get("original_phase_rotation_samples", -1))
        != int(anchor.get("selected_phase_rotation_samples", -1))
    }

    raw_adjacent: list[tuple[float, float, float]] = []
    for left, right in zip(stored_slots, stored_slots[1:]):
        raw_adjacent.append(
            _combined_distance(
                left,
                right,
                time_weight=selected_config.time_weight,
                spectral_weight=selected_config.spectral_weight,
            )
        )
    jump_threshold, jump_median, jump_mad = _robust_threshold(
        [item[2] for item in raw_adjacent],
        absolute_minimum=selected_config.jump_absolute_minimum,
        median_multiplier=selected_config.jump_median_multiplier,
        mad_multiplier=selected_config.jump_mad_multiplier,
    )
    adjacent_pairs = tuple(
        XtAdjacentSlotAudit(
            pair_index=index,
            left_slot_number=index + 1,
            right_slot_number=index + 2,
            time_distance=values[0],
            spectral_distance=values[1],
            combined_distance=values[2],
            touches_anchor=(index + 1 in anchor_slot_set or index + 2 in anchor_slot_set),
            touches_phase_changed_anchor=(
                index + 1 in changed_anchor_slot_set or index + 2 in changed_anchor_slot_set
            ),
            flagged_jump=values[2] > jump_threshold + _EPSILON,
        )
        for index, values in enumerate(raw_adjacent)
    )

    raw_curvatures: list[tuple[float, float, float]] = []
    for left, center, right in zip(stored_slots, stored_slots[1:], stored_slots[2:]):
        time_value = _time_curvature(left, center, right)
        spectral_value = _spectral_curvature(left, center, right)
        combined_value = (
            selected_config.time_weight * time_value
            + selected_config.spectral_weight * spectral_value
        )
        raw_curvatures.append((time_value, spectral_value, float(combined_value)))
    curvature_threshold, curvature_median, curvature_mad = _robust_threshold(
        [item[2] for item in raw_curvatures],
        absolute_minimum=selected_config.curvature_absolute_minimum,
        median_multiplier=selected_config.curvature_median_multiplier,
        mad_multiplier=selected_config.curvature_mad_multiplier,
    )
    curvatures = tuple(
        XtCurvatureAudit(
            center_slot_number=index + 2,
            time_curvature=values[0],
            spectral_curvature=values[1],
            combined_curvature=values[2],
            touches_anchor=(index + 2 in anchor_slot_set),
            touches_phase_changed_anchor=(index + 2 in changed_anchor_slot_set),
            flagged_curvature=values[2] > curvature_threshold + _EPSILON,
        )
        for index, values in enumerate(raw_curvatures)
    )

    phase_neighborhoods: list[XtPhaseNeighborhoodAudit] = []
    for anchor_index, anchor in enumerate(anchors):
        original = int(anchor.get("original_phase_rotation_samples", -1))
        selected = int(anchor.get("selected_phase_rotation_samples", -1))
        if original == selected:
            continue
        slot_number = anchor_slot_numbers[anchor_index]
        local_pairs = tuple(
            item
            for item in adjacent_pairs
            if item.left_slot_number == slot_number or item.right_slot_number == slot_number
        )
        raw_delta = selected - original
        circular_shift = ((raw_delta + 64) % 128) - 64
        phase_neighborhoods.append(
            XtPhaseNeighborhoodAudit(
                anchor_index=anchor_index,
                source_wave_index=int(anchor.get("source_wave_index", -1)),
                slot_number=slot_number,
                original_phase_rotation_samples=original,
                selected_phase_rotation_samples=selected,
                circular_shift_samples=int(circular_shift),
                objective_increase=float(anchor.get("objective_increase", 0.0)),
                local_maximum_combined_distance=max(item.combined_distance for item in local_pairs),
                local_mean_combined_distance=float(
                    np.mean(
                        np.asarray([item.combined_distance for item in local_pairs], dtype=np.float64),
                        dtype=np.float64,
                    )
                ),
                flagged_neighbor_pair_count=sum(item.flagged_jump for item in local_pairs),
            )
        )

    baseline_comparison: XtBaselineComparison | None = None
    preview_payloads: list[tuple[str, bytes]] = []
    previews: list[XtPreviewArtifact] = []

    optimized_sweep = _render_sweep(stored_slots, config=selected_config)
    optimized_stepped = _render_stepped(stored_slots, config=selected_config)
    for kind, file_name, samples in (
        ("optimized_continuous_sweep", DEFAULT_SWEEP_FILE_NAME, optimized_sweep),
        ("optimized_stepped_slots", DEFAULT_STEPPED_FILE_NAME, optimized_stepped),
    ):
        artifact, payload = _preview_artifact(
            kind=kind,
            file_name=file_name,
            samples=samples,
            sample_rate=selected_config.sample_rate,
        )
        previews.append(artifact)
        preview_payloads.append((file_name, payload))

    if projection_document is not None:
        projected_waves = _validate_projection_document(
            projection_document,
            expected_hash=source_projection_hash,
            expected_wave_count=len(anchors),
        )
        baseline_slots = _build_baseline_slots(slots, projected_waves)
        optimized_distances = _distance_series(stored_slots, config=selected_config)
        baseline_distances = _distance_series(baseline_slots, config=selected_config)
        optimized_mean = float(np.mean(np.asarray(optimized_distances), dtype=np.float64))
        baseline_mean = float(np.mean(np.asarray(baseline_distances), dtype=np.float64))
        optimized_max = max(optimized_distances)
        baseline_max = max(baseline_distances)
        baseline_comparison = XtBaselineComparison(
            source_projection_set_sha256=source_projection_hash,
            changed_anchor_count=len(phase_neighborhoods),
            optimized_adjacent_mean=optimized_mean,
            optimized_adjacent_maximum=optimized_max,
            baseline_adjacent_mean=baseline_mean,
            baseline_adjacent_maximum=baseline_max,
            mean_improvement=baseline_mean - optimized_mean,
            maximum_improvement=baseline_max - optimized_max,
        )
        baseline_sweep = _render_sweep(baseline_slots, config=selected_config)
        artifact, payload = _preview_artifact(
            kind="preserve_phase_baseline_sweep",
            file_name=DEFAULT_BASELINE_SWEEP_FILE_NAME,
            samples=baseline_sweep,
            sample_rate=selected_config.sample_rate,
        )
        previews.append(artifact)
        preview_payloads.append((artifact.file_name, payload))

    flagged_jump_count = sum(item.flagged_jump for item in adjacent_pairs)
    flagged_curvature_count = sum(item.flagged_curvature for item in curvatures)
    status = (
        XtTrajectoryQcStatus.PASS
        if flagged_jump_count == 0 and flagged_curvature_count == 0
        else XtTrajectoryQcStatus.REVIEW
    )
    if status is XtTrajectoryQcStatus.PASS:
        reason = (
            "All 60 adjacent transitions and 59 interior curvature points remain below "
            "the deterministic robust QC thresholds; deterministic previews were rendered."
        )
    else:
        reason = (
            f"Manual review required: {flagged_jump_count} adjacent transition(s) and "
            f"{flagged_curvature_count} curvature point(s) exceed deterministic QC thresholds."
        )

    analysis = XtTrajectoryQcAnalysis(
        schema_version=TRAJECTORY_QC_SCHEMA_VERSION,
        tool_version=tool_version,
        source_trajectory_sha256=trajectory_hash,
        source_projection_set_sha256=source_projection_hash,
        config=selected_config,
        status=status,
        jump_threshold=jump_threshold,
        jump_median=jump_median,
        jump_mad=jump_mad,
        curvature_threshold=curvature_threshold,
        curvature_median=curvature_median,
        curvature_mad=curvature_mad,
        adjacent_pairs=adjacent_pairs,
        curvatures=curvatures,
        phase_neighborhoods=tuple(phase_neighborhoods),
        baseline_comparison=baseline_comparison,
        previews=tuple(previews),
        decision_reason=reason,
    )
    return XtTrajectoryQcBuild(
        analysis=analysis,
        preview_payloads=tuple(preview_payloads),
    )


def load_and_analyze_xt_trajectory_qc(
    trajectory_path: str | Path,
    *,
    projection_path: str | Path | None = None,
    config: XtTrajectoryQcConfig | None = None,
    tool_version: str = __version__,
) -> XtTrajectoryQcBuild:
    trajectory = _read_json(trajectory_path)
    projection = None if projection_path is None else _read_json(projection_path)
    return analyze_xt_trajectory_qc_documents(
        trajectory,
        projection_document=projection,
        config=config,
        tool_version=tool_version,
    )
