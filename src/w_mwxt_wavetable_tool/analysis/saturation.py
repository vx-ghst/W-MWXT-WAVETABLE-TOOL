from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any

import numpy as np
import numpy.typing as npt

from .framing import iter_frames, validate_mono_samples
from ..errors import AnalysisError


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


def _canonical_hash(payload: dict[str, Any]) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sample_hash(samples: np.ndarray) -> str:
    return sha256(samples.astype("<f8", copy=False).tobytes(order="C")).hexdigest()


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


@dataclass(frozen=True, slots=True)
class SaturationFrameAnalysis:
    frame_index: int
    start_sample: int
    center_seconds: float
    sample_count: int
    rms: float
    peak_absolute: float
    crest_factor: float
    clipped_ratio: float
    near_clip_ratio: float
    flat_extreme_ratio: float
    asymmetry: float
    saturation_score: float

    def __post_init__(self) -> None:
        if self.frame_index < 0 or self.start_sample < 0 or self.sample_count <= 0:
            raise ValueError("frame identity is invalid")
        if _finite(self.center_seconds, name="center_seconds") < 0.0:
            raise ValueError("center_seconds must not be negative")
        for name in ("rms", "peak_absolute", "crest_factor"):
            if _finite(getattr(self, name), name=name) < 0.0:
                raise ValueError(f"{name} must not be negative")
        for name in (
            "clipped_ratio",
            "near_clip_ratio",
            "flat_extreme_ratio",
            "saturation_score",
        ):
            _ratio(getattr(self, name), name=name)
        if not -1.0 <= _finite(self.asymmetry, name="asymmetry") <= 1.0:
            raise ValueError("asymmetry must be between -1 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "start_sample": self.start_sample,
            "center_seconds": self.center_seconds,
            "sample_count": self.sample_count,
            "rms": self.rms,
            "peak_absolute": self.peak_absolute,
            "crest_factor": self.crest_factor,
            "clipped_ratio": self.clipped_ratio,
            "near_clip_ratio": self.near_clip_ratio,
            "flat_extreme_ratio": self.flat_extreme_ratio,
            "asymmetry": self.asymmetry,
            "saturation_score": self.saturation_score,
        }


@dataclass(frozen=True, slots=True)
class SaturationAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    frame_size: int
    hop_size: int
    clipping_threshold: float
    near_clip_threshold: float
    detection_threshold: float
    frames: tuple[SaturationFrameAnalysis, ...]
    mean_saturation_score: float
    maximum_saturation_score: float
    saturation_variation: float
    saturated_frame_ratio: float
    global_asymmetry: float
    saturation_detected: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported saturation schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if not _hash_is_valid(self.sample_sha256):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if self.frame_size <= 0 or self.hop_size <= 0:
            raise ValueError("frame_size and hop_size must be positive")
        for name in ("clipping_threshold", "near_clip_threshold"):
            if _finite(getattr(self, name), name=name) <= 0.0:
                raise ValueError(f"{name} must be positive")
        if not 0.0 < _finite(
            self.detection_threshold, name="detection_threshold"
        ) <= 1.0:
            raise ValueError("detection_threshold must be in (0, 1]")
        if self.near_clip_threshold > self.clipping_threshold:
            raise ValueError("near_clip_threshold must not exceed clipping_threshold")
        if not self.frames:
            raise ValueError("frames must not be empty")
        for name in (
            "mean_saturation_score",
            "maximum_saturation_score",
            "saturation_variation",
            "saturated_frame_ratio",
        ):
            _ratio(getattr(self, name), name=name)
        if not -1.0 <= _finite(self.global_asymmetry, name="global_asymmetry") <= 1.0:
            raise ValueError("global_asymmetry must be between -1 and 1")
        if not self.reason:
            raise ValueError("reason must not be empty")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "frame_size": self.frame_size,
            "hop_size": self.hop_size,
            "clipping_threshold": self.clipping_threshold,
            "near_clip_threshold": self.near_clip_threshold,
            "detection_threshold": self.detection_threshold,
            "frames": [frame.to_dict() for frame in self.frames],
            "mean_saturation_score": self.mean_saturation_score,
            "maximum_saturation_score": self.maximum_saturation_score,
            "saturation_variation": self.saturation_variation,
            "saturated_frame_ratio": self.saturated_frame_ratio,
            "global_asymmetry": self.global_asymmetry,
            "saturation_detected": self.saturation_detected,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _frame_metrics(
    frame: np.ndarray,
    *,
    clipping_threshold: float,
    near_clip_threshold: float,
) -> tuple[float, float, float, float, float, float, float, float]:
    absolute = np.abs(frame)
    rms = float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)))
    peak = float(np.max(absolute))
    crest = 0.0 if rms <= 1e-15 else float(peak / rms)
    clipped = float(np.mean(absolute >= clipping_threshold))
    near_clip = float(np.mean(absolute >= near_clip_threshold))
    differences = np.abs(np.diff(frame))
    flat_mask = (
        (absolute[:-1] >= near_clip_threshold)
        & (absolute[1:] >= near_clip_threshold)
        & (differences <= max(1e-12, clipping_threshold * 1e-5))
    )
    flat_extreme = 0.0 if flat_mask.size == 0 else float(np.mean(flat_mask))
    positive_peak = float(max(0.0, np.max(frame)))
    negative_peak = float(max(0.0, -np.min(frame)))
    denominator = positive_peak + negative_peak
    asymmetry = 0.0 if denominator <= 1e-15 else float(
        (positive_peak - negative_peak) / denominator
    )
    crest_suppression = float(min(1.0, max(0.0, (3.0 - crest) / 2.0)))
    activity = float(min(1.0, rms / 1e-5))
    score = float(
        min(
            1.0,
            max(
                0.0,
                0.25 * min(1.0, clipped * 200.0)
                + 0.20 * min(1.0, near_clip * 20.0)
                + 0.15 * min(1.0, flat_extreme * 100.0)
                + 0.40 * crest_suppression * activity,
            ),
        )
    )
    return rms, peak, crest, clipped, near_clip, flat_extreme, asymmetry, score


def analyze_saturation(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    frame_size: int = 2048,
    hop_size: int = 512,
    clipping_threshold: float = 1.0,
    near_clip_threshold: float = 0.98,
    detection_threshold: float = 0.35,
) -> SaturationAnalysis:
    data = validate_mono_samples(samples)
    if sample_rate <= 0:
        raise AnalysisError("sample_rate must be positive")
    if frame_size <= 0 or hop_size <= 0:
        raise AnalysisError("frame_size and hop_size must be positive")
    for name, value in (
        ("clipping_threshold", clipping_threshold),
        ("near_clip_threshold", near_clip_threshold),
        ("detection_threshold", detection_threshold),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise AnalysisError(f"{name} must be finite and positive")
    if near_clip_threshold > clipping_threshold:
        raise AnalysisError("near_clip_threshold must not exceed clipping_threshold")
    if detection_threshold > 1.0:
        raise AnalysisError("detection_threshold must not exceed one")

    records: list[SaturationFrameAnalysis] = []
    for frame_index, (start, frame) in enumerate(
        iter_frames(data, frame_size=frame_size, hop_size=hop_size)
    ):
        metrics = _frame_metrics(
            frame,
            clipping_threshold=clipping_threshold,
            near_clip_threshold=near_clip_threshold,
        )
        records.append(
            SaturationFrameAnalysis(
                frame_index=frame_index,
                start_sample=int(start),
                center_seconds=float((start + (frame.size - 1) / 2.0) / sample_rate),
                sample_count=int(frame.size),
                rms=metrics[0],
                peak_absolute=metrics[1],
                crest_factor=metrics[2],
                clipped_ratio=metrics[3],
                near_clip_ratio=metrics[4],
                flat_extreme_ratio=metrics[5],
                asymmetry=metrics[6],
                saturation_score=metrics[7],
            )
        )

    scores = np.asarray([record.saturation_score for record in records], dtype=np.float64)
    mean_score = float(np.mean(scores))
    maximum_score = float(np.max(scores))
    variation = float(min(1.0, np.std(scores, dtype=np.float64) * 2.0))
    saturated_ratio = float(np.mean(scores >= detection_threshold))
    positive_peak = float(max(0.0, np.max(data)))
    negative_peak = float(max(0.0, -np.min(data)))
    denominator = positive_peak + negative_peak
    global_asymmetry = 0.0 if denominator <= 1e-15 else float(
        (positive_peak - negative_peak) / denominator
    )
    detected = bool(maximum_score >= detection_threshold)
    reason = (
        "At least one frame exceeds the configured saturation score gate."
        if detected
        else "No frame exceeds the configured saturation score gate."
    )

    return SaturationAnalysis(
        schema_version=1,
        sample_rate=int(sample_rate),
        sample_count=int(data.size),
        sample_sha256=_sample_hash(data),
        frame_size=int(frame_size),
        hop_size=int(hop_size),
        clipping_threshold=float(clipping_threshold),
        near_clip_threshold=float(near_clip_threshold),
        detection_threshold=float(detection_threshold),
        frames=tuple(records),
        mean_saturation_score=mean_score,
        maximum_saturation_score=maximum_score,
        saturation_variation=variation,
        saturated_frame_ratio=saturated_ratio,
        global_asymmetry=global_asymmetry,
        saturation_detected=detected,
        reason=reason,
    )
