from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any


class RegionKind(str, Enum):
    SILENCE = "silence"
    ATTACK = "attack"
    ESTABLISHMENT = "establishment"
    SUSTAIN = "sustain"
    EVOLUTION = "evolution"
    SATURATION = "saturation"
    REDUNDANCY = "redundancy"
    DISAPPEARANCE = "disappearance"
    NOISE = "noise"


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
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class InterestRegion:
    index: int
    source_segment_index: int
    start_sample: int
    end_sample: int
    sample_rate: int
    kind: RegionKind
    mean_rms: float
    voiced_frame_ratio: float
    mean_spectral_flux: float
    saturation_score: float
    complexity_score: float
    useful_change_score: float
    redundancy_score: float
    interest_score: float
    allocation_weight: float
    useful_change: bool
    reason: str

    def __post_init__(self) -> None:
        if self.index < 0 or self.source_segment_index < 0:
            raise ValueError("region indexes must not be negative")
        if self.start_sample < 0 or self.end_sample <= self.start_sample:
            raise ValueError("region bounds are invalid")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if not isinstance(self.kind, RegionKind):
            raise ValueError("kind must be a RegionKind")
        for name in ("mean_rms", "mean_spectral_flux"):
            if _finite(getattr(self, name), name=name) < 0.0:
                raise ValueError(f"{name} must not be negative")
        for name in (
            "voiced_frame_ratio",
            "saturation_score",
            "complexity_score",
            "useful_change_score",
            "redundancy_score",
            "interest_score",
            "allocation_weight",
        ):
            _ratio(getattr(self, name), name=name)
        if not self.reason or self.reason.strip() != self.reason:
            raise ValueError("reason must be a non-empty normalized string")

    @property
    def duration_samples(self) -> int:
        return self.end_sample - self.start_sample

    @property
    def duration_seconds(self) -> float:
        return float(self.duration_samples / self.sample_rate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "source_segment_index": self.source_segment_index,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "sample_rate": self.sample_rate,
            "duration_samples": self.duration_samples,
            "duration_seconds": self.duration_seconds,
            "kind": self.kind.value,
            "mean_rms": self.mean_rms,
            "voiced_frame_ratio": self.voiced_frame_ratio,
            "mean_spectral_flux": self.mean_spectral_flux,
            "saturation_score": self.saturation_score,
            "complexity_score": self.complexity_score,
            "useful_change_score": self.useful_change_score,
            "redundancy_score": self.redundancy_score,
            "interest_score": self.interest_score,
            "allocation_weight": self.allocation_weight,
            "useful_change": self.useful_change,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RegionInterestAnalysis:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    signal_analysis_sha256: str
    signal_extension_analysis_sha256: str
    segmentation_analysis_sha256: str
    redundancy_minimum_duration_ms: float
    redundancy_flux_threshold: float
    useful_change_threshold: float
    regions: tuple[InterestRegion, ...]
    useful_region_indices: tuple[int, ...]
    redundant_region_indices: tuple[int, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported region-interest schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "signal_analysis_sha256",
            "signal_extension_analysis_sha256",
            "segmentation_analysis_sha256",
        ):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if _finite(
            self.redundancy_minimum_duration_ms,
            name="redundancy_minimum_duration_ms",
        ) <= 0.0:
            raise ValueError("redundancy_minimum_duration_ms must be positive")
        _ratio(self.redundancy_flux_threshold, name="redundancy_flux_threshold")
        _ratio(self.useful_change_threshold, name="useful_change_threshold")
        if not self.regions:
            raise ValueError("regions must not be empty")
        if tuple(region.index for region in self.regions) != tuple(range(len(self.regions))):
            raise ValueError("region indexes must be contiguous from zero")
        if self.regions[0].start_sample != 0 or self.regions[-1].end_sample != self.sample_count:
            raise ValueError("regions must cover the complete source")
        for left, right in zip(self.regions, self.regions[1:]):
            if left.end_sample != right.start_sample:
                raise ValueError("regions must be contiguous and non-overlapping")
        weights = sum(region.allocation_weight for region in self.regions)
        active = [region for region in self.regions if region.kind is not RegionKind.SILENCE]
        if active and not math.isclose(weights, 1.0, abs_tol=1e-12):
            raise ValueError("active region allocation weights must sum to one")
        valid = set(range(len(self.regions)))
        for indexes in (self.useful_region_indices, self.redundant_region_indices):
            if tuple(sorted(set(indexes))) != indexes:
                raise ValueError("region index collections must be sorted and unique")
            if any(index not in valid for index in indexes):
                raise ValueError("region index is outside the valid range")
        expected_useful = tuple(
            region.index for region in self.regions if region.useful_change
        )
        if self.useful_region_indices != expected_useful:
            raise ValueError("useful_region_indices do not match region flags")
        expected_redundant = tuple(
            region.index
            for region in self.regions
            if region.kind is RegionKind.REDUNDANCY
        )
        if self.redundant_region_indices != expected_redundant:
            raise ValueError("redundant_region_indices do not match region kinds")
        for region in self.regions:
            if region.kind is RegionKind.SILENCE and region.allocation_weight != 0.0:
                raise ValueError("silent regions must have zero allocation weight")
        if not self.reason:
            raise ValueError("reason must not be empty")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "signal_analysis_sha256": self.signal_analysis_sha256,
            "signal_extension_analysis_sha256": self.signal_extension_analysis_sha256,
            "segmentation_analysis_sha256": self.segmentation_analysis_sha256,
            "redundancy_minimum_duration_ms": self.redundancy_minimum_duration_ms,
            "redundancy_flux_threshold": self.redundancy_flux_threshold,
            "useful_change_threshold": self.useful_change_threshold,
            "regions": [region.to_dict() for region in self.regions],
            "useful_region_indices": list(self.useful_region_indices),
            "redundant_region_indices": list(self.redundant_region_indices),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class RegionSlotAllocation:
    schema_version: int
    region_interest_analysis_sha256: str
    total_slots: int
    region_count: int
    region_slot_counts: tuple[int, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported region-slot allocation schema version")
        if not _hash_is_valid(self.region_interest_analysis_sha256):
            raise ValueError("region_interest_analysis_sha256 must be a SHA-256 digest")
        if self.total_slots <= 0 or self.region_count <= 0:
            raise ValueError("total_slots and region_count must be positive")
        if len(self.region_slot_counts) != self.region_count:
            raise ValueError("region_slot_counts length must equal region_count")
        if any(value < 0 for value in self.region_slot_counts):
            raise ValueError("region slot counts must not be negative")
        if sum(self.region_slot_counts) != self.total_slots:
            raise ValueError("region slot counts must sum to total_slots")
        if not self.reason:
            raise ValueError("reason must not be empty")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "region_interest_analysis_sha256": self.region_interest_analysis_sha256,
            "total_slots": self.total_slots,
            "region_count": self.region_count,
            "region_slot_counts": list(self.region_slot_counts),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _mean_saturation_for_range(
    saturation_analysis: Any,
    start_sample: int,
    end_sample: int,
) -> float:
    values = [
        float(frame.saturation_score)
        for frame in saturation_analysis.frames
        if frame.start_sample < end_sample
        and frame.start_sample + frame.sample_count > start_sample
    ]
    return 0.0 if not values else float(sum(values) / len(values))


def _base_kind(segment: Any, *, first_active: bool) -> tuple[RegionKind, str]:
    value = segment.kind.value
    if value == "silence":
        return RegionKind.SILENCE, "The source segment is below the active RMS gate."
    if value == "attack":
        return RegionKind.ATTACK, "The source segment is the qualified onset attack."
    if value == "release":
        return RegionKind.DISAPPEARANCE, "The release segment describes source disappearance."
    if value == "transition":
        if first_active:
            return RegionKind.ESTABLISHMENT, "The first post-onset transition establishes the source state."
        return RegionKind.EVOLUTION, "Change-point or spectral-flux evidence marks useful evolution."
    if first_active:
        return RegionKind.ESTABLISHMENT, "The first active non-attack region establishes the stable source state."
    return RegionKind.SUSTAIN, "The active stable segment represents sustained source content."


def analyze_region_interest(
    signal_analysis: Any,
    signal_extension_analysis: Any,
    segmentation_analysis: Any,
    *,
    redundancy_minimum_duration_ms: float = 750.0,
    redundancy_representative_duration_ms: float = 250.0,
    redundancy_flux_threshold: float = 0.04,
    useful_change_threshold: float = 0.35,
    saturation_region_threshold: float = 0.45,
    noise_region_threshold: float = 0.55,
) -> RegionInterestAnalysis:
    if signal_analysis.sample_rate != signal_extension_analysis.sample_rate:
        raise ValueError("signal analyses have inconsistent sample rates")
    if signal_analysis.sample_count != signal_extension_analysis.sample_count:
        raise ValueError("signal analyses have inconsistent sample counts")
    if signal_analysis.sample_sha256 != signal_extension_analysis.sample_sha256:
        raise ValueError("signal analyses have inconsistent sample hashes")
    if signal_extension_analysis.signal_analysis_sha256 != signal_analysis.analysis_sha256:
        raise ValueError("signal extension does not link to the signal analysis")
    if segmentation_analysis.signal_analysis_sha256 != signal_analysis.analysis_sha256:
        raise ValueError("segmentation does not link to the signal analysis")
    if segmentation_analysis.sample_rate != signal_analysis.sample_rate:
        raise ValueError("segmentation sample rate is inconsistent")
    if segmentation_analysis.sample_count != signal_analysis.sample_count:
        raise ValueError("segmentation sample count is inconsistent")
    if segmentation_analysis.sample_sha256 != signal_analysis.sample_sha256:
        raise ValueError("segmentation sample hash is inconsistent")
    if not segmentation_analysis.segments:
        raise ValueError("segmentation must contain at least one segment")
    if segmentation_analysis.segments[0].start_sample != 0:
        raise ValueError("segmentation must begin at sample zero")
    if segmentation_analysis.segments[-1].end_sample != signal_analysis.sample_count:
        raise ValueError("segmentation must cover the complete source")
    for left, right in zip(
        segmentation_analysis.segments, segmentation_analysis.segments[1:]
    ):
        if left.end_sample != right.start_sample:
            raise ValueError("segmentation must be contiguous and non-overlapping")
    for name, value in (
        ("redundancy_minimum_duration_ms", redundancy_minimum_duration_ms),
        ("redundancy_representative_duration_ms", redundancy_representative_duration_ms),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and positive")
    for name, value in (
        ("redundancy_flux_threshold", redundancy_flux_threshold),
        ("useful_change_threshold", useful_change_threshold),
        ("saturation_region_threshold", saturation_region_threshold),
        ("noise_region_threshold", noise_region_threshold),
    ):
        _ratio(value, name=name)

    sample_rate = int(signal_analysis.sample_rate)
    active_segments = [
        segment for segment in segmentation_analysis.segments if segment.kind.value != "silence"
    ]
    establishment_candidates = [
        segment for segment in active_segments if segment.kind.value != "attack"
    ]
    first_active_index = (
        None if not establishment_candidates else establishment_candidates[0].index
    )
    global_complexity = float(signal_extension_analysis.complexity_analysis.complexity_score)
    noise = signal_analysis.noise_analysis
    noise_ratio = 0.0 if noise.signal_rms <= 1e-15 else float(
        min(1.0, max(0.0, noise.noise_floor_rms / noise.signal_rms))
    )

    provisional: list[dict[str, Any]] = []
    for segment in segmentation_analysis.segments:
        first_active = segment.index == first_active_index
        base_kind, reason = _base_kind(
            segment,
            first_active=first_active,
        )
        saturation_score = _mean_saturation_for_range(
            signal_extension_analysis.saturation_analysis,
            segment.start_sample,
            segment.end_sample,
        )
        flux_score = float(min(1.0, segment.mean_spectral_flux / max(redundancy_flux_threshold, 1e-12)))
        onset_score = float(min(1.0, segment.maximum_onset_strength / 8.0))
        event_score = float(min(1.0, (segment.change_point_count + segment.transient_count) / 3.0))
        useful_change_score = float(
            min(1.0, 0.50 * flux_score + 0.30 * event_score + 0.20 * onset_score)
        )
        redundancy_score = float(
            min(
                1.0,
                max(
                    0.0,
                    (1.0 - flux_score)
                    * segment.active_frame_ratio
                    * (0.5 + 0.5 * segment.voiced_frame_ratio),
                ),
            )
        )
        kind = base_kind
        if base_kind is not RegionKind.SILENCE:
            if saturation_score >= saturation_region_threshold:
                kind = RegionKind.SATURATION
                reason = "Frame-local saturation exceeds the configured region gate."
            elif segment.voiced_frame_ratio <= 0.20 and max(noise_ratio, global_complexity) >= noise_region_threshold:
                kind = RegionKind.NOISE
                reason = "Low voiced coverage with material noise or complexity marks a noise region."

        duration_ms = segment.duration_seconds * 1000.0
        should_split_redundancy = bool(
            kind is RegionKind.SUSTAIN
            and duration_ms >= redundancy_minimum_duration_ms
            and segment.mean_spectral_flux <= redundancy_flux_threshold
            and redundancy_representative_duration_ms < duration_ms
        )
        parts: list[tuple[int, int, RegionKind, str, float]]
        if should_split_redundancy:
            split = min(
                segment.end_sample - 1,
                segment.start_sample
                + max(1, int(round(redundancy_representative_duration_ms * sample_rate / 1000.0))),
            )
            parts = [
                (
                    segment.start_sample,
                    split,
                    RegionKind.SUSTAIN,
                    "The leading stable portion is retained as the representative sustain state.",
                    0.0,
                ),
                (
                    split,
                    segment.end_sample,
                    RegionKind.REDUNDANCY,
                    "A long low-flux stable tail is marked redundant instead of receiving uniform density.",
                    max(redundancy_score, 0.75),
                ),
            ]
        else:
            parts = [
                (
                    segment.start_sample,
                    segment.end_sample,
                    kind,
                    reason,
                    redundancy_score if kind is RegionKind.REDUNDANCY else 0.0,
                )
            ]

        for start, end, part_kind, part_reason, part_redundancy in parts:
            base_interest = {
                RegionKind.SILENCE: 0.0,
                RegionKind.ATTACK: 0.70,
                RegionKind.ESTABLISHMENT: 0.80,
                RegionKind.SUSTAIN: 0.45,
                RegionKind.EVOLUTION: 0.90,
                RegionKind.SATURATION: 0.75,
                RegionKind.REDUNDANCY: 0.05,
                RegionKind.DISAPPEARANCE: 0.35,
                RegionKind.NOISE: 0.60,
            }[part_kind]
            interest = float(
                min(
                    1.0,
                    max(
                        0.0,
                        base_interest
                        + 0.20 * useful_change_score
                        + 0.10 * saturation_score
                        + 0.10 * global_complexity
                        - 0.35 * part_redundancy,
                    ),
                )
            )
            provisional.append(
                {
                    "source_segment_index": segment.index,
                    "start_sample": start,
                    "end_sample": end,
                    "kind": part_kind,
                    "mean_rms": float(segment.mean_rms),
                    "voiced_frame_ratio": float(segment.voiced_frame_ratio),
                    "mean_spectral_flux": float(segment.mean_spectral_flux),
                    "saturation_score": saturation_score,
                    "complexity_score": global_complexity,
                    "useful_change_score": useful_change_score,
                    "redundancy_score": part_redundancy,
                    "interest_score": interest,
                    "useful_change": useful_change_score >= useful_change_threshold,
                    "reason": part_reason,
                }
            )

    active_interest_total = sum(
        item["interest_score"]
        for item in provisional
        if item["kind"] is not RegionKind.SILENCE
    )
    regions: list[InterestRegion] = []
    for index, item in enumerate(provisional):
        if item["kind"] is RegionKind.SILENCE or active_interest_total <= 1e-24:
            weight = 0.0
        else:
            weight = float(item["interest_score"] / active_interest_total)
        regions.append(
            InterestRegion(
                index=index,
                source_segment_index=int(item["source_segment_index"]),
                start_sample=int(item["start_sample"]),
                end_sample=int(item["end_sample"]),
                sample_rate=sample_rate,
                kind=item["kind"],
                mean_rms=float(item["mean_rms"]),
                voiced_frame_ratio=float(item["voiced_frame_ratio"]),
                mean_spectral_flux=float(item["mean_spectral_flux"]),
                saturation_score=float(item["saturation_score"]),
                complexity_score=float(item["complexity_score"]),
                useful_change_score=float(item["useful_change_score"]),
                redundancy_score=float(item["redundancy_score"]),
                interest_score=float(item["interest_score"]),
                allocation_weight=weight,
                useful_change=bool(item["useful_change"]),
                reason=str(item["reason"]),
            )
        )

    useful = tuple(region.index for region in regions if region.useful_change)
    redundant = tuple(
        region.index for region in regions if region.kind is RegionKind.REDUNDANCY
    )
    return RegionInterestAnalysis(
        schema_version=1,
        sample_rate=sample_rate,
        sample_count=int(signal_analysis.sample_count),
        sample_sha256=str(signal_analysis.sample_sha256),
        signal_analysis_sha256=str(signal_analysis.analysis_sha256),
        signal_extension_analysis_sha256=str(signal_extension_analysis.analysis_sha256),
        segmentation_analysis_sha256=str(segmentation_analysis.analysis_sha256),
        redundancy_minimum_duration_ms=float(redundancy_minimum_duration_ms),
        redundancy_flux_threshold=float(redundancy_flux_threshold),
        useful_change_threshold=float(useful_change_threshold),
        regions=tuple(regions),
        useful_region_indices=useful,
        redundant_region_indices=redundant,
        reason=(
            "Regions are contiguous, explicitly classified, scored for useful change and "
            "redundancy, and normalized into deterministic interest weights."
        ),
    )


def allocate_region_slots(
    analysis: RegionInterestAnalysis,
    *,
    total_slots: int = 61,
    minimum_active_slots: int = 1,
) -> RegionSlotAllocation:
    if total_slots <= 0:
        raise ValueError("total_slots must be positive")
    if minimum_active_slots < 0:
        raise ValueError("minimum_active_slots must not be negative")
    active = [
        region for region in analysis.regions if region.kind is not RegionKind.SILENCE
    ]
    if not active:
        counts = [0] * len(analysis.regions)
        counts[0] = total_slots
        return RegionSlotAllocation(
            schema_version=1,
            region_interest_analysis_sha256=analysis.analysis_sha256,
            total_slots=total_slots,
            region_count=len(analysis.regions),
            region_slot_counts=tuple(counts),
            reason="The source has no active region, so every slot is assigned to the first region.",
        )
    required = minimum_active_slots * len(active)
    if required > total_slots:
        raise ValueError("minimum active slot requirement exceeds total_slots")

    counts = [0] * len(analysis.regions)
    for region in active:
        counts[region.index] = minimum_active_slots
    remaining = total_slots - required
    exact = [region.allocation_weight * remaining for region in active]
    floors = [int(math.floor(value)) for value in exact]
    for region, value in zip(active, floors):
        counts[region.index] += value
    remainder = remaining - sum(floors)
    order = sorted(
        range(len(active)),
        key=lambda index: (
            -(exact[index] - floors[index]),
            -active[index].interest_score,
            active[index].index,
        ),
    )
    for index in order[:remainder]:
        counts[active[index].index] += 1

    return RegionSlotAllocation(
        schema_version=1,
        region_interest_analysis_sha256=analysis.analysis_sha256,
        total_slots=total_slots,
        region_count=len(analysis.regions),
        region_slot_counts=tuple(counts),
        reason=(
            "Slots are assigned by normalized region interest with deterministic largest-"
            "remainder rounding rather than uniform time density."
        ),
    )
