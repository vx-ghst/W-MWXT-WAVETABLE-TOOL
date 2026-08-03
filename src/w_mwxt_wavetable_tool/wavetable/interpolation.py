from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

import numpy as np

from .metrics import analyze_wave_shape, compare_wave_shapes
from .models import (
    GenerationMethod,
    ProgressionCurve,
    WaveBuildMetrics,
    WavetableCandidate,
    WavetableContractError,
    reconstruct_xt_cycle,
)

WAVETABLE_INTERPOLATION_SCHEMA_VERSION = 1
_INTERPOLATION_PRECISION = 12
_SUPPORTED_METHODS = (
    GenerationMethod.WAVEFORM_INTERPOLATION,
    GenerationMethod.AMPLITUDE_INTERPOLATION,
    GenerationMethod.PHASE_AWARE_INTERPOLATION,
    GenerationMethod.SPECTRAL_INTERPOLATION,
    GenerationMethod.HARMONIC_INTERPOLATION,
    GenerationMethod.PERCEPTUAL_INTERPOLATION,
)


def _q(value: float) -> float:
    return round(float(value), _INTERPOLATION_PRECISION)


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _normalized(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise WavetableContractError(f"{name} must be a normalized non-empty string")
    return value


def _entries(values: Sequence[str], *, name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence")
    result = tuple(_normalized(value, name=f"{name} entry") for value in values)
    if not allow_empty and not result:
        raise WavetableContractError(f"{name} must not be empty")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


def _ratio(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked) or not 0.0 <= checked <= 1.0:
        raise WavetableContractError(f"{name} must be finite and between 0 and 1")
    return checked


def _stored_samples(values: Sequence[int]) -> tuple[int, ...]:
    result = tuple(values)
    if len(result) != 64:
        raise WavetableContractError("interpolation requires exactly 64 stored samples")
    for sample in result:
        if isinstance(sample, bool) or not isinstance(sample, int) or not -127 <= sample <= 127:
            raise WavetableContractError("interpolation samples must be integers in -127..127")
    return result


def _full_cycle(stored: Sequence[int]) -> np.ndarray:
    return np.asarray(reconstruct_xt_cycle(_stored_samples(stored)), dtype=np.float64) / 127.0


def _quantize_half(cycle: np.ndarray) -> tuple[int, ...]:
    half = np.asarray(cycle[:64], dtype=np.float64) * 127.0
    result: list[int] = []
    error = 0.0
    for value in half:
        adjusted = float(value) + error
        quantized = int(np.rint(adjusted))
        quantized = max(-127, min(127, quantized))
        error = adjusted - quantized
        result.append(quantized)
    return tuple(result)


def _rms(cycle: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(cycle)))) if cycle.size else 0.0


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    if left.size != right.size or left.size == 0:
        raise WavetableContractError("correlation requires equally sized non-empty cycles")
    left_centered = left - float(np.mean(left))
    right_centered = right - float(np.mean(right))
    denominator = float(
        np.sqrt(np.sum(np.square(left_centered)) * np.sum(np.square(right_centered)))
    )
    if denominator <= 1e-18:
        return 1.0 if np.allclose(left, right, atol=1e-15, rtol=0.0) else 0.0
    return max(-1.0, min(1.0, float(np.dot(left_centered, right_centered)) / denominator))


def _fundamental(cycle: np.ndarray) -> float:
    if cycle.size == 0:
        return 0.0
    spectrum = np.fft.rfft(cycle)
    if spectrum.size <= 1:
        return 0.0
    return float(min(1.0, abs(spectrum[1]) / (cycle.size / 2.0)))


def _phase_lerp(left: np.ndarray, right: np.ndarray, progress: float) -> np.ndarray:
    delta = np.angle(np.exp(1j * (right - left)))
    return left + progress * delta


def _phase_aligned_right(left: np.ndarray, right: np.ndarray) -> tuple[np.ndarray, int]:
    best = right
    best_shift = 0
    best_error = float("inf")
    for shift in range(right.size):
        shifted = np.roll(right, shift)
        error = float(np.mean(np.square(left - shifted)))
        if error < best_error - 1e-15:
            best = shifted
            best_shift = shift
            best_error = error
    return best, best_shift


def _raw_interpolation(
    left: np.ndarray,
    right: np.ndarray,
    progress: float,
    method: GenerationMethod,
) -> tuple[np.ndarray, tuple[str, ...]]:
    evidence: list[str] = []
    if method is GenerationMethod.WAVEFORM_INTERPOLATION:
        cycle = (1.0 - progress) * left + progress * right
        evidence.append("sample-domain linear interpolation")
    elif method is GenerationMethod.AMPLITUDE_INTERPOLATION:
        left_rms = _rms(left)
        right_rms = _rms(right)
        left_unit = left if left_rms <= 1e-15 else left / left_rms
        right_unit = right if right_rms <= 1e-15 else right / right_rms
        target = (1.0 - progress) * left_rms + progress * right_rms
        cycle = ((1.0 - progress) * left_unit + progress * right_unit) * target
        evidence.append("RMS-normalized amplitude interpolation")
    elif method is GenerationMethod.PHASE_AWARE_INTERPOLATION:
        aligned, shift = _phase_aligned_right(left, right)
        cycle = (1.0 - progress) * left + progress * aligned
        evidence.append(f"phase-aware circular alignment shift {shift}")
    elif method is GenerationMethod.SPECTRAL_INTERPOLATION:
        left_spectrum = np.fft.rfft(left)
        right_spectrum = np.fft.rfft(right)
        spectrum = (1.0 - progress) * left_spectrum + progress * right_spectrum
        cycle = np.fft.irfft(spectrum, n=left.size)
        evidence.append("complex-spectrum linear interpolation")
    elif method is GenerationMethod.HARMONIC_INTERPOLATION:
        left_spectrum = np.fft.rfft(left)
        right_spectrum = np.fft.rfft(right)
        left_magnitude = np.abs(left_spectrum)
        right_magnitude = np.abs(right_spectrum)
        magnitude = np.exp(
            (1.0 - progress) * np.log(np.maximum(left_magnitude, 1e-12))
            + progress * np.log(np.maximum(right_magnitude, 1e-12))
        )
        phase = _phase_lerp(np.angle(left_spectrum), np.angle(right_spectrum), progress)
        cycle = np.fft.irfft(magnitude * np.exp(1j * phase), n=left.size)
        evidence.append("log-magnitude harmonic interpolation with shortest phase path")
    elif method is GenerationMethod.PERCEPTUAL_INTERPOLATION:
        aligned, shift = _phase_aligned_right(left, right)
        phase_cycle = (1.0 - progress) * left + progress * aligned
        left_spectrum = np.fft.rfft(left)
        right_spectrum = np.fft.rfft(right)
        magnitude = np.sqrt(
            np.maximum(np.abs(left_spectrum), 1e-12) ** (2.0 * (1.0 - progress))
            * np.maximum(np.abs(right_spectrum), 1e-12) ** (2.0 * progress)
        )
        phase = _phase_lerp(np.angle(left_spectrum), np.angle(right_spectrum), progress)
        harmonic_cycle = np.fft.irfft(magnitude * np.exp(1j * phase), n=left.size)
        cycle = 0.55 * phase_cycle + 0.45 * harmonic_cycle
        evidence.append(f"perceptual hybrid of phase alignment shift {shift} and harmonic path")
    else:
        raise WavetableContractError("unsupported interpolation method")
    return np.asarray(cycle, dtype=np.float64), tuple(evidence)


def _protect_cycle(
    cycle: np.ndarray,
    left: np.ndarray,
    right: np.ndarray,
    progress: float,
    *,
    protect_level: bool,
    protect_fundamental: bool,
    protect_polarity: bool,
) -> tuple[np.ndarray, tuple[str, ...]]:
    protected = np.asarray(cycle, dtype=np.float64)
    evidence: list[str] = []
    target_rms = (1.0 - progress) * _rms(left) + progress * _rms(right)
    target_fundamental = (
        (1.0 - progress) * _fundamental(left) + progress * _fundamental(right)
    )
    if protect_polarity and protected.size:
        weighted_correlation = (
            (1.0 - progress) * _correlation(protected, left)
            + progress * _correlation(protected, right)
        )
        if weighted_correlation < 0.0:
            protected = -protected
            evidence.append("global polarity inverted to preserve endpoint orientation")
        else:
            evidence.append("global polarity preserved against endpoint orientation")
    if protect_fundamental and protected.size:
        spectrum = np.fft.rfft(protected)
        if spectrum.size > 1:
            phase = float(np.angle(spectrum[1]))
            spectrum[1] = target_fundamental * (protected.size / 2.0) * np.exp(1j * phase)
            protected = np.fft.irfft(spectrum, n=protected.size)
            evidence.append("fundamental magnitude protected against endpoint target")
    if protect_level:
        measured = _rms(protected)
        if measured > 1e-15 and target_rms > 0.0:
            protected = protected * (target_rms / measured)
        elif target_rms <= 1e-15:
            protected = np.zeros_like(protected)
        evidence.append("RMS level protected against endpoint target")
    peak = float(np.max(np.abs(protected))) if protected.size else 0.0
    if peak > 1.0:
        protected = protected / peak
        evidence.append("peak normalized to XT-safe generated range")
    return protected, tuple(evidence)


def progression_value(
    fraction: float,
    curve: ProgressionCurve,
    complexity: float = 0.5,
) -> float:
    """Map one normalized slot fraction to deterministic interpolation progress."""

    value = _ratio(fraction, name="fraction")
    complexity_value = _ratio(complexity, name="complexity")
    if not isinstance(curve, ProgressionCurve):
        raise WavetableContractError("curve must be ProgressionCurve")
    if curve is ProgressionCurve.LINEAR:
        result = value
    elif curve is ProgressionCurve.SMOOTHSTEP:
        result = value * value * (3.0 - 2.0 * value)
    elif curve is ProgressionCurve.EXPONENTIAL:
        result = value * value
    elif curve is ProgressionCurve.LOGARITHMIC:
        result = math.sqrt(value)
    else:
        smooth = value * value * (3.0 - 2.0 * value)
        exponent = value ** (1.55 - 0.8 * complexity_value)
        result = (1.0 - complexity_value) * smooth + complexity_value * exponent
    return _q(max(0.0, min(1.0, result)))


@dataclass(frozen=True, slots=True)
class InterpolationPolicy:
    schema_version: int = WAVETABLE_INTERPOLATION_SCHEMA_VERSION
    method_priority: tuple[GenerationMethod, ...] = _SUPPORTED_METHODS
    adaptive_method_selection: bool = True
    protect_fundamental: bool = True
    protect_level: bool = True
    protect_polarity: bool = True
    level_tolerance: float = 0.16
    fundamental_tolerance: float = 0.22

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_INTERPOLATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported interpolation-policy schema version")
        methods = tuple(self.method_priority)
        object.__setattr__(self, "method_priority", methods)
        if not methods or len(set(methods)) != len(methods):
            raise WavetableContractError("method_priority must contain unique methods")
        if any(method not in _SUPPORTED_METHODS for method in methods):
            raise WavetableContractError("method_priority contains an unsupported method")
        for name in (
            "adaptive_method_selection",
            "protect_fundamental",
            "protect_level",
            "protect_polarity",
        ):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        for name in ("level_tolerance", "fundamental_tolerance"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 < value <= 1.0:
                raise WavetableContractError(f"{name} must be finite and in (0, 1]")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "method_priority": [method.value for method in self.method_priority],
            "adaptive_method_selection": self.adaptive_method_selection,
            "protect_fundamental": self.protect_fundamental,
            "protect_level": self.protect_level,
            "protect_polarity": self.protect_polarity,
            "level_tolerance": self.level_tolerance,
            "fundamental_tolerance": self.fundamental_tolerance,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_INTERPOLATION_POLICY = InterpolationPolicy()


@dataclass(frozen=True, slots=True)
class InterpolatedWave:
    schema_version: int
    method: GenerationMethod
    progress: float
    stored_samples: tuple[int, ...]
    source_candidate_ids: tuple[str, str]
    metrics: WaveBuildMetrics
    target_rms: float
    measured_rms: float
    target_fundamental: float
    measured_fundamental: float
    level_error: float
    fundamental_error: float
    left_distance: float
    right_distance: float
    polarity_score: float
    objective_score: float
    evidence: tuple[str, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_INTERPOLATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported interpolated-wave schema version")
        if self.method not in _SUPPORTED_METHODS:
            raise WavetableContractError("method must be a supported interpolation method")
        _ratio(self.progress, name="progress")
        object.__setattr__(self, "stored_samples", _stored_samples(self.stored_samples))
        source_ids = tuple(self.source_candidate_ids)
        object.__setattr__(self, "source_candidate_ids", source_ids)
        if len(source_ids) != 2 or source_ids[0] == source_ids[1]:
            raise WavetableContractError("interpolated wave requires two distinct source IDs")
        for value in source_ids:
            _normalized(value, name="source_candidate_id")
        if not isinstance(self.metrics, WaveBuildMetrics):
            raise WavetableContractError("metrics must be WaveBuildMetrics")
        for name in (
            "target_rms",
            "measured_rms",
            "target_fundamental",
            "measured_fundamental",
            "level_error",
            "fundamental_error",
            "left_distance",
            "right_distance",
            "polarity_score",
            "objective_score",
        ):
            _ratio(getattr(self, name), name=name)
        object.__setattr__(self, "evidence", _entries(self.evidence, name="evidence", allow_empty=False))
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        _normalized(self.reason, name="reason")

    @property
    def stored_samples_sha256(self) -> str:
        return sha256(bytes(sample + 128 for sample in self.stored_samples)).hexdigest()

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "method": self.method.value,
            "progress": self.progress,
            "stored_samples": list(self.stored_samples),
            "stored_samples_sha256": self.stored_samples_sha256,
            "source_candidate_ids": list(self.source_candidate_ids),
            "metrics": self.metrics.to_dict(),
            "target_rms": self.target_rms,
            "measured_rms": self.measured_rms,
            "target_fundamental": self.target_fundamental,
            "measured_fundamental": self.measured_fundamental,
            "level_error": self.level_error,
            "fundamental_error": self.fundamental_error,
            "left_distance": self.left_distance,
            "right_distance": self.right_distance,
            "polarity_score": self.polarity_score,
            "objective_score": self.objective_score,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _interpolated_metrics(
    left: WaveBuildMetrics,
    right: WaveBuildMetrics,
    progress: float,
    method: GenerationMethod,
) -> WaveBuildMetrics:
    names = (
        "quality_score",
        "usefulness_score",
        "stability_score",
        "harmonic_richness",
        "brightness",
        "bass_power",
        "source_fidelity",
        "xt_compatibility",
        "perceptual_novelty",
    )
    values = {
        name: _q((1.0 - progress) * getattr(left, name) + progress * getattr(right, name))
        for name in names
    }
    return WaveBuildMetrics(
        **values,
        reason=f"Deterministic {method.value} transition metrics between two V8-D keyframes.",
    )


def interpolate_xt_wave(
    left: WavetableCandidate,
    right: WavetableCandidate,
    progress: float,
    method: GenerationMethod,
    policy: InterpolationPolicy = DEFAULT_INTERPOLATION_POLICY,
) -> InterpolatedWave:
    """Generate one XT-native stored half-wave between two immutable candidates."""

    if not isinstance(left, WavetableCandidate) or not isinstance(right, WavetableCandidate):
        raise WavetableContractError("left and right must be WavetableCandidate values")
    if left.candidate_id == right.candidate_id:
        raise WavetableContractError("interpolation endpoints must be distinct candidates")
    if not isinstance(policy, InterpolationPolicy):
        raise WavetableContractError("policy must be InterpolationPolicy")
    value = _ratio(progress, name="progress")
    if method not in policy.method_priority:
        raise WavetableContractError("method is not enabled by interpolation policy")
    left_cycle = _full_cycle(left.stored_samples)
    right_cycle = _full_cycle(right.stored_samples)
    raw, method_evidence = _raw_interpolation(left_cycle, right_cycle, value, method)
    protected, protection_evidence = _protect_cycle(
        raw,
        left_cycle,
        right_cycle,
        value,
        protect_level=policy.protect_level,
        protect_fundamental=policy.protect_fundamental,
        protect_polarity=policy.protect_polarity,
    )
    stored = (
        left.stored_samples
        if value == 0.0
        else right.stored_samples
        if value == 1.0
        else _quantize_half(protected)
    )
    measured_cycle = _full_cycle(stored)
    left_shape = analyze_wave_shape(left)
    right_shape = analyze_wave_shape(right)
    measured_shape = analyze_wave_shape(stored)
    target_rms = _q((1.0 - value) * left_shape.rms + value * right_shape.rms)
    target_fundamental = _q(
        (1.0 - value) * _fundamental(left_cycle) + value * _fundamental(right_cycle)
    )
    measured_fundamental = _q(_fundamental(measured_cycle))
    level_error = _q(min(1.0, abs(measured_shape.rms - target_rms)))
    fundamental_error = _q(min(1.0, abs(measured_fundamental - target_fundamental)))
    left_distance_report = compare_wave_shapes(left.stored_samples, stored)
    right_distance_report = compare_wave_shapes(stored, right.stored_samples)
    endpoint_report = compare_wave_shapes(left, right)
    expected_left = value * endpoint_report.perceptual_distance
    expected_right = (1.0 - value) * endpoint_report.perceptual_distance
    path_error = min(
        1.0,
        0.5 * abs(left_distance_report.perceptual_distance - expected_left)
        + 0.5 * abs(right_distance_report.perceptual_distance - expected_right),
    )
    weighted_correlation = (
        (1.0 - value) * left_distance_report.correlation
        + value * right_distance_report.correlation
    )
    polarity_score = _q(max(0.0, min(1.0, (weighted_correlation + 1.0) / 2.0)))
    level_score = max(0.0, 1.0 - level_error / policy.level_tolerance)
    fundamental_score = max(
        0.0, 1.0 - fundamental_error / policy.fundamental_tolerance
    )
    path_score = max(0.0, 1.0 - path_error)
    peak_score = max(0.0, 1.0 - max(0.0, measured_shape.peak - 0.95) / 0.05)
    objective = _q(
        0.30 * path_score
        + 0.25 * level_score
        + 0.20 * fundamental_score
        + 0.15 * polarity_score
        + 0.10 * peak_score
    )
    warnings: list[str] = []
    if level_error > policy.level_tolerance:
        warnings.append("interpolated level exceeds policy tolerance")
    if fundamental_error > policy.fundamental_tolerance:
        warnings.append("interpolated fundamental exceeds policy tolerance")
    if policy.protect_polarity and polarity_score < 0.25:
        warnings.append("interpolated polarity continuity is weak")
    return InterpolatedWave(
        schema_version=WAVETABLE_INTERPOLATION_SCHEMA_VERSION,
        method=method,
        progress=_q(value),
        stored_samples=stored,
        source_candidate_ids=(left.candidate_id, right.candidate_id),
        metrics=_interpolated_metrics(left.metrics, right.metrics, value, method),
        target_rms=target_rms,
        measured_rms=measured_shape.rms,
        target_fundamental=target_fundamental,
        measured_fundamental=measured_fundamental,
        level_error=level_error,
        fundamental_error=fundamental_error,
        left_distance=left_distance_report.perceptual_distance,
        right_distance=right_distance_report.perceptual_distance,
        polarity_score=polarity_score,
        objective_score=objective,
        evidence=tuple(dict.fromkeys(method_evidence + protection_evidence)),
        warnings=tuple(warnings),
        reason="XT-native transition generated without changing either source keyframe.",
    )


def select_interpolation_method(
    left: WavetableCandidate,
    right: WavetableCandidate,
    progress: float,
    allowed_methods: Sequence[GenerationMethod],
    policy: InterpolationPolicy = DEFAULT_INTERPOLATION_POLICY,
) -> InterpolatedWave:
    """Select the best enabled interpolation family by deterministic protection score."""

    if not isinstance(policy, InterpolationPolicy):
        raise WavetableContractError("policy must be InterpolationPolicy")
    allowed = tuple(allowed_methods)
    if not allowed:
        raise WavetableContractError("allowed_methods must not be empty")
    if len(set(allowed)) != len(allowed):
        raise WavetableContractError("allowed_methods must be unique")
    candidates = tuple(method for method in policy.method_priority if method in allowed)
    if not candidates:
        raise WavetableContractError("no supported interpolation method is enabled")
    if not policy.adaptive_method_selection:
        return interpolate_xt_wave(left, right, progress, candidates[0], policy)
    results = tuple(
        interpolate_xt_wave(left, right, progress, method, policy)
        for method in candidates
    )
    priority = {method: index for index, method in enumerate(policy.method_priority)}
    return min(
        results,
        key=lambda item: (
            -item.objective_score,
            item.level_error,
            item.fundamental_error,
            priority[item.method],
            item.stored_samples_sha256,
        ),
    )


__all__ = [
    "DEFAULT_INTERPOLATION_POLICY",
    "WAVETABLE_INTERPOLATION_SCHEMA_VERSION",
    "InterpolatedWave",
    "InterpolationPolicy",
    "interpolate_xt_wave",
    "progression_value",
    "select_interpolation_method",
]
