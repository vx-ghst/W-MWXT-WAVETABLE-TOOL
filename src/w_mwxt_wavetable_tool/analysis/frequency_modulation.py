from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any

import numpy as np


def _finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _ratio(value: float, *, name: str) -> float:
    result = _finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


@dataclass(frozen=True, slots=True)
class FrequencyModulationFrame:
    frame_index: int
    center_seconds: float
    frequency_hz: float
    deviation_cents: float
    rapid_component_cents: float
    periodicity_score: float

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame_index must not be negative")
        if _finite(self.center_seconds, name="center_seconds") < 0.0:
            raise ValueError("center_seconds must not be negative")
        if _finite(self.frequency_hz, name="frequency_hz") <= 0.0:
            raise ValueError("frequency_hz must be positive")
        _finite(self.deviation_cents, name="deviation_cents")
        _finite(self.rapid_component_cents, name="rapid_component_cents")
        _ratio(self.periodicity_score, name="periodicity_score")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "center_seconds": self.center_seconds,
            "frequency_hz": self.frequency_hz,
            "deviation_cents": self.deviation_cents,
            "rapid_component_cents": self.rapid_component_cents,
            "periodicity_score": self.periodicity_score,
        }


@dataclass(frozen=True, slots=True)
class FrequencyModulationAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    pitch_periodicity_analysis_sha256: str
    frames: tuple[FrequencyModulationFrame, ...]
    voiced_frame_count: int
    voiced_active_ratio: float
    reference_frequency_hz: float | None
    rapid_rms_cents: float
    rapid_peak_to_peak_cents: float
    modulation_rate_hz: float
    modulation_depth_cents: float
    rapid_fm_score: float
    confidence: float
    rapid_fm_detected: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported frequency-modulation schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in ("sample_sha256", "pitch_periodicity_analysis_sha256"):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if self.voiced_frame_count != len(self.frames):
            raise ValueError("voiced_frame_count must equal the frame tuple length")
        frame_indexes = tuple(frame.frame_index for frame in self.frames)
        if frame_indexes != tuple(sorted(set(frame_indexes))):
            raise ValueError("frequency-modulation frame indexes must be sorted and unique")
        _ratio(self.voiced_active_ratio, name="voiced_active_ratio")
        if self.reference_frequency_hz is not None and _finite(
            self.reference_frequency_hz, name="reference_frequency_hz"
        ) <= 0.0:
            raise ValueError("reference_frequency_hz must be positive when defined")
        for name in (
            "rapid_rms_cents",
            "rapid_peak_to_peak_cents",
            "modulation_rate_hz",
            "modulation_depth_cents",
        ):
            if _finite(getattr(self, name), name=name) < 0.0:
                raise ValueError(f"{name} must not be negative")
        _ratio(self.rapid_fm_score, name="rapid_fm_score")
        _ratio(self.confidence, name="confidence")
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "pitch_periodicity_analysis_sha256": self.pitch_periodicity_analysis_sha256,
            "frames": [frame.to_dict() for frame in self.frames],
            "voiced_frame_count": self.voiced_frame_count,
            "voiced_active_ratio": self.voiced_active_ratio,
            "reference_frequency_hz": self.reference_frequency_hz,
            "rapid_rms_cents": self.rapid_rms_cents,
            "rapid_peak_to_peak_cents": self.rapid_peak_to_peak_cents,
            "modulation_rate_hz": self.modulation_rate_hz,
            "modulation_depth_cents": self.modulation_depth_cents,
            "rapid_fm_score": self.rapid_fm_score,
            "confidence": self.confidence,
            "rapid_fm_detected": self.rapid_fm_detected,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or values.size <= 1:
        return values.copy()
    window = min(window, int(values.size))
    kernel = np.ones(window, dtype=np.float64) / window
    padded = np.pad(values, (window // 2, window - 1 - window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def analyze_frequency_modulation(
    pitch_periodicity_analysis: Any,
    *,
    slow_window_seconds: float = 0.12,
    minimum_depth_cents: float = 12.0,
    minimum_rate_hz: float = 3.0,
) -> FrequencyModulationAnalysis:
    if slow_window_seconds <= 0.0 or not math.isfinite(slow_window_seconds):
        raise ValueError("slow_window_seconds must be finite and positive")
    if minimum_depth_cents <= 0.0 or not math.isfinite(minimum_depth_cents):
        raise ValueError("minimum_depth_cents must be finite and positive")
    if minimum_rate_hz <= 0.0 or not math.isfinite(minimum_rate_hz):
        raise ValueError("minimum_rate_hz must be finite and positive")

    voiced = [
        (index, frame)
        for index, frame in enumerate(pitch_periodicity_analysis.frames)
        if bool(frame.voiced)
    ]
    reference = pitch_periodicity_analysis.frequency_hz
    if not voiced or reference is None:
        return FrequencyModulationAnalysis(
            schema_version=1,
            sample_rate=int(pitch_periodicity_analysis.sample_rate),
            sample_count=int(pitch_periodicity_analysis.sample_count),
            sample_sha256=str(pitch_periodicity_analysis.sample_sha256),
            pitch_periodicity_analysis_sha256=str(
                pitch_periodicity_analysis.analysis_sha256
            ),
            frames=(),
            voiced_frame_count=0,
            voiced_active_ratio=float(pitch_periodicity_analysis.voiced_active_ratio),
            reference_frequency_hz=None,
            rapid_rms_cents=0.0,
            rapid_peak_to_peak_cents=0.0,
            modulation_rate_hz=0.0,
            modulation_depth_cents=0.0,
            rapid_fm_score=0.0,
            confidence=0.0,
            rapid_fm_detected=False,
            reason="No voiced frame is available for rapid frequency-modulation analysis.",
        )

    times = np.asarray(
        [float(frame.center_seconds) for _, frame in voiced],
        dtype=np.float64,
    )
    frequencies = np.asarray(
        [float(frame.frequency_hz) for _, frame in voiced],
        dtype=np.float64,
    )
    cents = 1200.0 * np.log2(frequencies / float(reference))

    if times.size >= 2:
        time_step = float(np.median(np.diff(times)))
    else:
        time_step = float(pitch_periodicity_analysis.hop_size / pitch_periodicity_analysis.sample_rate)
    time_step = max(time_step, 1.0 / float(pitch_periodicity_analysis.sample_rate))
    window = max(1, int(round(slow_window_seconds / time_step)))
    if window % 2 == 0:
        window += 1
    slow = _moving_average(cents, window)
    rapid = cents - slow

    rapid_rms = float(np.sqrt(np.mean(np.square(rapid), dtype=np.float64)))
    rapid_peak_to_peak = float(np.ptp(rapid)) if rapid.size else 0.0
    modulation_depth = rapid_peak_to_peak / 2.0

    modulation_rate = 0.0
    if rapid.size >= 3 and times[-1] > times[0]:
        signs = np.sign(rapid)
        nonzero = np.flatnonzero(signs != 0.0)
        if nonzero.size >= 2:
            compact_signs = signs[nonzero]
            crossings = int(np.count_nonzero(compact_signs[1:] != compact_signs[:-1]))
            duration = float(times[nonzero[-1]] - times[nonzero[0]])
            if duration > 0.0:
                modulation_rate = float(crossings / (2.0 * duration))

    depth_score = float(min(1.0, modulation_depth / max(minimum_depth_cents, 1e-12)))
    rate_score = float(min(1.0, modulation_rate / max(minimum_rate_hz, 1e-12)))
    voiced_ratio = float(pitch_periodicity_analysis.voiced_active_ratio)
    periodicity = float(pitch_periodicity_analysis.periodicity_score)
    confidence = float(min(1.0, max(0.0, voiced_ratio * periodicity)))
    rapid_score = float(min(1.0, max(0.0, depth_score * rate_score * confidence)))
    detected = bool(
        modulation_depth >= minimum_depth_cents
        and modulation_rate >= minimum_rate_hz
        and confidence >= 0.25
    )

    frame_records = tuple(
        FrequencyModulationFrame(
            frame_index=int(source_index),
            center_seconds=float(time),
            frequency_hz=float(frequency),
            deviation_cents=float(deviation),
            rapid_component_cents=float(component),
            periodicity_score=float(frame.periodicity_score),
        )
        for source_index, time, frequency, deviation, component, frame in (
            (
                source_index,
                time,
                frequency,
                deviation,
                component,
                frame,
            )
            for (source_index, frame), time, frequency, deviation, component in zip(
                voiced, times, frequencies, cents, rapid
            )
        )
    )
    if detected:
        reason = (
            "Rapid pitch variation exceeds both the configured modulation-depth and "
            "modulation-rate gates."
        )
    else:
        reason = (
            "Rapid pitch variation does not exceed both the configured depth and rate "
            "gates with sufficient periodicity confidence."
        )

    return FrequencyModulationAnalysis(
        schema_version=1,
        sample_rate=int(pitch_periodicity_analysis.sample_rate),
        sample_count=int(pitch_periodicity_analysis.sample_count),
        sample_sha256=str(pitch_periodicity_analysis.sample_sha256),
        pitch_periodicity_analysis_sha256=str(
            pitch_periodicity_analysis.analysis_sha256
        ),
        frames=frame_records,
        voiced_frame_count=len(frame_records),
        voiced_active_ratio=voiced_ratio,
        reference_frequency_hz=float(reference),
        rapid_rms_cents=rapid_rms,
        rapid_peak_to_peak_cents=rapid_peak_to_peak,
        modulation_rate_hz=modulation_rate,
        modulation_depth_cents=modulation_depth,
        rapid_fm_score=rapid_score,
        confidence=confidence,
        rapid_fm_detected=detected,
        reason=reason,
    )
