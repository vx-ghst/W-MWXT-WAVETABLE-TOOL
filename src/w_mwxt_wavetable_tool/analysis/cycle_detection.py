from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any

import numpy as np
import numpy.typing as npt

from ..version import __version__
from .framing import validate_mono_samples
from .repitch import WorkingPitchPolicy, plan_working_pitch
from .segmentation import AttackPolicy, segment_source
from .signal import analyze_audio_source_signal


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _require_positive(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _require_non_negative(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if result < 0.0:
        raise ValueError(f"{name} must not be negative")
    return result


def _require_ratio(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def _canonical_sha256(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


def _sample_sha256(samples: npt.NDArray[np.float64]) -> str:
    canonical = samples.astype("<f8", copy=False).tobytes(order="C")
    return sha256(canonical).hexdigest()


def _clamp_ratio(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


class CycleCandidateStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CycleCandidate:
    index: int
    segment_index: int
    local_index: int
    start_sample: int
    end_sample: int
    sample_rate: int
    source_segment_sha256: str
    expected_source_period_samples: float
    cycle_length_samples: int
    period_error_samples: float
    period_error_ratio: float
    waveform_rms: float
    peak_amplitude: float
    periodicity_score: float
    seam_value_error: float
    seam_slope_error: float
    seam_score: float
    energy_consistency_score: float
    spectral_consistency_score: float
    composite_score: float
    status: CycleCandidateStatus
    rejection_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.index < 0 or self.segment_index < 0 or self.local_index < 0:
            raise ValueError("candidate indexes must not be negative")
        if self.start_sample < 0 or self.end_sample <= self.start_sample:
            raise ValueError("candidate sample bounds are invalid")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if not _hash_is_valid(self.source_segment_sha256):
            raise ValueError("source_segment_sha256 must be a lowercase SHA-256 digest")
        _require_positive(
            self.expected_source_period_samples,
            name="expected_source_period_samples",
        )
        if self.cycle_length_samples <= 1:
            raise ValueError("cycle_length_samples must be greater than one")
        if self.end_sample - self.start_sample != self.cycle_length_samples:
            raise ValueError("cycle length does not match candidate bounds")
        for name in (
            "period_error_samples",
            "period_error_ratio",
            "waveform_rms",
            "peak_amplitude",
            "seam_value_error",
            "seam_slope_error",
        ):
            _require_non_negative(getattr(self, name), name=name)
        for name in (
            "periodicity_score",
            "seam_score",
            "energy_consistency_score",
            "spectral_consistency_score",
            "composite_score",
        ):
            _require_ratio(getattr(self, name), name=name)
        if not isinstance(self.status, CycleCandidateStatus):
            raise ValueError("status must be a CycleCandidateStatus")
        if tuple(dict.fromkeys(self.rejection_reasons)) != self.rejection_reasons:
            raise ValueError("rejection_reasons must be unique and ordered")
        if any(not reason for reason in self.rejection_reasons):
            raise ValueError("rejection reasons must not be empty")
        if self.status is CycleCandidateStatus.ACCEPTED and self.rejection_reasons:
            raise ValueError("accepted candidates cannot expose rejection reasons")
        if self.status is CycleCandidateStatus.REJECTED and not self.rejection_reasons:
            raise ValueError("rejected candidates require at least one rejection reason")

    @property
    def start_seconds(self) -> float:
        return float(self.start_sample / self.sample_rate)

    @property
    def end_seconds(self) -> float:
        return float(self.end_sample / self.sample_rate)

    @property
    def duration_seconds(self) -> float:
        return float(self.cycle_length_samples / self.sample_rate)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "segment_index": self.segment_index,
            "local_index": self.local_index,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "sample_rate": self.sample_rate,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration_seconds": self.duration_seconds,
            "source_segment_sha256": self.source_segment_sha256,
            "expected_source_period_samples": self.expected_source_period_samples,
            "cycle_length_samples": self.cycle_length_samples,
            "period_error_samples": self.period_error_samples,
            "period_error_ratio": self.period_error_ratio,
            "waveform_rms": self.waveform_rms,
            "peak_amplitude": self.peak_amplitude,
            "periodicity_score": self.periodicity_score,
            "seam_value_error": self.seam_value_error,
            "seam_slope_error": self.seam_slope_error,
            "seam_score": self.seam_score,
            "energy_consistency_score": self.energy_consistency_score,
            "spectral_consistency_score": self.spectral_consistency_score,
            "composite_score": self.composite_score,
            "status": self.status.value,
            "rejection_reasons": list(self.rejection_reasons),
        }

    @property
    def candidate_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["candidate_sha256"] = self.candidate_sha256
        return result


@dataclass(frozen=True, slots=True)
class CycleDiscoveryAnalysis:
    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    segmentation_analysis_sha256: str
    working_pitch_plan_sha256: str
    working_frequency_hz: float | None
    working_period_samples: float | None
    source_period_samples: float | None
    repitch_ratio: float | None
    repitch_required: bool
    period_search_radius_ratio: float
    boundary_search_radius_samples: int
    maximum_cycles_per_segment: int
    minimum_periodicity_score: float
    minimum_seam_score: float
    minimum_energy_consistency_score: float
    minimum_spectral_consistency_score: float
    usable_segment_indices: tuple[int, ...]
    usable_segment_sha256: tuple[str, ...]
    analyzed_segment_indices: tuple[int, ...]
    skipped_segment_indices: tuple[int, ...]
    candidates: tuple[CycleCandidate, ...]
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported cycle-discovery schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise ValueError("tool_version must be a non-empty normalized string")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "segmentation_analysis_sha256",
            "working_pitch_plan_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        _require_ratio(
            self.period_search_radius_ratio,
            name="period_search_radius_ratio",
        )
        if self.period_search_radius_ratio <= 0.0:
            raise ValueError("period_search_radius_ratio must be positive")
        if self.boundary_search_radius_samples < 0:
            raise ValueError("boundary_search_radius_samples must not be negative")
        if not 1 <= self.maximum_cycles_per_segment <= 1024:
            raise ValueError("maximum_cycles_per_segment must be between 1 and 1024")
        for name in (
            "minimum_periodicity_score",
            "minimum_seam_score",
            "minimum_energy_consistency_score",
            "minimum_spectral_consistency_score",
        ):
            _require_ratio(getattr(self, name), name=name)
        if len(self.usable_segment_indices) != len(self.usable_segment_sha256):
            raise ValueError("usable segment indexes and hashes must have equal length")
        if tuple(sorted(set(self.usable_segment_indices))) != self.usable_segment_indices:
            raise ValueError("usable_segment_indices must be sorted and unique")
        if any(not _hash_is_valid(value) for value in self.usable_segment_sha256):
            raise ValueError("usable segment hashes must be lowercase SHA-256 digests")
        usable = set(self.usable_segment_indices)
        analyzed = set(self.analyzed_segment_indices)
        skipped = set(self.skipped_segment_indices)
        if tuple(sorted(analyzed)) != self.analyzed_segment_indices:
            raise ValueError("analyzed_segment_indices must be sorted and unique")
        if tuple(sorted(skipped)) != self.skipped_segment_indices:
            raise ValueError("skipped_segment_indices must be sorted and unique")
        if analyzed & skipped or analyzed | skipped != usable:
            raise ValueError("analyzed and skipped segments must partition usable segments")
        if tuple(candidate.index for candidate in self.candidates) != tuple(
            range(len(self.candidates))
        ):
            raise ValueError("candidate indexes must be contiguous from zero")
        segment_hashes = dict(zip(self.usable_segment_indices, self.usable_segment_sha256))
        local_indexes: dict[int, list[int]] = {}
        for candidate in self.candidates:
            if candidate.sample_rate != self.sample_rate:
                raise ValueError("candidate sample rate is inconsistent")
            if candidate.end_sample > self.sample_count:
                raise ValueError("candidate exceeds the source sample range")
            if candidate.segment_index not in analyzed:
                raise ValueError("candidate must belong to an analyzed segment")
            if candidate.source_segment_sha256 != segment_hashes[candidate.segment_index]:
                raise ValueError("candidate segment hash is inconsistent")
            local_indexes.setdefault(candidate.segment_index, []).append(candidate.local_index)
        for indexes in local_indexes.values():
            if tuple(indexes) != tuple(range(len(indexes))):
                raise ValueError("candidate local indexes must be contiguous per segment")
        pitch_values = (
            self.working_frequency_hz,
            self.working_period_samples,
            self.source_period_samples,
            self.repitch_ratio,
        )
        if any(value is None for value in pitch_values):
            if any(value is not None for value in pitch_values):
                raise ValueError("working-pitch metadata must be fully defined or absent")
            if self.candidates or self.analyzed_segment_indices:
                raise ValueError("pitch-unavailable analysis cannot expose cycle candidates")
        else:
            for name, value in zip(
                (
                    "working_frequency_hz",
                    "working_period_samples",
                    "source_period_samples",
                    "repitch_ratio",
                ),
                pitch_values,
            ):
                _require_positive(value, name=name)
        if not self.decision_reason:
            raise ValueError("decision_reason must not be empty")

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def candidate_sha256(self) -> tuple[str, ...]:
        return tuple(candidate.candidate_sha256 for candidate in self.candidates)

    @property
    def accepted_candidate_indices(self) -> tuple[int, ...]:
        return tuple(
            candidate.index
            for candidate in self.candidates
            if candidate.status is CycleCandidateStatus.ACCEPTED
        )

    @property
    def accepted_candidate_count(self) -> int:
        return len(self.accepted_candidate_indices)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "segmentation_analysis_sha256": self.segmentation_analysis_sha256,
            "working_pitch_plan_sha256": self.working_pitch_plan_sha256,
            "working_frequency_hz": self.working_frequency_hz,
            "working_period_samples": self.working_period_samples,
            "source_period_samples": self.source_period_samples,
            "repitch_ratio": self.repitch_ratio,
            "repitch_required": self.repitch_required,
            "period_search_radius_ratio": self.period_search_radius_ratio,
            "boundary_search_radius_samples": self.boundary_search_radius_samples,
            "maximum_cycles_per_segment": self.maximum_cycles_per_segment,
            "minimum_periodicity_score": self.minimum_periodicity_score,
            "minimum_seam_score": self.minimum_seam_score,
            "minimum_energy_consistency_score": self.minimum_energy_consistency_score,
            "minimum_spectral_consistency_score": self.minimum_spectral_consistency_score,
            "usable_segment_indices": list(self.usable_segment_indices),
            "usable_segment_sha256": list(self.usable_segment_sha256),
            "analyzed_segment_indices": list(self.analyzed_segment_indices),
            "skipped_segment_indices": list(self.skipped_segment_indices),
            "candidate_count": self.candidate_count,
            "candidate_sha256": list(self.candidate_sha256),
            "accepted_candidate_count": self.accepted_candidate_count,
            "accepted_candidate_indices": list(self.accepted_candidate_indices),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "decision_reason": self.decision_reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _normalized_correlation(left: np.ndarray, right: np.ndarray) -> float:
    left_centered = left - float(np.mean(left, dtype=np.float64))
    right_centered = right - float(np.mean(right, dtype=np.float64))
    denominator = float(
        np.linalg.norm(left_centered) * np.linalg.norm(right_centered)
    )
    if denominator <= 1.0e-24:
        return 1.0 if np.array_equal(left, right) else 0.0
    return _clamp_ratio(float(np.dot(left_centered, right_centered) / denominator))


def _spectral_consistency(left: np.ndarray, right: np.ndarray) -> float:
    window = np.hanning(left.size)
    left_magnitude = np.abs(np.fft.rfft(left * window))
    right_magnitude = np.abs(np.fft.rfft(right * window))
    denominator = float(np.linalg.norm(left_magnitude) * np.linalg.norm(right_magnitude))
    if denominator <= 1.0e-24:
        return 1.0 if np.array_equal(left, right) else 0.0
    return _clamp_ratio(float(np.dot(left_magnitude, right_magnitude) / denominator))


def _energy_consistency(left: np.ndarray, right: np.ndarray) -> tuple[float, float, float]:
    left_rms = float(np.sqrt(np.mean(np.square(left), dtype=np.float64)))
    right_rms = float(np.sqrt(np.mean(np.square(right), dtype=np.float64)))
    maximum = max(left_rms, right_rms)
    score = 1.0 if maximum <= 1.0e-24 else float(min(left_rms, right_rms) / maximum)
    return _clamp_ratio(score), left_rms, right_rms


def _seam_metrics(cycle: np.ndarray) -> tuple[float, float, float]:
    differences = np.diff(cycle)
    scale = max(
        float(np.max(np.abs(cycle))),
        float(np.sqrt(np.mean(np.square(cycle), dtype=np.float64))),
        1.0e-12,
    )
    if differences.size == 0:
        return 1.0, 1.0, 0.0
    typical_step = float(np.quantile(np.abs(differences), 0.75))
    seam_step = float(cycle[0] - cycle[-1])
    value_error = float(max(0.0, abs(seam_step) - typical_step) / scale)
    boundary_reference = float((differences[0] + differences[-1]) / 2.0)
    slope_error = float(abs(seam_step - boundary_reference) / scale)
    seam_score = _clamp_ratio(math.exp(-(value_error + slope_error)))
    return value_error, slope_error, seam_score


def _candidate_metrics(
    data: np.ndarray,
    *,
    start: int,
    period: int,
    expected_period: float,
) -> dict[str, float]:
    cycle = data[start : start + period]
    following = data[start + period : start + 2 * period]
    periodicity = _normalized_correlation(cycle, following)
    spectral = _spectral_consistency(cycle, following)
    energy, waveform_rms, _ = _energy_consistency(cycle, following)
    seam_value, seam_slope, seam = _seam_metrics(cycle)
    peak = float(np.max(np.abs(cycle)))
    period_error = float(abs(period - expected_period))
    period_error_ratio = float(period_error / expected_period)
    period_fit = _clamp_ratio(1.0 - period_error_ratio)
    composite = _clamp_ratio(
        0.30 * periodicity
        + 0.25 * seam
        + 0.20 * spectral
        + 0.15 * energy
        + 0.10 * period_fit
    )
    return {
        "period_error_samples": period_error,
        "period_error_ratio": period_error_ratio,
        "waveform_rms": waveform_rms,
        "peak_amplitude": peak,
        "periodicity_score": periodicity,
        "seam_value_error": seam_value,
        "seam_slope_error": seam_slope,
        "seam_score": seam,
        "energy_consistency_score": energy,
        "spectral_consistency_score": spectral,
        "composite_score": composite,
    }


def _anchor_cycle_numbers(total_cycles: int, maximum_count: int) -> tuple[int, ...]:
    if total_cycles <= 0:
        return ()
    if total_cycles <= maximum_count:
        return tuple(range(total_cycles))
    values = np.linspace(0.0, float(total_cycles - 1), num=maximum_count)
    result = tuple(sorted({int(round(value)) for value in values}))
    if len(result) == maximum_count:
        return result
    missing = [index for index in range(total_cycles) if index not in result]
    return tuple(sorted((*result, *missing[: maximum_count - len(result)])))


def _period_candidates(
    minimum_period: int,
    maximum_period: int,
    expected_period: float,
    *,
    maximum_count: int = 33,
) -> tuple[int, ...]:
    count = maximum_period - minimum_period + 1
    if count <= maximum_count:
        return tuple(range(minimum_period, maximum_period + 1))
    values = np.linspace(
        float(minimum_period),
        float(maximum_period),
        num=maximum_count,
    )
    selected = {int(round(value)) for value in values}
    selected.add(max(minimum_period, min(maximum_period, int(round(expected_period)))))
    return tuple(sorted(selected))


def _best_candidate_window(
    data: np.ndarray,
    *,
    anchor_start: int,
    segment_start: int,
    segment_end: int,
    expected_period: float,
    minimum_period: int,
    maximum_period: int,
    boundary_radius: int,
) -> tuple[int, int, dict[str, float]] | None:
    choices: list[tuple[float, float, int, int, dict[str, float]]] = []
    for start in range(
        max(segment_start, anchor_start - boundary_radius),
        min(segment_end, anchor_start + boundary_radius) + 1,
    ):
        for period in _period_candidates(
            minimum_period,
            maximum_period,
            expected_period,
        ):
            if start + 2 * period > segment_end:
                continue
            metrics = _candidate_metrics(
                data,
                start=start,
                period=period,
                expected_period=expected_period,
            )
            choices.append(
                (
                    -metrics["composite_score"],
                    metrics["period_error_samples"],
                    start,
                    period,
                    metrics,
                )
            )
    if not choices:
        return None
    _, _, start, period, metrics = min(choices, key=lambda item: item[:4])
    return start, period, metrics


def discover_cycles(
    samples: npt.ArrayLike,
    segmentation_analysis: Any,
    working_pitch_plan: Any,
    *,
    period_search_radius_ratio: float = 0.125,
    boundary_search_radius_samples: int = 4,
    maximum_cycles_per_segment: int = 64,
    minimum_periodicity_score: float = 0.75,
    minimum_seam_score: float = 0.45,
    minimum_energy_consistency_score: float = 0.50,
    minimum_spectral_consistency_score: float = 0.70,
    tool_version: str = __version__,
) -> CycleDiscoveryAnalysis:
    """Discover deterministic source-domain cycles and measure their quality."""

    data = validate_mono_samples(samples)
    radius_ratio = _require_ratio(
        period_search_radius_ratio,
        name="period_search_radius_ratio",
    )
    if radius_ratio <= 0.0:
        raise ValueError("period_search_radius_ratio must be positive")
    if not isinstance(boundary_search_radius_samples, int) or boundary_search_radius_samples < 0:
        raise ValueError("boundary_search_radius_samples must be a non-negative integer")
    if not isinstance(maximum_cycles_per_segment, int) or not 1 <= maximum_cycles_per_segment <= 1024:
        raise ValueError("maximum_cycles_per_segment must be an integer between 1 and 1024")
    periodicity_gate = _require_ratio(
        minimum_periodicity_score,
        name="minimum_periodicity_score",
    )
    seam_gate = _require_ratio(minimum_seam_score, name="minimum_seam_score")
    energy_gate = _require_ratio(
        minimum_energy_consistency_score,
        name="minimum_energy_consistency_score",
    )
    spectral_gate = _require_ratio(
        minimum_spectral_consistency_score,
        name="minimum_spectral_consistency_score",
    )
    if not tool_version or tool_version.strip() != tool_version:
        raise ValueError("tool_version must be a non-empty normalized string")

    sample_rate = int(segmentation_analysis.sample_rate)
    sample_count = int(segmentation_analysis.sample_count)
    sample_hash = _sample_sha256(data)
    if sample_rate <= 0 or sample_count != data.size:
        raise ValueError("segmentation sample identity is inconsistent with samples")
    if sample_hash != segmentation_analysis.sample_sha256:
        raise ValueError("segmentation sample hash is inconsistent with samples")
    for name in ("sample_rate", "sample_count", "sample_sha256"):
        if getattr(working_pitch_plan, name) != getattr(segmentation_analysis, name):
            raise ValueError("working-pitch plan identity is inconsistent with segmentation")
    if segmentation_analysis.working_pitch_plan_sha256 != working_pitch_plan.analysis_sha256:
        raise ValueError("segmentation does not link to the working-pitch plan")
    if segmentation_analysis.working_frequency_hz != working_pitch_plan.target_frequency_hz:
        raise ValueError("segmentation working frequency is inconsistent")
    if segmentation_analysis.working_period_samples != working_pitch_plan.target_period_samples:
        raise ValueError("segmentation working period is inconsistent")
    if bool(segmentation_analysis.repitch_required) != bool(working_pitch_plan.repitch_required):
        raise ValueError("segmentation repitch requirement is inconsistent")

    usable_indexes = tuple(int(index) for index in segmentation_analysis.usable_segment_indices)
    segments = tuple(segmentation_analysis.segments)
    if any(index < 0 or index >= len(segments) for index in usable_indexes):
        raise ValueError("usable segment index is outside the segmentation range")
    usable_hashes = tuple(str(segments[index].segment_sha256) for index in usable_indexes)

    target_period = working_pitch_plan.target_period_samples
    repitch_ratio = working_pitch_plan.repitch_ratio
    if target_period is None or repitch_ratio is None:
        return CycleDiscoveryAnalysis(
            schema_version=1,
            tool_version=tool_version,
            sample_rate=sample_rate,
            sample_count=sample_count,
            sample_sha256=sample_hash,
            segmentation_analysis_sha256=segmentation_analysis.analysis_sha256,
            working_pitch_plan_sha256=working_pitch_plan.analysis_sha256,
            working_frequency_hz=None,
            working_period_samples=None,
            source_period_samples=None,
            repitch_ratio=None,
            repitch_required=bool(working_pitch_plan.repitch_required),
            period_search_radius_ratio=radius_ratio,
            boundary_search_radius_samples=boundary_search_radius_samples,
            maximum_cycles_per_segment=maximum_cycles_per_segment,
            minimum_periodicity_score=periodicity_gate,
            minimum_seam_score=seam_gate,
            minimum_energy_consistency_score=energy_gate,
            minimum_spectral_consistency_score=spectral_gate,
            usable_segment_indices=usable_indexes,
            usable_segment_sha256=usable_hashes,
            analyzed_segment_indices=(),
            skipped_segment_indices=usable_indexes,
            candidates=(),
            decision_reason=(
                "No working pitch is available, so source-domain cycle discovery is "
                "deferred to a later non-periodic reconstruction route."
            ),
        )

    working_frequency = _require_positive(
        working_pitch_plan.target_frequency_hz,
        name="working_frequency_hz",
    )
    working_period = _require_positive(target_period, name="working_period_samples")
    ratio = _require_positive(repitch_ratio, name="repitch_ratio")
    source_period = _require_positive(
        working_period * ratio,
        name="source_period_samples",
    )
    minimum_period = max(2, int(math.floor(source_period * (1.0 - radius_ratio))))
    maximum_period = max(
        minimum_period,
        int(math.ceil(source_period * (1.0 + radius_ratio))),
    )

    candidates: list[CycleCandidate] = []
    analyzed: list[int] = []
    skipped: list[int] = []
    for segment_index, segment_hash in zip(usable_indexes, usable_hashes):
        segment = segments[segment_index]
        start = int(segment.start_sample)
        end = int(segment.end_sample)
        available_cycles = int(math.floor((end - start) / source_period)) - 1
        cycle_numbers = _anchor_cycle_numbers(
            available_cycles,
            maximum_cycles_per_segment,
        )
        if not cycle_numbers or end - start < 2 * minimum_period:
            skipped.append(segment_index)
            continue
        local_candidates: list[CycleCandidate] = []
        seen_bounds: set[tuple[int, int]] = set()
        for cycle_number in cycle_numbers:
            anchor = start + int(round(cycle_number * source_period))
            selected = _best_candidate_window(
                data,
                anchor_start=anchor,
                segment_start=start,
                segment_end=end,
                expected_period=source_period,
                minimum_period=minimum_period,
                maximum_period=maximum_period,
                boundary_radius=boundary_search_radius_samples,
            )
            if selected is None:
                continue
            selected_start, period, metrics = selected
            bounds = (selected_start, selected_start + period)
            if bounds in seen_bounds:
                continue
            seen_bounds.add(bounds)
            reasons: list[str] = []
            if metrics["periodicity_score"] < periodicity_gate:
                reasons.append("periodicity_below_gate")
            if metrics["seam_score"] < seam_gate:
                reasons.append("seam_below_gate")
            if metrics["energy_consistency_score"] < energy_gate:
                reasons.append("energy_consistency_below_gate")
            if metrics["spectral_consistency_score"] < spectral_gate:
                reasons.append("spectral_consistency_below_gate")
            status = (
                CycleCandidateStatus.ACCEPTED
                if not reasons
                else CycleCandidateStatus.REJECTED
            )
            local_candidates.append(
                CycleCandidate(
                    index=len(candidates) + len(local_candidates),
                    segment_index=segment_index,
                    local_index=len(local_candidates),
                    start_sample=selected_start,
                    end_sample=selected_start + period,
                    sample_rate=sample_rate,
                    source_segment_sha256=segment_hash,
                    expected_source_period_samples=source_period,
                    cycle_length_samples=period,
                    period_error_samples=metrics["period_error_samples"],
                    period_error_ratio=metrics["period_error_ratio"],
                    waveform_rms=metrics["waveform_rms"],
                    peak_amplitude=metrics["peak_amplitude"],
                    periodicity_score=metrics["periodicity_score"],
                    seam_value_error=metrics["seam_value_error"],
                    seam_slope_error=metrics["seam_slope_error"],
                    seam_score=metrics["seam_score"],
                    energy_consistency_score=metrics["energy_consistency_score"],
                    spectral_consistency_score=metrics["spectral_consistency_score"],
                    composite_score=metrics["composite_score"],
                    status=status,
                    rejection_reasons=tuple(reasons),
                )
            )
        if local_candidates:
            analyzed.append(segment_index)
            candidates.extend(local_candidates)
        else:
            skipped.append(segment_index)

    accepted_count = sum(
        candidate.status is CycleCandidateStatus.ACCEPTED
        for candidate in candidates
    )
    if not candidates:
        reason = "No usable segment contained two complete cycles inside the configured period search range."
    elif accepted_count:
        reason = (
            f"Discovered {len(candidates)} source-domain cycle candidates; "
            f"{accepted_count} satisfy every configured quality gate."
        )
    else:
        reason = (
            f"Discovered {len(candidates)} source-domain cycle candidates, but none "
            "satisfy every configured quality gate."
        )

    return CycleDiscoveryAnalysis(
        schema_version=1,
        tool_version=tool_version,
        sample_rate=sample_rate,
        sample_count=sample_count,
        sample_sha256=sample_hash,
        segmentation_analysis_sha256=segmentation_analysis.analysis_sha256,
        working_pitch_plan_sha256=working_pitch_plan.analysis_sha256,
        working_frequency_hz=working_frequency,
        working_period_samples=working_period,
        source_period_samples=source_period,
        repitch_ratio=ratio,
        repitch_required=bool(working_pitch_plan.repitch_required),
        period_search_radius_ratio=radius_ratio,
        boundary_search_radius_samples=boundary_search_radius_samples,
        maximum_cycles_per_segment=maximum_cycles_per_segment,
        minimum_periodicity_score=periodicity_gate,
        minimum_seam_score=seam_gate,
        minimum_energy_consistency_score=energy_gate,
        minimum_spectral_consistency_score=spectral_gate,
        usable_segment_indices=usable_indexes,
        usable_segment_sha256=usable_hashes,
        analyzed_segment_indices=tuple(analyzed),
        skipped_segment_indices=tuple(skipped),
        candidates=tuple(candidates),
        decision_reason=reason,
    )


def analyze_audio_source_cycles(
    source: Any,
    *,
    working_pitch_policy: WorkingPitchPolicy | str = WorkingPitchPolicy.AUTO,
    locked_frequency_hz: float | None = None,
    attack_policy: AttackPolicy | str = AttackPolicy.AUTO,
    **cycle_kwargs: float | int | str,
) -> CycleDiscoveryAnalysis:
    """Run the canonical V6-A, V6-B, and V6-C analysis chain for one source."""

    signal_analysis = analyze_audio_source_signal(source)
    working_pitch_plan = plan_working_pitch(
        signal_analysis.pitch_periodicity_analysis,
        policy=working_pitch_policy,
        locked_frequency_hz=locked_frequency_hz,
    )
    segmentation_analysis = segment_source(
        signal_analysis,
        working_pitch_plan,
        attack_policy=attack_policy,
    )
    return discover_cycles(
        source.mono_samples,
        segmentation_analysis,
        working_pitch_plan,
        **cycle_kwargs,
    )
