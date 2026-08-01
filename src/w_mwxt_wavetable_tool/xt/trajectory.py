from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

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

TRAJECTORY_SCHEMA_VERSION = 1
DEFAULT_TARGET_SLOT_COUNT = 61
DEFAULT_STEM = "CODE_V7_C_XT_WAVETABLE_TRAJECTORY"
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


def _round_half_away_from_zero(values: npt.NDArray[np.float64]) -> npt.NDArray[np.int64]:
    magnitudes = np.floor(np.abs(values) + 0.5)
    return np.asarray(np.copysign(magnitudes, values), dtype=np.int64)


def _validated_stored_samples(values: Sequence[int], *, name: str) -> tuple[int, ...]:
    stored = tuple(int(value) for value in values)
    if len(stored) != STORED_SAMPLE_COUNT:
        raise AnalysisError(f"{name} must contain exactly {STORED_SAMPLE_COUNT} values")
    if any(value < XT_SAMPLE_MIN or value > XT_SAMPLE_MAX for value in stored):
        raise AnalysisError(f"{name} must stay in [{XT_SAMPLE_MIN}, {XT_SAMPLE_MAX}]")
    if XT_SAMPLE_MIN - 1 in stored:
        raise AnalysisError(f"{name} contains forbidden -128")
    return stored


def _validated_source_samples(values: Sequence[float], *, name: str) -> npt.NDArray[np.float64]:
    samples = np.asarray(tuple(float(value) for value in values), dtype=np.float64)
    if samples.shape != (SOURCE_SAMPLE_COUNT,):
        raise AnalysisError(f"{name} must contain exactly {SOURCE_SAMPLE_COUNT} values")
    if not np.all(np.isfinite(samples)):
        raise AnalysisError(f"{name} contains NaN or infinite values")
    if float(np.max(np.abs(samples))) > 1.0 + _EPSILON:
        raise AnalysisError(f"{name} exceeds normalized range [-1, 1]")
    return samples


def _stored_for_phase(samples: npt.NDArray[np.float64], phase: int) -> tuple[int, ...]:
    if phase not in range(SOURCE_SAMPLE_COUNT):
        raise AnalysisError("phase must be in range 0..127")
    rotated = np.roll(samples, -phase)
    continuous = 0.5 * (
        rotated[:STORED_SAMPLE_COUNT]
        - rotated[::-1][:STORED_SAMPLE_COUNT]
    )
    quantized = _round_half_away_from_zero(continuous * XT_SAMPLE_MAX)
    quantized = np.clip(quantized, XT_SAMPLE_MIN, XT_SAMPLE_MAX)
    return tuple(int(value) for value in quantized)


def _normalized_spectrum(stored: Sequence[int]) -> npt.NDArray[np.float64]:
    reconstructed = np.asarray(reconstruct_xt_native(stored), dtype=np.float64) / XT_SAMPLE_MAX
    magnitudes = np.abs(np.fft.rfft(reconstructed))[1:]
    norm = float(np.linalg.norm(magnitudes))
    if norm <= _EPSILON:
        return np.zeros_like(magnitudes, dtype=np.float64)
    return np.asarray(magnitudes / norm, dtype=np.float64)


def _stored_distance(left: Sequence[int], right: Sequence[int]) -> float:
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
    similarity = float(
        np.clip(
            np.dot(left_spectrum, right_spectrum) / denominator,
            0.0,
            1.0,
        )
    )
    return 1.0 - similarity


def _interpolate_stored(
    left: Sequence[int],
    right: Sequence[int],
    blend_fraction: float,
) -> tuple[int, ...]:
    alpha = _require_finite(blend_fraction, name="blend_fraction")
    if not 0.0 <= alpha <= 1.0:
        raise AnalysisError("blend_fraction must be between 0 and 1")
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    quantized = _round_half_away_from_zero((1.0 - alpha) * left_array + alpha * right_array)
    quantized = np.clip(quantized, XT_SAMPLE_MIN, XT_SAMPLE_MAX)
    return tuple(int(value) for value in quantized)


class XtPhasePathPolicy(str, Enum):
    PRESERVE = "preserve"
    GLOBAL = "global"


class XtInterpolationCurve(str, Enum):
    LINEAR = "linear"
    SMOOTHSTEP = "smoothstep"


class XtTrajectorySlotKind(str, Enum):
    ANCHOR = "anchor"
    INTERPOLATED = "interpolated"


@dataclass(frozen=True, slots=True)
class XtTrajectoryConfig:
    target_slot_count: int = DEFAULT_TARGET_SLOT_COUNT
    phase_path_policy: XtPhasePathPolicy = XtPhasePathPolicy.GLOBAL
    interpolation_curve: XtInterpolationCurve = XtInterpolationCurve.LINEAR
    local_fidelity_weight: float = 0.35
    transition_weight: float = 0.65
    transition_time_weight: float = 0.70
    transition_spectral_weight: float = 0.30
    max_objective_increase: float = 0.02
    minimum_intermediates_per_transition: int = 1
    spacing_power: float = 1.0

    def __post_init__(self) -> None:
        if not 2 <= self.target_slot_count <= DEFAULT_TARGET_SLOT_COUNT:
            raise AnalysisError("target_slot_count must be between 2 and 61")
        if not isinstance(self.phase_path_policy, XtPhasePathPolicy):
            raise AnalysisError("phase_path_policy must be an XtPhasePathPolicy")
        if not isinstance(self.interpolation_curve, XtInterpolationCurve):
            raise AnalysisError("interpolation_curve must be an XtInterpolationCurve")
        outer = (
            _require_non_negative(self.local_fidelity_weight, name="local_fidelity_weight"),
            _require_non_negative(self.transition_weight, name="transition_weight"),
        )
        if not math.isclose(sum(outer), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise AnalysisError("local_fidelity_weight and transition_weight must sum exactly to 1.0")
        inner = (
            _require_non_negative(self.transition_time_weight, name="transition_time_weight"),
            _require_non_negative(self.transition_spectral_weight, name="transition_spectral_weight"),
        )
        if not math.isclose(sum(inner), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise AnalysisError("transition time and spectral weights must sum exactly to 1.0")
        _require_non_negative(self.max_objective_increase, name="max_objective_increase")
        if self.minimum_intermediates_per_transition < 0:
            raise AnalysisError("minimum_intermediates_per_transition must not be negative")
        _require_positive(self.spacing_power, name="spacing_power")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_slot_count": self.target_slot_count,
            "phase_path_policy": self.phase_path_policy.value,
            "interpolation_curve": self.interpolation_curve.value,
            "local_fidelity_weight": self.local_fidelity_weight,
            "transition_weight": self.transition_weight,
            "transition_time_weight": self.transition_time_weight,
            "transition_spectral_weight": self.transition_spectral_weight,
            "max_objective_increase": self.max_objective_increase,
            "minimum_intermediates_per_transition": self.minimum_intermediates_per_transition,
            "spacing_power": self.spacing_power,
        }


@dataclass(frozen=True, slots=True)
class XtTrajectoryAnchor:
    anchor_index: int
    source_wave_index: int
    candidate_index: int
    source_projection_sha256: str
    original_phase_rotation_samples: int
    selected_phase_rotation_samples: int
    original_objective_score: float
    selected_objective_score: float
    objective_increase: float
    admissible_phase_count: int
    stored_samples: tuple[int, ...]
    reconstructed_samples: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.anchor_index < 0 or self.source_wave_index < 0 or self.candidate_index < 0:
            raise AnalysisError("anchor and source indexes must not be negative")
        _require_hash(self.source_projection_sha256, name="source_projection_sha256")
        if self.original_phase_rotation_samples not in range(SOURCE_SAMPLE_COUNT):
            raise AnalysisError("original phase must be in range 0..127")
        if self.selected_phase_rotation_samples not in range(SOURCE_SAMPLE_COUNT):
            raise AnalysisError("selected phase must be in range 0..127")
        _require_non_negative(self.original_objective_score, name="original_objective_score")
        _require_non_negative(self.selected_objective_score, name="selected_objective_score")
        _require_non_negative(self.objective_increase, name="objective_increase")
        if self.admissible_phase_count <= 0:
            raise AnalysisError("admissible_phase_count must be positive")
        stored = _validated_stored_samples(self.stored_samples, name="anchor stored_samples")
        if reconstruct_xt_native(stored) != self.reconstructed_samples:
            raise AnalysisError("anchor reconstruction does not match stored samples")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "anchor_index": self.anchor_index,
            "source_wave_index": self.source_wave_index,
            "candidate_index": self.candidate_index,
            "source_projection_sha256": self.source_projection_sha256,
            "original_phase_rotation_samples": self.original_phase_rotation_samples,
            "selected_phase_rotation_samples": self.selected_phase_rotation_samples,
            "original_objective_score": self.original_objective_score,
            "selected_objective_score": self.selected_objective_score,
            "objective_increase": self.objective_increase,
            "admissible_phase_count": self.admissible_phase_count,
            "stored_samples": list(self.stored_samples),
            "reconstructed_samples": list(self.reconstructed_samples),
        }

    @property
    def anchor_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["anchor_sha256"] = self.anchor_sha256
        return result


@dataclass(frozen=True, slots=True)
class XtTrajectoryTransition:
    transition_index: int
    left_anchor_index: int
    right_anchor_index: int
    stored_distance: float
    spectral_distance: float
    combined_distance: float
    allocated_intermediate_count: int

    def __post_init__(self) -> None:
        if self.transition_index < 0:
            raise AnalysisError("transition_index must not be negative")
        if self.left_anchor_index < 0 or self.right_anchor_index != self.left_anchor_index + 1:
            raise AnalysisError("transitions must connect consecutive anchors")
        for name in ("stored_distance", "spectral_distance", "combined_distance"):
            value = _require_non_negative(getattr(self, name), name=name)
            if value > 1.0 + _EPSILON:
                raise AnalysisError(f"{name} must not exceed 1")
        if self.allocated_intermediate_count < 0:
            raise AnalysisError("allocated_intermediate_count must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_index": self.transition_index,
            "left_anchor_index": self.left_anchor_index,
            "right_anchor_index": self.right_anchor_index,
            "stored_distance": self.stored_distance,
            "spectral_distance": self.spectral_distance,
            "combined_distance": self.combined_distance,
            "allocated_intermediate_count": self.allocated_intermediate_count,
        }


@dataclass(frozen=True, slots=True)
class XtTrajectorySlot:
    slot_number: int
    kind: XtTrajectorySlotKind
    left_anchor_index: int
    right_anchor_index: int
    position_fraction: float
    blend_fraction: float
    source_wave_index: int | None
    stored_samples: tuple[int, ...]
    reconstructed_samples: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.slot_number <= 0:
            raise AnalysisError("slot_number must be positive")
        if not isinstance(self.kind, XtTrajectorySlotKind):
            raise AnalysisError("kind must be an XtTrajectorySlotKind")
        if self.left_anchor_index < 0 or self.right_anchor_index < self.left_anchor_index:
            raise AnalysisError("slot anchor bounds are invalid")
        for name in ("position_fraction", "blend_fraction"):
            value = _require_finite(getattr(self, name), name=name)
            if not 0.0 <= value <= 1.0:
                raise AnalysisError(f"{name} must be between 0 and 1")
        if self.kind is XtTrajectorySlotKind.ANCHOR:
            if self.left_anchor_index != self.right_anchor_index:
                raise AnalysisError("anchor slots must reference one anchor")
            if self.source_wave_index is None:
                raise AnalysisError("anchor slots require source_wave_index")
        else:
            if self.right_anchor_index != self.left_anchor_index + 1:
                raise AnalysisError("interpolated slots must connect consecutive anchors")
            if self.source_wave_index is not None:
                raise AnalysisError("interpolated slots must not expose source_wave_index")
            if not 0.0 < self.position_fraction < 1.0:
                raise AnalysisError("interpolated position_fraction must be strictly between 0 and 1")
        stored = _validated_stored_samples(self.stored_samples, name="slot stored_samples")
        if reconstruct_xt_native(stored) != self.reconstructed_samples:
            raise AnalysisError("slot reconstruction does not match stored samples")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "slot_number": self.slot_number,
            "kind": self.kind.value,
            "left_anchor_index": self.left_anchor_index,
            "right_anchor_index": self.right_anchor_index,
            "position_fraction": self.position_fraction,
            "blend_fraction": self.blend_fraction,
            "source_wave_index": self.source_wave_index,
            "stored_samples": list(self.stored_samples),
            "reconstructed_samples": list(self.reconstructed_samples),
        }

    @property
    def slot_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["slot_sha256"] = self.slot_sha256
        return result


@dataclass(frozen=True, slots=True)
class XtWavetableTrajectory:
    schema_version: int
    tool_version: str
    source_projection_set_sha256: str
    source_reconstructed_wave_set_sha256: str
    config: XtTrajectoryConfig
    anchors: tuple[XtTrajectoryAnchor, ...]
    transitions: tuple[XtTrajectoryTransition, ...]
    slots: tuple[XtTrajectorySlot, ...]
    phase_path_cost: float
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != TRAJECTORY_SCHEMA_VERSION:
            raise AnalysisError("Unsupported XT trajectory schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise AnalysisError("tool_version must be a normalized non-empty string")
        _require_hash(self.source_projection_set_sha256, name="source_projection_set_sha256")
        _require_hash(
            self.source_reconstructed_wave_set_sha256,
            name="source_reconstructed_wave_set_sha256",
        )
        if len(self.anchors) < 2:
            raise AnalysisError("trajectory requires at least two anchors")
        if len(self.anchors) > self.config.target_slot_count:
            raise AnalysisError("anchor count exceeds target slot count")
        if tuple(anchor.anchor_index for anchor in self.anchors) != tuple(range(len(self.anchors))):
            raise AnalysisError("anchor indexes must be contiguous from zero")
        if tuple(anchor.source_wave_index for anchor in self.anchors) != tuple(range(len(self.anchors))):
            raise AnalysisError("source wave order must be preserved")
        if len(self.transitions) != len(self.anchors) - 1:
            raise AnalysisError("transition count must equal anchor_count - 1")
        if tuple(slot.slot_number for slot in self.slots) != tuple(range(1, len(self.slots) + 1)):
            raise AnalysisError("slot numbers must be contiguous from one")
        if len(self.slots) != self.config.target_slot_count:
            raise AnalysisError("slot count does not match target_slot_count")
        anchor_slots = tuple(slot for slot in self.slots if slot.kind is XtTrajectorySlotKind.ANCHOR)
        if len(anchor_slots) != len(self.anchors):
            raise AnalysisError("every anchor must appear exactly once in slots")
        for anchor, slot in zip(self.anchors, anchor_slots, strict=True):
            if slot.left_anchor_index != anchor.anchor_index:
                raise AnalysisError("anchor slot order is inconsistent")
            if slot.stored_samples != anchor.stored_samples:
                raise AnalysisError("anchor slot does not preserve anchor stored samples")
        _require_non_negative(self.phase_path_cost, name="phase_path_cost")
        if not self.decision_reason:
            raise AnalysisError("decision_reason must not be empty")

    @property
    def anchor_count(self) -> int:
        return len(self.anchors)

    @property
    def interpolated_slot_count(self) -> int:
        return sum(slot.kind is XtTrajectorySlotKind.INTERPOLATED for slot in self.slots)

    @property
    def anchor_slot_numbers(self) -> tuple[int, ...]:
        return tuple(
            slot.slot_number
            for slot in self.slots
            if slot.kind is XtTrajectorySlotKind.ANCHOR
        )

    @property
    def phase_change_count(self) -> int:
        return sum(
            anchor.original_phase_rotation_samples != anchor.selected_phase_rotation_samples
            for anchor in self.anchors
        )

    @property
    def duplicate_adjacent_slot_pairs(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (left.slot_number, right.slot_number)
            for left, right in zip(self.slots, self.slots[1:])
            if left.stored_samples == right.stored_samples
        )

    @property
    def adjacent_distance_summary(self) -> dict[str, float]:
        values = np.asarray(
            [
                _stored_distance(left.stored_samples, right.stored_samples)
                for left, right in zip(self.slots, self.slots[1:])
            ],
            dtype=np.float64,
        )
        return {
            "minimum": float(np.min(values)),
            "mean": float(np.mean(values, dtype=np.float64)),
            "maximum": float(np.max(values)),
        }

    @property
    def anchor_sha256(self) -> tuple[str, ...]:
        return tuple(anchor.anchor_sha256 for anchor in self.anchors)

    @property
    def slot_sha256(self) -> tuple[str, ...]:
        return tuple(slot.slot_sha256 for slot in self.slots)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "source_projection_set_sha256": self.source_projection_set_sha256,
            "source_reconstructed_wave_set_sha256": self.source_reconstructed_wave_set_sha256,
            "config": self.config.to_dict(),
            "order_policy": "source_order",
            "anchor_count": self.anchor_count,
            "interpolated_slot_count": self.interpolated_slot_count,
            "slot_count": len(self.slots),
            "anchor_slot_numbers": list(self.anchor_slot_numbers),
            "phase_change_count": self.phase_change_count,
            "phase_path_cost": self.phase_path_cost,
            "duplicate_adjacent_slot_pairs": [list(pair) for pair in self.duplicate_adjacent_slot_pairs],
            "adjacent_distance_summary": self.adjacent_distance_summary,
            "anchor_sha256": list(self.anchor_sha256),
            "slot_sha256": list(self.slot_sha256),
            "anchors": [anchor.to_dict() for anchor in self.anchors],
            "transitions": [transition.to_dict() for transition in self.transitions],
            "slots": [slot.to_dict() for slot in self.slots],
            "decision_reason": self.decision_reason,
            "boundaries": {
                "generates_sysex": False,
                "allocates_hardware_user_waves": False,
                "writes_user_wavetable": False,
                "includes_three_fixed_xt_waves": False,
                "allows_negative_128": False,
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
            "# CODE V7-C — XT wavetable trajectory",
            "",
            f"- Analysis SHA-256: `{self.analysis_sha256}`",
            f"- Source V7-B projection: `{self.source_projection_set_sha256}`",
            f"- Structural anchors: `{self.anchor_count}`",
            f"- Interpolated positions: `{self.interpolated_slot_count}`",
            f"- Total editable positions: `{len(self.slots)}`",
            f"- Phase policy: `{self.config.phase_path_policy.value}`",
            f"- Phase changes relative to V7-B: `{self.phase_change_count}`",
            f"- Duplicate adjacent slot pairs: `{len(self.duplicate_adjacent_slot_pairs)}`",
            "- SysEx generation: `no`",
            "",
            "## Anchor placement",
            "",
            "| Anchor | Source wave | Candidate | Original phase | Selected phase | Slot | Objective increase |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for anchor, slot_number in zip(self.anchors, self.anchor_slot_numbers, strict=True):
            lines.append(
                f"| {anchor.anchor_index} | {anchor.source_wave_index} | {anchor.candidate_index} | "
                f"{anchor.original_phase_rotation_samples} | {anchor.selected_phase_rotation_samples} | "
                f"{slot_number} | {anchor.objective_increase:.12g} |"
            )
        lines.extend(
            [
                "",
                "## Transition allocation",
                "",
                "| Transition | Anchors | Combined distance | Intermediate positions |",
                "|---:|---:|---:|---:|",
            ]
        )
        for transition in self.transitions:
            lines.append(
                f"| {transition.transition_index} | {transition.left_anchor_index}→{transition.right_anchor_index} | "
                f"{transition.combined_distance:.12g} | {transition.allocated_intermediate_count} |"
            )
        lines.extend(
            [
                "",
                "## Boundary",
                "",
                "This stage constructs a deterministic 61-position mathematical trajectory only. "
                "It preserves source order, does not allocate hardware memory, does not append the XT fixed waves, "
                "does not build WCTD/WAVD messages, and does not transmit SysEx.",
                "",
            ]
        )
        return "\n".join(lines)

    def write(self, directory: str | Path, *, stem: str = DEFAULT_STEM) -> tuple[Path, Path]:
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        json_path = destination / f"{stem}.analysis.json"
        markdown_path = destination / f"{stem}.analysis.md"
        json_path.write_text(self.to_json(), encoding="utf-8", newline="\n")
        markdown_path.write_text(self.to_markdown(), encoding="utf-8", newline="\n")
        return json_path, markdown_path


def _validated_hashed_document(document: Mapping[str, Any], *, hash_field: str) -> str:
    recorded = str(document.get(hash_field, ""))
    _require_hash(recorded, name=hash_field)
    content = dict(document)
    del content[hash_field]
    calculated = _canonical_sha256(content)
    if calculated != recorded:
        raise AnalysisError(f"{hash_field} mismatch: recorded={recorded}, calculated={calculated}")
    return recorded


def _validate_projection_document(document: Mapping[str, Any]) -> tuple[str, str, list[Mapping[str, Any]]]:
    analysis_hash = _validated_hashed_document(document, hash_field="analysis_sha256")
    if int(document.get("schema_version", 0)) != 1:
        raise AnalysisError("CODE V7-C requires XT projection schema version 1")
    if int(document.get("source_sample_count", 0)) != SOURCE_SAMPLE_COUNT:
        raise AnalysisError("projection source_sample_count must be 128")
    if int(document.get("stored_sample_count", 0)) != STORED_SAMPLE_COUNT:
        raise AnalysisError("projection stored_sample_count must be 64")
    if document.get("quantization_range") != [XT_SAMPLE_MIN, XT_SAMPLE_MAX]:
        raise AnalysisError("projection quantization range must be -127..127")
    source_hash = str(document.get("source_reconstructed_wave_set_sha256", ""))
    _require_hash(source_hash, name="source_reconstructed_wave_set_sha256")
    waves = document.get("waves")
    if not isinstance(waves, list) or len(waves) < 2:
        raise AnalysisError("CODE V7-C requires at least two projected waves")
    if len(waves) > DEFAULT_TARGET_SLOT_COUNT:
        raise AnalysisError("CODE V7-C cannot preserve more than 61 structural waves")
    for expected_index, wave in enumerate(waves):
        if not isinstance(wave, Mapping):
            raise AnalysisError("Each projected wave must be a JSON object")
        if int(wave.get("index", -1)) != expected_index:
            raise AnalysisError("projected wave indexes must be contiguous from zero")
        _validated_hashed_document(wave, hash_field="projection_sha256")
        source_samples = _validated_source_samples(
            wave.get("source_samples", ()),
            name=f"wave {expected_index} source_samples",
        )
        selected_phase = int(wave.get("selected_phase_rotation_samples", -1))
        recorded_stored = _validated_stored_samples(
            wave.get("stored_samples", ()),
            name=f"wave {expected_index} stored_samples",
        )
        if _stored_for_phase(source_samples, selected_phase) != recorded_stored:
            raise AnalysisError(f"wave {expected_index} selected phase does not reproduce stored_samples")
        evaluations = wave.get("phase_evaluations")
        if not isinstance(evaluations, list) or len(evaluations) != SOURCE_SAMPLE_COUNT:
            raise AnalysisError(f"wave {expected_index} must contain 128 phase evaluations")
        for phase, evaluation in enumerate(evaluations):
            if not isinstance(evaluation, Mapping):
                raise AnalysisError("phase evaluation must be a JSON object")
            if int(evaluation.get("phase_rotation_samples", -1)) != phase:
                raise AnalysisError("phase evaluations must be ordered 0..127")
            metrics = evaluation.get("metrics")
            if not isinstance(metrics, Mapping):
                raise AnalysisError("phase evaluation metrics must be a JSON object")
            objective = _require_non_negative(
                metrics.get("objective_score", float("nan")),
                name="objective_score",
            )
            if objective > 10.0:
                raise AnalysisError("objective_score is outside a plausible deterministic range")
    return analysis_hash, source_hash, waves


def _phase_candidate_data(
    waves: Sequence[Mapping[str, Any]],
    config: XtTrajectoryConfig,
) -> tuple[list[npt.NDArray[np.float64]], list[npt.NDArray[np.int64]], list[npt.NDArray[np.int64]]]:
    objectives: list[npt.NDArray[np.float64]] = []
    allowed_phases: list[npt.NDArray[np.int64]] = []
    stored_candidates: list[npt.NDArray[np.int64]] = []
    for wave in waves:
        source = _validated_source_samples(wave["source_samples"], name="source_samples")
        objective = np.asarray(
            [
                float(evaluation["metrics"]["objective_score"])
                for evaluation in wave["phase_evaluations"]
            ],
            dtype=np.float64,
        )
        selected_phase = int(wave["selected_phase_rotation_samples"])
        if config.phase_path_policy is XtPhasePathPolicy.PRESERVE:
            allowed = np.asarray([selected_phase], dtype=np.int64)
        else:
            best = float(np.min(objective))
            allowed = np.flatnonzero(
                objective <= best + config.max_objective_increase + _EPSILON
            ).astype(np.int64)
        if allowed.size == 0:
            raise AnalysisError("phase admissibility unexpectedly removed all candidates")
        stored = np.asarray(
            [_stored_for_phase(source, phase) for phase in range(SOURCE_SAMPLE_COUNT)],
            dtype=np.int64,
        )
        objectives.append(objective)
        allowed_phases.append(allowed)
        stored_candidates.append(stored)
    return objectives, allowed_phases, stored_candidates


def _transition_matrix(
    left: npt.NDArray[np.int64],
    right: npt.NDArray[np.int64],
    config: XtTrajectoryConfig,
) -> npt.NDArray[np.float64]:
    left_normalized = left.astype(np.float64) / XT_SAMPLE_MAX
    right_normalized = right.astype(np.float64) / XT_SAMPLE_MAX
    differences = left_normalized[:, None, :] - right_normalized[None, :, :]
    time_distance = np.sqrt(np.mean(np.square(differences), axis=2)) / 2.0

    left_spectra = np.asarray([_normalized_spectrum(row) for row in left], dtype=np.float64)
    right_spectra = np.asarray([_normalized_spectrum(row) for row in right], dtype=np.float64)
    similarity = np.clip(left_spectra @ right_spectra.T, 0.0, 1.0)
    left_zero = np.linalg.norm(left_spectra, axis=1) <= _EPSILON
    right_zero = np.linalg.norm(right_spectra, axis=1) <= _EPSILON
    both_zero = left_zero[:, None] & right_zero[None, :]
    similarity = np.where(both_zero, 1.0, similarity)
    spectral_distance = 1.0 - similarity
    return np.asarray(
        config.transition_time_weight * time_distance
        + config.transition_spectral_weight * spectral_distance,
        dtype=np.float64,
    )


def _optimize_phase_path(
    objectives: Sequence[npt.NDArray[np.float64]],
    allowed_phases: Sequence[npt.NDArray[np.int64]],
    stored_candidates: Sequence[npt.NDArray[np.int64]],
    config: XtTrajectoryConfig,
) -> tuple[tuple[int, ...], float]:
    count = len(objectives)
    local_costs: list[npt.NDArray[np.float64]] = []
    for objective, allowed in zip(objectives, allowed_phases, strict=True):
        best = float(np.min(objective))
        denominator = max(config.max_objective_increase, _EPSILON)
        local = np.clip((objective[allowed] - best) / denominator, 0.0, 1.0)
        local_costs.append(np.asarray(config.local_fidelity_weight * local, dtype=np.float64))

    costs = local_costs[0].copy()
    backpointers: list[npt.NDArray[np.int64]] = []
    for index in range(count - 1):
        left_allowed = allowed_phases[index]
        right_allowed = allowed_phases[index + 1]
        matrix = _transition_matrix(
            stored_candidates[index][left_allowed],
            stored_candidates[index + 1][right_allowed],
            config,
        )
        combined = costs[:, None] + config.transition_weight * matrix
        previous_choice = np.argmin(combined, axis=0).astype(np.int64)
        next_costs = combined[previous_choice, np.arange(right_allowed.size)] + local_costs[index + 1]
        backpointers.append(previous_choice)
        costs = np.asarray(next_costs, dtype=np.float64)

    final_index = int(np.argmin(costs))
    selected_indexes = [final_index]
    for backpointer in reversed(backpointers):
        selected_indexes.append(int(backpointer[selected_indexes[-1]]))
    selected_indexes.reverse()
    phases = tuple(
        int(allowed[index])
        for allowed, index in zip(allowed_phases, selected_indexes, strict=True)
    )
    return phases, float(costs[final_index])


def _allocate_intermediates(
    distances: Sequence[float],
    *,
    anchor_count: int,
    config: XtTrajectoryConfig,
) -> tuple[int, ...]:
    transition_count = anchor_count - 1
    extra_slots = config.target_slot_count - anchor_count
    minimum_total = config.minimum_intermediates_per_transition * transition_count
    if minimum_total > extra_slots:
        raise AnalysisError(
            "minimum_intermediates_per_transition cannot fit inside target_slot_count"
        )
    allocations = np.full(
        transition_count,
        config.minimum_intermediates_per_transition,
        dtype=np.int64,
    )
    remaining = extra_slots - minimum_total
    if remaining == 0:
        return tuple(int(value) for value in allocations)
    weights = np.power(np.maximum(np.asarray(distances, dtype=np.float64), _EPSILON), config.spacing_power)
    if float(np.sum(weights, dtype=np.float64)) <= _EPSILON:
        weights = np.ones(transition_count, dtype=np.float64)
    quotas = remaining * weights / float(np.sum(weights, dtype=np.float64))
    floors = np.floor(quotas).astype(np.int64)
    allocations += floors
    leftovers = int(remaining - int(np.sum(floors, dtype=np.int64)))
    fractions = quotas - floors
    order = sorted(
        range(transition_count),
        key=lambda index: (-float(fractions[index]), -float(weights[index]), index),
    )
    for index in order[:leftovers]:
        allocations[index] += 1
    return tuple(int(value) for value in allocations)


def _curve_fraction(value: float, curve: XtInterpolationCurve) -> float:
    if curve is XtInterpolationCurve.LINEAR:
        return float(value)
    return float(value * value * (3.0 - 2.0 * value))


def build_xt_wavetable_trajectory_document(
    document: Mapping[str, Any],
    *,
    config: XtTrajectoryConfig | None = None,
    tool_version: str = __version__,
) -> XtWavetableTrajectory:
    selected_config = XtTrajectoryConfig() if config is None else config
    projection_hash, source_hash, waves = _validate_projection_document(document)
    if len(waves) > selected_config.target_slot_count:
        raise AnalysisError("target_slot_count cannot preserve every structural wave")

    objectives, allowed_phases, stored_candidates = _phase_candidate_data(waves, selected_config)
    selected_phases, path_cost = _optimize_phase_path(
        objectives,
        allowed_phases,
        stored_candidates,
        selected_config,
    )

    anchors: list[XtTrajectoryAnchor] = []
    for index, (wave, phase) in enumerate(zip(waves, selected_phases, strict=True)):
        original_phase = int(wave["selected_phase_rotation_samples"])
        original_objective = float(objectives[index][original_phase])
        selected_objective = float(objectives[index][phase])
        stored = tuple(int(value) for value in stored_candidates[index][phase])
        anchors.append(
            XtTrajectoryAnchor(
                anchor_index=index,
                source_wave_index=int(wave["index"]),
                candidate_index=int(wave["candidate_index"]),
                source_projection_sha256=str(wave["projection_sha256"]),
                original_phase_rotation_samples=original_phase,
                selected_phase_rotation_samples=phase,
                original_objective_score=original_objective,
                selected_objective_score=selected_objective,
                objective_increase=max(0.0, selected_objective - original_objective),
                admissible_phase_count=int(allowed_phases[index].size),
                stored_samples=stored,
                reconstructed_samples=reconstruct_xt_native(stored),
            )
        )

    transition_components: list[tuple[float, float, float]] = []
    for left, right in zip(anchors, anchors[1:]):
        time_distance = _stored_distance(left.stored_samples, right.stored_samples)
        spectral_distance = _spectral_distance(left.stored_samples, right.stored_samples)
        combined = (
            selected_config.transition_time_weight * time_distance
            + selected_config.transition_spectral_weight * spectral_distance
        )
        transition_components.append((time_distance, spectral_distance, float(combined)))

    allocations = _allocate_intermediates(
        [item[2] for item in transition_components],
        anchor_count=len(anchors),
        config=selected_config,
    )
    transitions = tuple(
        XtTrajectoryTransition(
            transition_index=index,
            left_anchor_index=index,
            right_anchor_index=index + 1,
            stored_distance=components[0],
            spectral_distance=components[1],
            combined_distance=components[2],
            allocated_intermediate_count=allocations[index],
        )
        for index, components in enumerate(transition_components)
    )

    slots: list[XtTrajectorySlot] = []
    slot_number = 1
    first = anchors[0]
    slots.append(
        XtTrajectorySlot(
            slot_number=slot_number,
            kind=XtTrajectorySlotKind.ANCHOR,
            left_anchor_index=0,
            right_anchor_index=0,
            position_fraction=0.0,
            blend_fraction=0.0,
            source_wave_index=first.source_wave_index,
            stored_samples=first.stored_samples,
            reconstructed_samples=first.reconstructed_samples,
        )
    )
    for transition in transitions:
        left = anchors[transition.left_anchor_index]
        right = anchors[transition.right_anchor_index]
        count = transition.allocated_intermediate_count
        for step in range(1, count + 1):
            position_fraction = step / (count + 1)
            blend_fraction = _curve_fraction(
                position_fraction,
                selected_config.interpolation_curve,
            )
            stored = _interpolate_stored(
                left.stored_samples,
                right.stored_samples,
                blend_fraction,
            )
            slot_number += 1
            slots.append(
                XtTrajectorySlot(
                    slot_number=slot_number,
                    kind=XtTrajectorySlotKind.INTERPOLATED,
                    left_anchor_index=left.anchor_index,
                    right_anchor_index=right.anchor_index,
                    position_fraction=float(position_fraction),
                    blend_fraction=float(blend_fraction),
                    source_wave_index=None,
                    stored_samples=stored,
                    reconstructed_samples=reconstruct_xt_native(stored),
                )
            )
        slot_number += 1
        slots.append(
            XtTrajectorySlot(
                slot_number=slot_number,
                kind=XtTrajectorySlotKind.ANCHOR,
                left_anchor_index=right.anchor_index,
                right_anchor_index=right.anchor_index,
                position_fraction=1.0,
                blend_fraction=1.0,
                source_wave_index=right.source_wave_index,
                stored_samples=right.stored_samples,
                reconstructed_samples=right.reconstructed_samples,
            )
        )

    return XtWavetableTrajectory(
        schema_version=TRAJECTORY_SCHEMA_VERSION,
        tool_version=tool_version,
        source_projection_set_sha256=projection_hash,
        source_reconstructed_wave_set_sha256=source_hash,
        config=selected_config,
        anchors=tuple(anchors),
        transitions=transitions,
        slots=tuple(slots),
        phase_path_cost=path_cost,
        decision_reason=(
            "All V7-B structural waves were preserved in source order. A deterministic "
            "global phase path was selected within the configured per-wave fidelity bound, "
            "then the remaining editable XT positions were allocated adaptively according "
            "to adjacent stored-domain and spectral distance. Intermediate waves were "
            "quantized directly in the safe 64-value XT domain."
        ),
    )


def load_and_build_xt_wavetable_trajectory(
    path: str | Path,
    *,
    config: XtTrajectoryConfig | None = None,
    tool_version: str = __version__,
) -> XtWavetableTrajectory:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Unable to read CODE V7-B projection JSON: {source}") from exc
    if not isinstance(document, Mapping):
        raise AnalysisError("CODE V7-B projection JSON root must be an object")
    return build_xt_wavetable_trajectory_document(
        document,
        config=config,
        tool_version=tool_version,
    )
