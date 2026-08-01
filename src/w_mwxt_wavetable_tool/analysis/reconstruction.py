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
from .cycle_detection import CycleDiscoveryAnalysis, analyze_audio_source_cycles
from .cycle_selection import (
    CycleSelectionDecision,
    CycleSelectionPolicy,
    SelectedCycleSet,
    select_representative_cycles,
)
from .framing import validate_mono_samples
from .repitch import WorkingPitchPolicy
from .segmentation import AttackPolicy


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


class ReconstructionStrategy(str, Enum):
    AUTO = "auto"
    SPECTRAL = "spectral"
    PARTIAL = "partial"
    HYBRID = "hybrid"


class ReconstructionDecision(str, Enum):
    RECONSTRUCTED = "reconstructed"
    NO_SELECTED_CYCLES = "no_selected_cycles"


@dataclass(frozen=True, slots=True)
class ReconstructedWave:
    index: int
    candidate_index: int
    candidate_sha256: str
    ranking_sha256: str
    segment_index: int
    source_start_sample: int
    source_end_sample: int
    source_cycle_sha256: str
    strategy: ReconstructionStrategy
    target_sample_count: int
    maximum_partials: int
    available_harmonic_bin_count: int
    retained_harmonic_bin_count: int
    remove_dc: bool
    hybrid_time_weight: float
    normalization_peak: float
    normalization_gain: float
    source_rms: float
    reconstructed_rms: float
    peak_amplitude: float
    seam_value_error: float
    seam_slope_error: float
    seam_score: float
    spectral_similarity_score: float
    samples: tuple[float, ...]
    decision_reason: str

    def __post_init__(self) -> None:
        if self.index < 0 or self.candidate_index < 0 or self.segment_index < 0:
            raise ValueError("wave and candidate indexes must not be negative")
        if self.source_start_sample < 0 or self.source_end_sample <= self.source_start_sample:
            raise ValueError("source cycle bounds are invalid")
        for name in (
            "candidate_sha256",
            "ranking_sha256",
            "source_cycle_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if self.strategy is ReconstructionStrategy.AUTO:
            raise ValueError("individual reconstructed waves require a concrete strategy")
        if self.target_sample_count < 16 or self.target_sample_count > 4096:
            raise ValueError("target_sample_count must be between 16 and 4096")
        if self.maximum_partials <= 0:
            raise ValueError("maximum_partials must be positive")
        if self.available_harmonic_bin_count < 0:
            raise ValueError("available_harmonic_bin_count must not be negative")
        if not 0 <= self.retained_harmonic_bin_count <= self.available_harmonic_bin_count:
            raise ValueError("retained harmonic bin count is outside the available range")
        if self.strategy in {ReconstructionStrategy.PARTIAL, ReconstructionStrategy.HYBRID}:
            if self.retained_harmonic_bin_count > self.maximum_partials:
                raise ValueError("partial and hybrid reconstruction exceed maximum_partials")
        _require_ratio(self.hybrid_time_weight, name="hybrid_time_weight")
        peak_target = _require_positive(self.normalization_peak, name="normalization_peak")
        if peak_target > 1.0:
            raise ValueError("normalization_peak must not exceed one")
        _require_positive(self.normalization_gain, name="normalization_gain")
        for name in (
            "source_rms",
            "reconstructed_rms",
            "peak_amplitude",
            "seam_value_error",
            "seam_slope_error",
        ):
            _require_non_negative(getattr(self, name), name=name)
        _require_ratio(self.seam_score, name="seam_score")
        _require_ratio(
            self.spectral_similarity_score,
            name="spectral_similarity_score",
        )
        if len(self.samples) != self.target_sample_count:
            raise ValueError("sample payload length does not match target_sample_count")
        if any(not math.isfinite(float(value)) for value in self.samples):
            raise ValueError("reconstructed samples must be finite")
        if self.peak_amplitude > self.normalization_peak + 1.0e-12:
            raise ValueError("reconstructed peak exceeds normalization_peak")
        measured_peak = max(abs(float(value)) for value in self.samples)
        if not math.isclose(
            measured_peak,
            self.peak_amplitude,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("peak_amplitude is inconsistent with sample payload")
        if not self.decision_reason:
            raise ValueError("decision_reason must not be empty")

    @property
    def source_cycle_length_samples(self) -> int:
        return self.source_end_sample - self.source_start_sample

    def _content_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "candidate_index": self.candidate_index,
            "candidate_sha256": self.candidate_sha256,
            "ranking_sha256": self.ranking_sha256,
            "segment_index": self.segment_index,
            "source_start_sample": self.source_start_sample,
            "source_end_sample": self.source_end_sample,
            "source_cycle_length_samples": self.source_cycle_length_samples,
            "source_cycle_sha256": self.source_cycle_sha256,
            "strategy": self.strategy.value,
            "target_sample_count": self.target_sample_count,
            "maximum_partials": self.maximum_partials,
            "available_harmonic_bin_count": self.available_harmonic_bin_count,
            "retained_harmonic_bin_count": self.retained_harmonic_bin_count,
            "remove_dc": self.remove_dc,
            "hybrid_time_weight": self.hybrid_time_weight,
            "normalization_peak": self.normalization_peak,
            "normalization_gain": self.normalization_gain,
            "source_rms": self.source_rms,
            "reconstructed_rms": self.reconstructed_rms,
            "peak_amplitude": self.peak_amplitude,
            "seam_value_error": self.seam_value_error,
            "seam_slope_error": self.seam_slope_error,
            "seam_score": self.seam_score,
            "spectral_similarity_score": self.spectral_similarity_score,
            "samples": list(self.samples),
            "decision_reason": self.decision_reason,
        }

    @property
    def wave_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["wave_sha256"] = self.wave_sha256
        return result


@dataclass(frozen=True, slots=True)
class ReconstructedWaveSet:
    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    cycle_discovery_analysis_sha256: str
    selected_cycle_set_sha256: str
    requested_strategy: ReconstructionStrategy
    decision: ReconstructionDecision
    target_sample_count: int
    maximum_partials: int
    hybrid_time_weight: float
    normalization_peak: float
    remove_dc: bool
    waves: tuple[ReconstructedWave, ...]
    selected_candidate_indices: tuple[int, ...]
    selected_candidate_sha256: tuple[str, ...]
    selected_ranking_sha256: tuple[str, ...]
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported reconstructed-wave-set schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise ValueError("tool_version must be a non-empty normalized string")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "cycle_discovery_analysis_sha256",
            "selected_cycle_set_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if not isinstance(self.requested_strategy, ReconstructionStrategy):
            raise ValueError("requested_strategy must be a ReconstructionStrategy")
        if not isinstance(self.decision, ReconstructionDecision):
            raise ValueError("decision must be a ReconstructionDecision")
        if self.target_sample_count < 16 or self.target_sample_count > 4096:
            raise ValueError("target_sample_count must be between 16 and 4096")
        if self.maximum_partials <= 0:
            raise ValueError("maximum_partials must be positive")
        _require_ratio(self.hybrid_time_weight, name="hybrid_time_weight")
        normalization_peak = _require_positive(
            self.normalization_peak,
            name="normalization_peak",
        )
        if normalization_peak > 1.0:
            raise ValueError("normalization_peak must not exceed one")
        if tuple(wave.index for wave in self.waves) != tuple(range(len(self.waves))):
            raise ValueError("wave indexes must be contiguous from zero")
        if any(wave.target_sample_count != self.target_sample_count for wave in self.waves):
            raise ValueError("wave target sample counts are inconsistent")
        if any(wave.maximum_partials != self.maximum_partials for wave in self.waves):
            raise ValueError("wave maximum_partials values are inconsistent")
        if any(wave.remove_dc != self.remove_dc for wave in self.waves):
            raise ValueError("wave DC policy is inconsistent")
        if self.selected_candidate_indices != tuple(
            wave.candidate_index for wave in self.waves
        ):
            raise ValueError("selected candidate indexes do not match waves")
        if self.selected_candidate_sha256 != tuple(
            wave.candidate_sha256 for wave in self.waves
        ):
            raise ValueError("selected candidate hashes do not match waves")
        if self.selected_ranking_sha256 != tuple(
            wave.ranking_sha256 for wave in self.waves
        ):
            raise ValueError("selected ranking hashes do not match waves")
        if self.decision is ReconstructionDecision.RECONSTRUCTED:
            if not self.waves:
                raise ValueError("reconstructed decision requires at least one wave")
        elif self.waves:
            raise ValueError("no-selected-cycles decision cannot expose waves")
        if not self.decision_reason:
            raise ValueError("decision_reason must not be empty")

    @property
    def wave_count(self) -> int:
        return len(self.waves)

    @property
    def wave_sha256(self) -> tuple[str, ...]:
        return tuple(wave.wave_sha256 for wave in self.waves)

    @property
    def strategy_counts(self) -> dict[str, int]:
        result = {
            ReconstructionStrategy.SPECTRAL.value: 0,
            ReconstructionStrategy.PARTIAL.value: 0,
            ReconstructionStrategy.HYBRID.value: 0,
        }
        for wave in self.waves:
            result[wave.strategy.value] += 1
        return result

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "cycle_discovery_analysis_sha256": (
                self.cycle_discovery_analysis_sha256
            ),
            "selected_cycle_set_sha256": self.selected_cycle_set_sha256,
            "requested_strategy": self.requested_strategy.value,
            "decision": self.decision.value,
            "target_sample_count": self.target_sample_count,
            "maximum_partials": self.maximum_partials,
            "hybrid_time_weight": self.hybrid_time_weight,
            "normalization_peak": self.normalization_peak,
            "remove_dc": self.remove_dc,
            "wave_count": self.wave_count,
            "wave_sha256": list(self.wave_sha256),
            "strategy_counts": self.strategy_counts,
            "selected_candidate_indices": list(self.selected_candidate_indices),
            "selected_candidate_sha256": list(self.selected_candidate_sha256),
            "selected_ranking_sha256": list(self.selected_ranking_sha256),
            "waves": [wave.to_dict() for wave in self.waves],
            "decision_reason": self.decision_reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _periodic_linear_resample(samples: np.ndarray, target_count: int) -> np.ndarray:
    source_count = int(samples.size)
    positions = np.arange(target_count, dtype=np.float64) * source_count / target_count
    left = np.floor(positions).astype(np.int64)
    fraction = positions - left
    right = (left + 1) % source_count
    return np.asarray(
        samples[left] * (1.0 - fraction) + samples[right] * fraction,
        dtype=np.float64,
    )


def _spectral_projection(
    samples: np.ndarray,
    target_count: int,
    *,
    maximum_partials: int | None,
    remove_dc: bool,
) -> tuple[np.ndarray, int, int]:
    source_count = int(samples.size)
    working = np.asarray(samples, dtype=np.float64)
    if remove_dc:
        working = working - float(np.mean(working, dtype=np.float64))
    spectrum = np.fft.rfft(working)
    target_spectrum = np.zeros(target_count // 2 + 1, dtype=np.complex128)
    maximum_bin = min(spectrum.size - 1, target_spectrum.size - 1)
    available = max(0, maximum_bin)
    if maximum_partials is None:
        retained_bins = list(range(1, maximum_bin + 1))
    else:
        ranked_bins = sorted(
            range(1, maximum_bin + 1),
            key=lambda index: (-float(abs(spectrum[index])), index),
        )
        retained_bins = sorted(ranked_bins[:maximum_partials])
    scale = target_count / source_count
    if not remove_dc and target_spectrum.size:
        target_spectrum[0] = spectrum[0] * scale
    for index in retained_bins:
        target_spectrum[index] = spectrum[index] * scale
    if target_count % 2 == 0 and target_spectrum.size > 1:
        target_spectrum[-1] = complex(float(target_spectrum[-1].real), 0.0)
    reconstructed = np.fft.irfft(target_spectrum, n=target_count)
    return (
        np.asarray(reconstructed, dtype=np.float64),
        available,
        len(retained_bins),
    )


def _spectral_similarity(reference: np.ndarray, candidate: np.ndarray) -> float:
    reference_magnitude = np.abs(np.fft.rfft(reference))
    candidate_magnitude = np.abs(np.fft.rfft(candidate))
    denominator = float(
        np.linalg.norm(reference_magnitude) * np.linalg.norm(candidate_magnitude)
    )
    if denominator <= 1.0e-24:
        return 1.0 if np.array_equal(reference, candidate) else 0.0
    return _clamp_ratio(
        float(np.dot(reference_magnitude, candidate_magnitude) / denominator)
    )


def _choose_strategy(candidate: Any) -> ReconstructionStrategy:
    if (
        float(candidate.seam_score) >= 0.80
        and float(candidate.spectral_consistency_score) >= 0.90
    ):
        return ReconstructionStrategy.SPECTRAL
    if (
        float(candidate.periodicity_score) >= 0.90
        and float(candidate.energy_consistency_score) >= 0.80
    ):
        return ReconstructionStrategy.PARTIAL
    return ReconstructionStrategy.HYBRID


def _normalize_wave(
    samples: np.ndarray,
    *,
    remove_dc: bool,
    normalization_peak: float,
) -> tuple[np.ndarray, float]:
    result = np.asarray(samples, dtype=np.float64)
    if remove_dc:
        result = result - float(np.mean(result, dtype=np.float64))
    peak = float(np.max(np.abs(result)))
    gain = 1.0 if peak <= 1.0e-24 else float(normalization_peak / peak)
    result = result * gain
    result[np.abs(result) < 1.0e-15] = 0.0
    return np.asarray(result, dtype=np.float64), gain


def _seam_metrics(samples: np.ndarray) -> tuple[float, float, float]:
    peak = max(float(np.max(np.abs(samples))), 1.0e-24)
    value_error = float(abs(samples[0] - samples[-1]) / (2.0 * peak))
    incoming_slope = float(samples[0] - samples[-1])
    outgoing_slope = float(samples[1] - samples[0])
    slope_error = float(abs(outgoing_slope - incoming_slope) / (4.0 * peak))
    score = _clamp_ratio(1.0 - 0.60 * value_error - 0.40 * slope_error)
    return value_error, slope_error, score


def reconstruct_selected_cycles(
    samples: npt.ArrayLike,
    cycle_discovery_analysis: CycleDiscoveryAnalysis,
    selected_cycle_set: SelectedCycleSet,
    *,
    strategy: ReconstructionStrategy | str = ReconstructionStrategy.AUTO,
    target_sample_count: int = 128,
    maximum_partials: int = 32,
    hybrid_time_weight: float = 0.35,
    normalization_peak: float = 0.98,
    remove_dc: bool = True,
    tool_version: str = __version__,
) -> ReconstructedWaveSet:
    """Reconstruct selected V6-D cycles as deterministic float-domain waves."""

    data = validate_mono_samples(samples)
    requested_strategy = ReconstructionStrategy(strategy)
    target_count = int(target_sample_count)
    if target_count < 16 or target_count > 4096:
        raise ValueError("target_sample_count must be between 16 and 4096")
    maximum_partials = int(maximum_partials)
    if maximum_partials <= 0:
        raise ValueError("maximum_partials must be positive")
    time_weight = _require_ratio(hybrid_time_weight, name="hybrid_time_weight")
    peak_target = _require_positive(normalization_peak, name="normalization_peak")
    if peak_target > 1.0:
        raise ValueError("normalization_peak must not exceed one")
    sample_hash = _sample_sha256(data)
    if sample_hash != cycle_discovery_analysis.sample_sha256:
        raise ValueError("source samples do not match cycle discovery identity")
    if sample_hash != selected_cycle_set.sample_sha256:
        raise ValueError("source samples do not match selected cycle set identity")
    if (
        selected_cycle_set.cycle_discovery_analysis_sha256
        != cycle_discovery_analysis.analysis_sha256
    ):
        raise ValueError("selected cycle set does not link to cycle discovery")

    candidate_by_index = {
        candidate.index: candidate
        for candidate in cycle_discovery_analysis.candidates
    }
    selected_entries = tuple(
        entry for entry in selected_cycle_set.ranked_candidates if entry.selected
    )
    selected_indexes = tuple(entry.candidate_index for entry in selected_entries)
    selected_candidate_hashes = tuple(
        entry.candidate_sha256 for entry in selected_entries
    )
    selected_ranking_hashes = tuple(
        entry.ranking_sha256 for entry in selected_entries
    )
    if tuple(
        getattr(selected_cycle_set, "selected_candidate_indices", selected_indexes)
    ) != selected_indexes:
        raise ValueError("selected candidate indexes are inconsistent")
    if tuple(
        getattr(
            selected_cycle_set,
            "selected_candidate_sha256",
            selected_candidate_hashes,
        )
    ) != selected_candidate_hashes:
        raise ValueError("selected candidate hashes are inconsistent")
    if tuple(
        getattr(
            selected_cycle_set,
            "selected_ranking_sha256",
            selected_ranking_hashes,
        )
    ) != selected_ranking_hashes:
        raise ValueError("selected ranking hashes are inconsistent")
    if selected_cycle_set.decision is not CycleSelectionDecision.SELECTED:
        if selected_entries:
            raise ValueError("non-selected V6-D decision cannot expose selected entries")
        decision = ReconstructionDecision.NO_SELECTED_CYCLES
        waves: tuple[ReconstructedWave, ...] = ()
        reason = (
            "V6-D did not select any representative cycles, so no waveform "
            "reconstruction was performed."
        )
    else:
        reconstructed: list[ReconstructedWave] = []
        for wave_index, entry in enumerate(selected_entries):
            candidate = candidate_by_index.get(entry.candidate_index)
            if candidate is None:
                raise ValueError("selected cycle references an unknown V6-C candidate")
            if candidate.candidate_sha256 != entry.candidate_sha256:
                raise ValueError("selected cycle candidate hash is inconsistent")
            start = int(candidate.start_sample)
            end = int(candidate.end_sample)
            if start < 0 or end > data.size or end <= start:
                raise ValueError("selected cycle bounds exceed source samples")
            source_cycle = np.asarray(data[start:end], dtype=np.float64)
            concrete_strategy = (
                _choose_strategy(candidate)
                if requested_strategy is ReconstructionStrategy.AUTO
                else requested_strategy
            )
            reference = _periodic_linear_resample(source_cycle, target_count)
            if concrete_strategy is ReconstructionStrategy.SPECTRAL:
                raw, available, retained = _spectral_projection(
                    source_cycle,
                    target_count,
                    maximum_partials=None,
                    remove_dc=bool(remove_dc),
                )
                strategy_reason = (
                    "Full retained-bin spectral projection was selected."
                )
            elif concrete_strategy is ReconstructionStrategy.PARTIAL:
                raw, available, retained = _spectral_projection(
                    source_cycle,
                    target_count,
                    maximum_partials=maximum_partials,
                    remove_dc=bool(remove_dc),
                )
                strategy_reason = (
                    "Dominant-partial reconstruction was selected."
                )
            else:
                partial, available, retained = _spectral_projection(
                    source_cycle,
                    target_count,
                    maximum_partials=maximum_partials,
                    remove_dc=bool(remove_dc),
                )
                raw = time_weight * reference + (1.0 - time_weight) * partial
                strategy_reason = (
                    "Hybrid periodic-time and dominant-partial reconstruction was selected."
                )
            normalized, gain = _normalize_wave(
                raw,
                remove_dc=bool(remove_dc),
                normalization_peak=peak_target,
            )
            seam_value, seam_slope, seam_score = _seam_metrics(normalized)
            source_rms = float(
                np.sqrt(np.mean(np.square(source_cycle), dtype=np.float64))
            )
            reconstructed_rms = float(
                np.sqrt(np.mean(np.square(normalized), dtype=np.float64))
            )
            peak_amplitude = float(np.max(np.abs(normalized)))
            spectral_similarity = _spectral_similarity(reference, normalized)
            payload = tuple(float(value) for value in normalized)
            reconstructed.append(
                ReconstructedWave(
                    index=wave_index,
                    candidate_index=candidate.index,
                    candidate_sha256=candidate.candidate_sha256,
                    ranking_sha256=entry.ranking_sha256,
                    segment_index=candidate.segment_index,
                    source_start_sample=start,
                    source_end_sample=end,
                    source_cycle_sha256=_sample_sha256(source_cycle),
                    strategy=concrete_strategy,
                    target_sample_count=target_count,
                    maximum_partials=maximum_partials,
                    available_harmonic_bin_count=available,
                    retained_harmonic_bin_count=retained,
                    remove_dc=bool(remove_dc),
                    hybrid_time_weight=time_weight,
                    normalization_peak=peak_target,
                    normalization_gain=gain,
                    source_rms=source_rms,
                    reconstructed_rms=reconstructed_rms,
                    peak_amplitude=peak_amplitude,
                    seam_value_error=seam_value,
                    seam_slope_error=seam_slope,
                    seam_score=seam_score,
                    spectral_similarity_score=spectral_similarity,
                    samples=payload,
                    decision_reason=strategy_reason,
                )
            )
        waves = tuple(reconstructed)
        decision = ReconstructionDecision.RECONSTRUCTED
        reason = (
            f"Reconstructed {len(waves)} deterministic float-domain waves from the "
            "V6-D selected cycle set without modifying source audio."
        )

    return ReconstructedWaveSet(
        schema_version=1,
        tool_version=tool_version,
        sample_rate=cycle_discovery_analysis.sample_rate,
        sample_count=cycle_discovery_analysis.sample_count,
        sample_sha256=sample_hash,
        cycle_discovery_analysis_sha256=cycle_discovery_analysis.analysis_sha256,
        selected_cycle_set_sha256=selected_cycle_set.analysis_sha256,
        requested_strategy=requested_strategy,
        decision=decision,
        target_sample_count=target_count,
        maximum_partials=maximum_partials,
        hybrid_time_weight=time_weight,
        normalization_peak=peak_target,
        remove_dc=bool(remove_dc),
        waves=waves,
        selected_candidate_indices=tuple(wave.candidate_index for wave in waves),
        selected_candidate_sha256=tuple(wave.candidate_sha256 for wave in waves),
        selected_ranking_sha256=tuple(wave.ranking_sha256 for wave in waves),
        decision_reason=reason,
    )


def analyze_audio_source_reconstruction(
    source: Any,
    *,
    working_pitch_policy: WorkingPitchPolicy | str = WorkingPitchPolicy.AUTO,
    locked_frequency_hz: float | None = None,
    attack_policy: AttackPolicy | str = AttackPolicy.AUTO,
    selection_policy: CycleSelectionPolicy | str = CycleSelectionPolicy.AUTO,
    top_n: int = 16,
    forced_candidate_index: int | None = None,
    allow_rejected_forced_candidate: bool = False,
    reconstruction_strategy: ReconstructionStrategy | str = ReconstructionStrategy.AUTO,
    cycle_discovery_kwargs: dict[str, float | int] | None = None,
    selection_kwargs: dict[str, float] | None = None,
    reconstruction_kwargs: dict[str, float | int | bool] | None = None,
) -> ReconstructedWaveSet:
    """Run the canonical V6-A through V6-E chain for one imported source."""

    cycles = analyze_audio_source_cycles(
        source,
        working_pitch_policy=working_pitch_policy,
        locked_frequency_hz=locked_frequency_hz,
        attack_policy=attack_policy,
        **dict(cycle_discovery_kwargs or {}),
    )
    selected = select_representative_cycles(
        cycles,
        policy=selection_policy,
        top_n=top_n,
        forced_candidate_index=forced_candidate_index,
        allow_rejected_forced_candidate=allow_rejected_forced_candidate,
        **dict(selection_kwargs or {}),
    )
    return reconstruct_selected_cycles(
        source.mono_samples,
        cycles,
        selected,
        strategy=reconstruction_strategy,
        **dict(reconstruction_kwargs or {}),
    )
