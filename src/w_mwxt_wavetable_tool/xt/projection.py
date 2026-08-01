from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence, TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from ..errors import AnalysisError
from ..version import __version__

if TYPE_CHECKING:
    from ..analysis.code_v6 import CodeV6Analysis
    from ..analysis.reconstruction import ReconstructedWaveSet

PROJECTION_SCHEMA_VERSION = 1
SOURCE_SAMPLE_COUNT = 128
STORED_SAMPLE_COUNT = 64
XT_SAMPLE_MIN = -127
XT_SAMPLE_MAX = 127
DEFAULT_STEM = "CODE_V7_B_XT_NATIVE_PROJECTION"
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


def _samples_sha256(samples: Sequence[float]) -> str:
    array = np.asarray(samples, dtype="<f8")
    return sha256(array.tobytes(order="C")).hexdigest()


def _require_hash(value: str, *, name: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise AnalysisError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _require_finite_samples(samples: Sequence[float], *, name: str) -> npt.NDArray[np.float64]:
    array = np.asarray(tuple(float(value) for value in samples), dtype=np.float64)
    if array.shape != (SOURCE_SAMPLE_COUNT,):
        raise AnalysisError(
            f"{name} must contain exactly {SOURCE_SAMPLE_COUNT} samples, got {array.size}"
        )
    if not np.all(np.isfinite(array)):
        raise AnalysisError(f"{name} contains NaN or infinite values")
    peak = float(np.max(np.abs(array)))
    if peak > 1.0 + _EPSILON:
        raise AnalysisError(
            f"{name} exceeds normalized range [-1, 1] with peak {peak:.12g}; "
            "implicit clipping is forbidden"
        )
    return array


def _round_half_away_from_zero(values: npt.NDArray[np.float64]) -> npt.NDArray[np.int64]:
    magnitudes = np.floor(np.abs(values) + 0.5)
    return np.asarray(np.copysign(magnitudes, values), dtype=np.int64)


def reconstruct_xt_native(stored_samples: Sequence[int]) -> tuple[int, ...]:
    stored = tuple(int(value) for value in stored_samples)
    if len(stored) != STORED_SAMPLE_COUNT:
        raise AnalysisError(
            f"XT stored wave must contain {STORED_SAMPLE_COUNT} values, got {len(stored)}"
        )
    if any(value < XT_SAMPLE_MIN or value > XT_SAMPLE_MAX for value in stored):
        raise AnalysisError(
            f"XT stored samples must stay in [{XT_SAMPLE_MIN}, {XT_SAMPLE_MAX}]"
        )
    return stored + tuple(-value for value in reversed(stored))


def _quantize_projected_half(rotated_target: npt.NDArray[np.float64]) -> tuple[int, ...]:
    # For each constrained pair x[i] = q and x[127-i] = -q, the continuous
    # least-squares optimum is q = (t[i] - t[127-i]) / 2. Nearest-int8
    # quantization independently minimizes the quantized pair error.
    continuous = 0.5 * (
        rotated_target[:STORED_SAMPLE_COUNT]
        - rotated_target[::-1][:STORED_SAMPLE_COUNT]
    )
    quantized = _round_half_away_from_zero(continuous * XT_SAMPLE_MAX)
    quantized = np.clip(quantized, XT_SAMPLE_MIN, XT_SAMPLE_MAX)
    return tuple(int(value) for value in quantized)


def _safe_ratio(value: float, denominator: float) -> float:
    return float(value / max(abs(denominator), _EPSILON))


def _correlation(left: npt.NDArray[np.float64], right: npt.NDArray[np.float64]) -> float:
    left_centered = left - float(np.mean(left, dtype=np.float64))
    right_centered = right - float(np.mean(right, dtype=np.float64))
    denominator = float(np.linalg.norm(left_centered) * np.linalg.norm(right_centered))
    if denominator <= _EPSILON:
        return 1.0 if np.allclose(left, right, rtol=0.0, atol=1.0e-12) else 0.0
    return float(np.clip(np.dot(left_centered, right_centered) / denominator, -1.0, 1.0))


def _normalized_spectrum(samples: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    magnitudes = np.abs(np.fft.rfft(samples))[1:]
    norm = float(np.linalg.norm(magnitudes))
    if norm <= _EPSILON:
        return np.zeros_like(magnitudes, dtype=np.float64)
    return np.asarray(magnitudes / norm, dtype=np.float64)


def _band_power_ratios(samples: npt.NDArray[np.float64]) -> tuple[float, float, float]:
    power = np.square(np.abs(np.fft.rfft(samples))[1:])
    total = float(np.sum(power, dtype=np.float64))
    if total <= _EPSILON:
        return 0.0, 0.0, 0.0
    low = float(np.sum(power[0:4], dtype=np.float64) / total)
    mid = float(np.sum(power[4:16], dtype=np.float64) / total)
    high = float(np.sum(power[16:], dtype=np.float64) / total)
    return low, mid, high


@dataclass(frozen=True, slots=True)
class XtProjectionWeights:
    time: float = 0.45
    spectral: float = 0.25
    seam: float = 0.10
    h1: float = 0.06
    h2: float = 0.05
    h3: float = 0.04
    bands: float = 0.05

    def __post_init__(self) -> None:
        values = (self.time, self.spectral, self.seam, self.h1, self.h2, self.h3, self.bands)
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise AnalysisError("Projection weights must be finite and non-negative")
        if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise AnalysisError("Projection weights must sum exactly to 1.0")

    def to_dict(self) -> dict[str, float]:
        return {
            "time": self.time,
            "spectral": self.spectral,
            "seam": self.seam,
            "h1": self.h1,
            "h2": self.h2,
            "h3": self.h3,
            "bands": self.bands,
        }


@dataclass(frozen=True, slots=True)
class XtProjectionMetrics:
    source_rms: float
    reconstructed_rms: float
    source_peak: float
    reconstructed_peak: float
    time_rmse: float
    time_nrmse: float
    maximum_absolute_error: float
    correlation: float
    spectral_rmse: float
    spectral_similarity: float
    h1_error: float
    h2_error: float
    h3_error: float
    low_band_error: float
    mid_band_error: float
    high_band_error: float
    seam_value_error: float
    seam_slope_error: float
    objective_score: float

    def __post_init__(self) -> None:
        for name, value in self.to_dict().items():
            if not math.isfinite(float(value)):
                raise AnalysisError(f"Projection metric {name} must be finite")
        if not -1.0 - _EPSILON <= self.correlation <= 1.0 + _EPSILON:
            raise AnalysisError("correlation must be between -1 and 1")
        if not 0.0 - _EPSILON <= self.spectral_similarity <= 1.0 + _EPSILON:
            raise AnalysisError("spectral_similarity must be between 0 and 1")

    def to_dict(self) -> dict[str, float]:
        return {
            "source_rms": self.source_rms,
            "reconstructed_rms": self.reconstructed_rms,
            "source_peak": self.source_peak,
            "reconstructed_peak": self.reconstructed_peak,
            "time_rmse": self.time_rmse,
            "time_nrmse": self.time_nrmse,
            "maximum_absolute_error": self.maximum_absolute_error,
            "correlation": self.correlation,
            "spectral_rmse": self.spectral_rmse,
            "spectral_similarity": self.spectral_similarity,
            "h1_error": self.h1_error,
            "h2_error": self.h2_error,
            "h3_error": self.h3_error,
            "low_band_error": self.low_band_error,
            "mid_band_error": self.mid_band_error,
            "high_band_error": self.high_band_error,
            "seam_value_error": self.seam_value_error,
            "seam_slope_error": self.seam_slope_error,
            "objective_score": self.objective_score,
        }


@dataclass(frozen=True, slots=True)
class XtPhaseEvaluation:
    phase_rotation_samples: int
    metrics: XtProjectionMetrics

    def __post_init__(self) -> None:
        if not 0 <= self.phase_rotation_samples < SOURCE_SAMPLE_COUNT:
            raise AnalysisError("phase_rotation_samples must be in range 0..127")

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_rotation_samples": self.phase_rotation_samples,
            "metrics": self.metrics.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class XtProjectedWave:
    index: int
    candidate_index: int
    source_wave_sha256: str
    source_samples_sha256: str
    selected_phase_rotation_samples: int
    worst_phase_rotation_samples: int
    stored_samples: tuple[int, ...]
    reconstructed_samples: tuple[int, ...]
    reconstructed_aligned: tuple[float, ...]
    source_samples: tuple[float, ...]
    selected_metrics: XtProjectionMetrics
    phase_evaluations: tuple[XtPhaseEvaluation, ...]

    def __post_init__(self) -> None:
        if self.index < 0 or self.candidate_index < 0:
            raise AnalysisError("wave indexes must not be negative")
        _require_hash(self.source_wave_sha256, name="source_wave_sha256")
        _require_hash(self.source_samples_sha256, name="source_samples_sha256")
        if len(self.source_samples) != SOURCE_SAMPLE_COUNT:
            raise AnalysisError("source_samples must contain 128 values")
        if len(self.reconstructed_aligned) != SOURCE_SAMPLE_COUNT:
            raise AnalysisError("reconstructed_aligned must contain 128 values")
        if reconstruct_xt_native(self.stored_samples) != self.reconstructed_samples:
            raise AnalysisError("reconstructed_samples do not match stored_samples")
        if tuple(evaluation.phase_rotation_samples for evaluation in self.phase_evaluations) != tuple(range(128)):
            raise AnalysisError("phase evaluations must cover phases 0..127 exactly")
        if self.selected_phase_rotation_samples not in range(128):
            raise AnalysisError("selected phase is outside 0..127")
        if self.worst_phase_rotation_samples not in range(128):
            raise AnalysisError("worst phase is outside 0..127")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "candidate_index": self.candidate_index,
            "source_wave_sha256": self.source_wave_sha256,
            "source_samples_sha256": self.source_samples_sha256,
            "selected_phase_rotation_samples": self.selected_phase_rotation_samples,
            "worst_phase_rotation_samples": self.worst_phase_rotation_samples,
            "stored_samples": list(self.stored_samples),
            "reconstructed_samples": list(self.reconstructed_samples),
            "reconstructed_aligned": list(self.reconstructed_aligned),
            "source_samples": list(self.source_samples),
            "selected_metrics": self.selected_metrics.to_dict(),
            "phase_evaluations": [evaluation.to_dict() for evaluation in self.phase_evaluations],
        }

    @property
    def projection_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["projection_sha256"] = self.projection_sha256
        return result


@dataclass(frozen=True, slots=True)
class XtProjectionSet:
    schema_version: int
    tool_version: str
    source_reconstructed_wave_set_sha256: str
    source_code_v6_analysis_sha256: str | None
    weights: XtProjectionWeights
    waves: tuple[XtProjectedWave, ...]
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != PROJECTION_SCHEMA_VERSION:
            raise AnalysisError("Unsupported XT projection schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise AnalysisError("tool_version must be a normalized non-empty string")
        _require_hash(
            self.source_reconstructed_wave_set_sha256,
            name="source_reconstructed_wave_set_sha256",
        )
        if self.source_code_v6_analysis_sha256 is not None:
            _require_hash(
                self.source_code_v6_analysis_sha256,
                name="source_code_v6_analysis_sha256",
            )
        if tuple(wave.index for wave in self.waves) != tuple(range(len(self.waves))):
            raise AnalysisError("projected wave indexes must be contiguous from zero")
        if not self.waves:
            raise AnalysisError("projection set requires at least one wave")
        if not self.decision_reason:
            raise AnalysisError("decision_reason must not be empty")

    @property
    def wave_count(self) -> int:
        return len(self.waves)

    @property
    def projection_sha256(self) -> tuple[str, ...]:
        return tuple(wave.projection_sha256 for wave in self.waves)

    @property
    def objective_summary(self) -> dict[str, float]:
        values = np.asarray(
            [wave.selected_metrics.objective_score for wave in self.waves],
            dtype=np.float64,
        )
        return {
            "minimum": float(np.min(values)),
            "mean": float(np.mean(values, dtype=np.float64)),
            "maximum": float(np.max(values)),
        }

    @property
    def time_nrmse_summary(self) -> dict[str, float]:
        values = np.asarray(
            [wave.selected_metrics.time_nrmse for wave in self.waves],
            dtype=np.float64,
        )
        return {
            "minimum": float(np.min(values)),
            "mean": float(np.mean(values, dtype=np.float64)),
            "maximum": float(np.max(values)),
        }

    @property
    def spectral_similarity_summary(self) -> dict[str, float]:
        values = np.asarray(
            [wave.selected_metrics.spectral_similarity for wave in self.waves],
            dtype=np.float64,
        )
        return {
            "minimum": float(np.min(values)),
            "mean": float(np.mean(values, dtype=np.float64)),
            "maximum": float(np.max(values)),
        }

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "source_reconstructed_wave_set_sha256": self.source_reconstructed_wave_set_sha256,
            "source_code_v6_analysis_sha256": self.source_code_v6_analysis_sha256,
            "source_sample_count": SOURCE_SAMPLE_COUNT,
            "stored_sample_count": STORED_SAMPLE_COUNT,
            "quantization_range": [XT_SAMPLE_MIN, XT_SAMPLE_MAX],
            "phase_search_count": SOURCE_SAMPLE_COUNT,
            "weights": self.weights.to_dict(),
            "wave_count": self.wave_count,
            "projection_sha256": list(self.projection_sha256),
            "objective_summary": self.objective_summary,
            "time_nrmse_summary": self.time_nrmse_summary,
            "spectral_similarity_summary": self.spectral_similarity_summary,
            "waves": [wave.to_dict() for wave in self.waves],
            "decision_reason": self.decision_reason,
            "boundaries": {
                "generates_sysex": False,
                "allocates_user_waves": False,
                "orders_wavetable_positions": False,
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
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# CODE V7-B — XT-native projection",
            "",
            f"- Analysis SHA-256: `{self.analysis_sha256}`",
            f"- Source reconstructed-wave-set: `{self.source_reconstructed_wave_set_sha256}`",
            f"- Wave count: `{self.wave_count}`",
            f"- Quantization range: `{XT_SAMPLE_MIN}…{XT_SAMPLE_MAX}`",
            f"- Phase candidates per wave: `{SOURCE_SAMPLE_COUNT}`",
            "- SysEx generation: `no`",
            "",
            "## Aggregate metrics",
            "",
            f"- Objective mean: `{self.objective_summary['mean']:.12g}`",
            f"- Time NRMSE mean: `{self.time_nrmse_summary['mean']:.12g}`",
            f"- Spectral similarity mean: `{self.spectral_similarity_summary['mean']:.12g}`",
            "",
            "## Waves",
            "",
            "| Wave | Candidate | Phase | Score | Time NRMSE | Spectral similarity | Correlation |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for wave in self.waves:
            metrics = wave.selected_metrics
            lines.append(
                f"| {wave.index} | {wave.candidate_index} | "
                f"{wave.selected_phase_rotation_samples} | "
                f"{metrics.objective_score:.12g} | "
                f"{metrics.time_nrmse:.12g} | "
                f"{metrics.spectral_similarity:.12g} | "
                f"{metrics.correlation:.12g} |"
            )
        lines.extend(
            [
                "",
                "## Boundary",
                "",
                "This stage performs deterministic mathematical projection only. It does not allocate XT memory, build WAVD messages, create a 61-position wavetable, or transmit SysEx.",
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


def _measure_projection(
    source_aligned: npt.NDArray[np.float64],
    reconstructed_aligned: npt.NDArray[np.float64],
    rotated_source: npt.NDArray[np.float64],
    reconstructed_rotated: npt.NDArray[np.float64],
    weights: XtProjectionWeights,
) -> XtProjectionMetrics:
    difference = reconstructed_aligned - source_aligned
    source_rms = float(np.sqrt(np.mean(np.square(source_aligned), dtype=np.float64)))
    reconstructed_rms = float(
        np.sqrt(np.mean(np.square(reconstructed_aligned), dtype=np.float64))
    )
    source_peak = float(np.max(np.abs(source_aligned)))
    reconstructed_peak = float(np.max(np.abs(reconstructed_aligned)))
    time_rmse = float(np.sqrt(np.mean(np.square(difference), dtype=np.float64)))
    time_nrmse = _safe_ratio(time_rmse, source_rms)
    maximum_absolute_error = float(np.max(np.abs(difference)))
    correlation = _correlation(source_aligned, reconstructed_aligned)

    source_spectrum = _normalized_spectrum(source_aligned)
    reconstructed_spectrum = _normalized_spectrum(reconstructed_aligned)
    spectral_difference = reconstructed_spectrum - source_spectrum
    spectral_rmse = float(
        np.sqrt(np.mean(np.square(spectral_difference), dtype=np.float64))
    )
    spectrum_denominator = float(
        np.linalg.norm(source_spectrum) * np.linalg.norm(reconstructed_spectrum)
    )
    spectral_similarity = (
        1.0
        if spectrum_denominator <= _EPSILON
        and np.allclose(source_spectrum, reconstructed_spectrum, atol=1.0e-12, rtol=0.0)
        else float(
            np.clip(
                np.dot(source_spectrum, reconstructed_spectrum)
                / max(spectrum_denominator, _EPSILON),
                0.0,
                1.0,
            )
        )
    )

    def harmonic_error(index: int) -> float:
        if index - 1 >= source_spectrum.size:
            return 0.0
        return float(abs(source_spectrum[index - 1] - reconstructed_spectrum[index - 1]))

    h1_error = harmonic_error(1)
    h2_error = harmonic_error(2)
    h3_error = harmonic_error(3)

    source_bands = _band_power_ratios(source_aligned)
    reconstructed_bands = _band_power_ratios(reconstructed_aligned)
    low_band_error = abs(source_bands[0] - reconstructed_bands[0])
    mid_band_error = abs(source_bands[1] - reconstructed_bands[1])
    high_band_error = abs(source_bands[2] - reconstructed_bands[2])
    bands_error = (low_band_error + mid_band_error + high_band_error) / 3.0

    amplitude_scale = max(2.0 * source_peak, _EPSILON)
    source_seam_value = float(rotated_source[0] - rotated_source[-1])
    reconstructed_seam_value = float(
        reconstructed_rotated[0] - reconstructed_rotated[-1]
    )
    seam_value_error = abs(reconstructed_seam_value - source_seam_value) / amplitude_scale

    source_seam_slope = float(
        (rotated_source[1] - rotated_source[0])
        - (rotated_source[0] - rotated_source[-1])
    )
    reconstructed_seam_slope = float(
        (reconstructed_rotated[1] - reconstructed_rotated[0])
        - (reconstructed_rotated[0] - reconstructed_rotated[-1])
    )
    seam_slope_error = abs(reconstructed_seam_slope - source_seam_slope) / amplitude_scale
    seam_error = 0.5 * (seam_value_error + seam_slope_error)

    objective_score = (
        weights.time * time_nrmse
        + weights.spectral * spectral_rmse
        + weights.seam * seam_error
        + weights.h1 * h1_error
        + weights.h2 * h2_error
        + weights.h3 * h3_error
        + weights.bands * bands_error
    )

    return XtProjectionMetrics(
        source_rms=source_rms,
        reconstructed_rms=reconstructed_rms,
        source_peak=source_peak,
        reconstructed_peak=reconstructed_peak,
        time_rmse=time_rmse,
        time_nrmse=time_nrmse,
        maximum_absolute_error=maximum_absolute_error,
        correlation=correlation,
        spectral_rmse=spectral_rmse,
        spectral_similarity=spectral_similarity,
        h1_error=h1_error,
        h2_error=h2_error,
        h3_error=h3_error,
        low_band_error=low_band_error,
        mid_band_error=mid_band_error,
        high_band_error=high_band_error,
        seam_value_error=seam_value_error,
        seam_slope_error=seam_slope_error,
        objective_score=float(objective_score),
    )


def project_wave_xt_native(
    samples: Sequence[float],
    *,
    index: int = 0,
    candidate_index: int = 0,
    source_wave_sha256: str | None = None,
    weights: XtProjectionWeights | None = None,
) -> XtProjectedWave:
    source = _require_finite_samples(samples, name="source wave")
    if float(np.max(np.abs(source))) <= _EPSILON:
        raise AnalysisError("silent reconstructed waves are not valid CODE V7-B inputs")
    selected_weights = XtProjectionWeights() if weights is None else weights
    source_samples_sha256 = _samples_sha256(source)
    source_wave_digest = source_samples_sha256 if source_wave_sha256 is None else source_wave_sha256
    _require_hash(source_wave_digest, name="source_wave_sha256")

    candidates: list[tuple[int, tuple[int, ...], tuple[int, ...], tuple[float, ...], XtProjectionMetrics]] = []
    evaluations: list[XtPhaseEvaluation] = []

    for phase in range(SOURCE_SAMPLE_COUNT):
        rotated_source = np.roll(source, -phase)
        stored_samples = _quantize_projected_half(rotated_source)
        reconstructed_samples = reconstruct_xt_native(stored_samples)
        reconstructed_rotated = np.asarray(reconstructed_samples, dtype=np.float64) / XT_SAMPLE_MAX
        reconstructed_aligned = np.roll(reconstructed_rotated, phase)
        metrics = _measure_projection(
            source,
            reconstructed_aligned,
            rotated_source,
            reconstructed_rotated,
            selected_weights,
        )
        evaluations.append(XtPhaseEvaluation(phase, metrics))
        candidates.append(
            (
                phase,
                stored_samples,
                reconstructed_samples,
                tuple(float(value) for value in reconstructed_aligned),
                metrics,
            )
        )

    candidates.sort(
        key=lambda item: (
            item[4].objective_score,
            item[4].time_nrmse,
            item[4].spectral_rmse,
            -item[4].correlation,
            item[0],
        )
    )
    selected = candidates[0]
    worst = max(
        candidates,
        key=lambda item: (
            item[4].objective_score,
            item[4].time_nrmse,
            item[0],
        ),
    )

    return XtProjectedWave(
        index=index,
        candidate_index=candidate_index,
        source_wave_sha256=source_wave_digest,
        source_samples_sha256=source_samples_sha256,
        selected_phase_rotation_samples=selected[0],
        worst_phase_rotation_samples=worst[0],
        stored_samples=selected[1],
        reconstructed_samples=selected[2],
        reconstructed_aligned=selected[3],
        source_samples=tuple(float(value) for value in source),
        selected_metrics=selected[4],
        phase_evaluations=tuple(evaluations),
    )


def _project_wave_records(
    wave_records: Sequence[Mapping[str, Any]],
    *,
    source_reconstructed_wave_set_sha256: str,
    source_code_v6_analysis_sha256: str | None,
    weights: XtProjectionWeights,
    tool_version: str,
) -> XtProjectionSet:
    projected: list[XtProjectedWave] = []
    for expected_index, record in enumerate(wave_records):
        index = int(record.get("index", expected_index))
        if index != expected_index:
            raise AnalysisError("source wave indexes must be contiguous from zero")
        candidate_index = int(record.get("candidate_index", index))
        samples = record.get("samples")
        if not isinstance(samples, Sequence):
            raise AnalysisError(f"source wave {index} has no sample sequence")
        source_wave_sha256 = str(record.get("wave_sha256") or _samples_sha256(samples))
        projected.append(
            project_wave_xt_native(
                samples,
                index=index,
                candidate_index=candidate_index,
                source_wave_sha256=source_wave_sha256,
                weights=weights,
            )
        )
    return XtProjectionSet(
        schema_version=PROJECTION_SCHEMA_VERSION,
        tool_version=tool_version,
        source_reconstructed_wave_set_sha256=source_reconstructed_wave_set_sha256,
        source_code_v6_analysis_sha256=source_code_v6_analysis_sha256,
        weights=weights,
        waves=tuple(projected),
        decision_reason=(
            "Each 128-point CODE V6 cycle was exhaustively searched over 128 integer "
            "phase rotations, projected pairwise into the documented XT reverse-negate "
            "subspace, and quantized to the strict safe range -127..127."
        ),
    )


def project_reconstructed_wave_set_xt_native(
    reconstructed_wave_set: "ReconstructedWaveSet",
    *,
    weights: XtProjectionWeights | None = None,
    tool_version: str = __version__,
    source_code_v6_analysis_sha256: str | None = None,
) -> XtProjectionSet:
    target_sample_count = int(getattr(reconstructed_wave_set, "target_sample_count"))
    if target_sample_count != SOURCE_SAMPLE_COUNT:
        raise AnalysisError(
            f"CODE V7-B requires reconstructed waves of exactly 128 points, got {target_sample_count}"
        )
    waves = tuple(getattr(reconstructed_wave_set, "waves"))
    if not waves:
        raise AnalysisError("CODE V7-B requires at least one reconstructed wave")
    source_hash = str(getattr(reconstructed_wave_set, "analysis_sha256"))
    _require_hash(source_hash, name="reconstructed_wave_set.analysis_sha256")
    records = tuple(
        {
            "index": int(getattr(wave, "index")),
            "candidate_index": int(getattr(wave, "candidate_index")),
            "wave_sha256": str(getattr(wave, "wave_sha256")),
            "samples": tuple(getattr(wave, "samples")),
        }
        for wave in waves
    )
    return _project_wave_records(
        records,
        source_reconstructed_wave_set_sha256=source_hash,
        source_code_v6_analysis_sha256=source_code_v6_analysis_sha256,
        weights=XtProjectionWeights() if weights is None else weights,
        tool_version=tool_version,
    )


def project_code_v6_analysis_xt_native(
    code_v6_analysis: "CodeV6Analysis",
    *,
    weights: XtProjectionWeights | None = None,
    tool_version: str = __version__,
) -> XtProjectionSet:
    code_v6_hash = str(getattr(code_v6_analysis, "analysis_sha256"))
    _require_hash(code_v6_hash, name="code_v6_analysis.analysis_sha256")
    return project_reconstructed_wave_set_xt_native(
        getattr(code_v6_analysis, "reconstructed_wave_set"),
        weights=weights,
        tool_version=tool_version,
        source_code_v6_analysis_sha256=code_v6_hash,
    )


def _validated_hashed_document(document: Mapping[str, Any], *, hash_field: str) -> str:
    recorded = str(document.get(hash_field, ""))
    _require_hash(recorded, name=hash_field)
    content = dict(document)
    del content[hash_field]
    calculated = _canonical_sha256(content)
    if calculated != recorded:
        raise AnalysisError(
            f"{hash_field} mismatch: recorded={recorded}, calculated={calculated}"
        )
    return recorded


def project_code_v6_document_xt_native(
    document: Mapping[str, Any],
    *,
    weights: XtProjectionWeights | None = None,
    tool_version: str = __version__,
) -> XtProjectionSet:
    if "reconstructed_wave_set" in document:
        code_v6_hash = _validated_hashed_document(document, hash_field="analysis_sha256")
        reconstructed = document["reconstructed_wave_set"]
    else:
        code_v6_hash = None
        reconstructed = document
    if not isinstance(reconstructed, Mapping):
        raise AnalysisError("reconstructed_wave_set must be a JSON object")
    reconstructed_hash = _validated_hashed_document(
        reconstructed,
        hash_field="analysis_sha256",
    )
    if int(reconstructed.get("target_sample_count", 0)) != SOURCE_SAMPLE_COUNT:
        raise AnalysisError("JSON reconstructed-wave set must target exactly 128 samples")
    waves = reconstructed.get("waves")
    if not isinstance(waves, list) or not waves:
        raise AnalysisError("JSON reconstructed-wave set must contain at least one wave")
    for wave in waves:
        if not isinstance(wave, Mapping):
            raise AnalysisError("Each reconstructed wave must be a JSON object")
        _validated_hashed_document(wave, hash_field="wave_sha256")
    return _project_wave_records(
        waves,
        source_reconstructed_wave_set_sha256=reconstructed_hash,
        source_code_v6_analysis_sha256=code_v6_hash,
        weights=XtProjectionWeights() if weights is None else weights,
        tool_version=tool_version,
    )


def load_and_project_code_v6_json(
    path: str | Path,
    *,
    weights: XtProjectionWeights | None = None,
    tool_version: str = __version__,
) -> XtProjectionSet:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Unable to read CODE V6 JSON: {source}") from exc
    if not isinstance(document, Mapping):
        raise AnalysisError("CODE V6 JSON root must be an object")
    return project_code_v6_document_xt_native(
        document,
        weights=weights,
        tool_version=tool_version,
    )
