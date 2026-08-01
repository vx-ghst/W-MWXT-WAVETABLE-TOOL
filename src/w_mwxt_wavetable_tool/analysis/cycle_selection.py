from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any

from ..version import __version__
from .cycle_detection import (
    CycleCandidate,
    CycleCandidateStatus,
    CycleDiscoveryAnalysis,
    analyze_audio_source_cycles,
)
from .repitch import WorkingPitchPolicy
from .segmentation import AttackPolicy


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
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


def _clamp_ratio(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


class CycleSelectionPolicy(str, Enum):
    AUTO = "auto"
    FORCE = "force"


class CycleSelectionDecision(str, Enum):
    SELECTED = "selected"
    PITCH_UNAVAILABLE = "pitch_unavailable"
    NO_CANDIDATES = "no_candidates"
    NO_ACCEPTED_CANDIDATES = "no_accepted_candidates"


@dataclass(frozen=True, slots=True)
class RankedCycleCandidate:
    rank: int
    candidate_index: int
    candidate_sha256: str
    segment_index: int
    local_index: int
    start_sample: int
    end_sample: int
    quality_score: float
    temporal_novelty_score: float
    segment_novelty_score: float
    representative_score: float
    forced: bool
    selected: bool
    selection_reason: str

    def __post_init__(self) -> None:
        if self.rank <= 0:
            raise ValueError("rank must be positive")
        if self.candidate_index < 0 or self.segment_index < 0 or self.local_index < 0:
            raise ValueError("candidate indexes must not be negative")
        if self.start_sample < 0 or self.end_sample <= self.start_sample:
            raise ValueError("candidate sample bounds are invalid")
        if not _hash_is_valid(self.candidate_sha256):
            raise ValueError("candidate_sha256 must be a lowercase SHA-256 digest")
        for name in (
            "quality_score",
            "temporal_novelty_score",
            "segment_novelty_score",
            "representative_score",
        ):
            _require_ratio(getattr(self, name), name=name)
        if not self.selection_reason:
            raise ValueError("selection_reason must not be empty")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "candidate_index": self.candidate_index,
            "candidate_sha256": self.candidate_sha256,
            "segment_index": self.segment_index,
            "local_index": self.local_index,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "quality_score": self.quality_score,
            "temporal_novelty_score": self.temporal_novelty_score,
            "segment_novelty_score": self.segment_novelty_score,
            "representative_score": self.representative_score,
            "forced": self.forced,
            "selected": self.selected,
            "selection_reason": self.selection_reason,
        }

    @property
    def ranking_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["ranking_sha256"] = self.ranking_sha256
        return result


@dataclass(frozen=True, slots=True)
class SelectedCycleSet:
    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    cycle_discovery_analysis_sha256: str
    source_period_samples: float | None
    policy: CycleSelectionPolicy
    decision: CycleSelectionDecision
    top_n: int
    forced_candidate_index: int | None
    allow_rejected_forced_candidate: bool
    quality_weight: float
    temporal_novelty_weight: float
    segment_novelty_weight: float
    minimum_temporal_separation_periods: float
    ranked_candidates: tuple[RankedCycleCandidate, ...]
    selected_candidate_indices: tuple[int, ...]
    selected_candidate_sha256: tuple[str, ...]
    selected_ranking_sha256: tuple[str, ...]
    representative_segment_indices: tuple[int, ...]
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported selected-cycle-set schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise ValueError("tool_version must be a non-empty normalized string")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in ("sample_sha256", "cycle_discovery_analysis_sha256"):
            if not _hash_is_valid(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if not isinstance(self.policy, CycleSelectionPolicy):
            raise ValueError("policy must be a CycleSelectionPolicy")
        if not isinstance(self.decision, CycleSelectionDecision):
            raise ValueError("decision must be a CycleSelectionDecision")
        if self.source_period_samples is not None:
            period = _require_finite(
                self.source_period_samples,
                name="source_period_samples",
            )
            if period <= 0.0:
                raise ValueError("source_period_samples must be positive when defined")
        if not 1 <= self.top_n <= 61:
            raise ValueError("top_n must be between 1 and 61")
        for name in (
            "quality_weight",
            "temporal_novelty_weight",
            "segment_novelty_weight",
        ):
            _require_ratio(getattr(self, name), name=name)
        if not math.isclose(
            self.quality_weight
            + self.temporal_novelty_weight
            + self.segment_novelty_weight,
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("selection weights must sum to one")
        _require_non_negative(
            self.minimum_temporal_separation_periods,
            name="minimum_temporal_separation_periods",
        )
        if tuple(entry.rank for entry in self.ranked_candidates) != tuple(
            range(1, len(self.ranked_candidates) + 1)
        ):
            raise ValueError("ranking positions must be contiguous from one")
        candidate_indexes = tuple(
            entry.candidate_index for entry in self.ranked_candidates
        )
        if len(set(candidate_indexes)) != len(candidate_indexes):
            raise ValueError("ranked candidate indexes must be unique")
        selected_entries = tuple(
            entry for entry in self.ranked_candidates if entry.selected
        )
        if self.selected_candidate_indices != tuple(
            entry.candidate_index for entry in selected_entries
        ):
            raise ValueError("selected candidate indexes do not match ranking entries")
        if self.selected_candidate_sha256 != tuple(
            entry.candidate_sha256 for entry in selected_entries
        ):
            raise ValueError("selected candidate hashes do not match ranking entries")
        if self.selected_ranking_sha256 != tuple(
            entry.ranking_sha256 for entry in selected_entries
        ):
            raise ValueError("selected ranking hashes do not match ranking entries")
        if self.representative_segment_indices != tuple(
            sorted({entry.segment_index for entry in selected_entries})
        ):
            raise ValueError("representative segment indexes are inconsistent")
        if len(selected_entries) > self.top_n:
            raise ValueError("selected candidate count exceeds top_n")
        if self.policy is CycleSelectionPolicy.AUTO:
            if self.forced_candidate_index is not None:
                raise ValueError("auto policy cannot expose a forced candidate")
            if any(entry.forced for entry in self.ranked_candidates):
                raise ValueError("auto policy cannot mark a ranking entry forced")
        else:
            if self.forced_candidate_index is None:
                raise ValueError("force policy requires forced_candidate_index")
            forced_entries = tuple(
                entry for entry in self.ranked_candidates if entry.forced
            )
            if len(forced_entries) != 1:
                raise ValueError("force policy requires exactly one forced ranking entry")
            forced_entry = forced_entries[0]
            if (
                forced_entry.rank != 1
                or forced_entry.candidate_index != self.forced_candidate_index
                or not forced_entry.selected
            ):
                raise ValueError("forced candidate must be selected at rank one")
        if self.decision is CycleSelectionDecision.SELECTED:
            if not selected_entries:
                raise ValueError("selected decision requires at least one cycle")
        elif selected_entries:
            raise ValueError("non-selected decisions cannot expose selected cycles")
        if not self.decision_reason:
            raise ValueError("decision_reason must not be empty")

    @property
    def selected_count(self) -> int:
        return len(self.selected_candidate_indices)

    @property
    def ranking_sha256(self) -> tuple[str, ...]:
        return tuple(entry.ranking_sha256 for entry in self.ranked_candidates)

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
            "source_period_samples": self.source_period_samples,
            "policy": self.policy.value,
            "decision": self.decision.value,
            "top_n": self.top_n,
            "forced_candidate_index": self.forced_candidate_index,
            "allow_rejected_forced_candidate": (
                self.allow_rejected_forced_candidate
            ),
            "quality_weight": self.quality_weight,
            "temporal_novelty_weight": self.temporal_novelty_weight,
            "segment_novelty_weight": self.segment_novelty_weight,
            "minimum_temporal_separation_periods": (
                self.minimum_temporal_separation_periods
            ),
            "ranked_candidate_count": len(self.ranked_candidates),
            "ranking_sha256": list(self.ranking_sha256),
            "ranked_candidates": [
                entry.to_dict() for entry in self.ranked_candidates
            ],
            "selected_count": self.selected_count,
            "selected_candidate_indices": list(self.selected_candidate_indices),
            "selected_candidate_sha256": list(self.selected_candidate_sha256),
            "selected_ranking_sha256": list(self.selected_ranking_sha256),
            "representative_segment_indices": list(
                self.representative_segment_indices
            ),
            "decision_reason": self.decision_reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _candidate_center(candidate: CycleCandidate) -> float:
    return float((candidate.start_sample + candidate.end_sample) / 2.0)


def _temporal_novelty(
    candidate: CycleCandidate,
    ranked: list[CycleCandidate],
    sample_count: int,
) -> float:
    if not ranked:
        return 1.0
    center = _candidate_center(candidate)
    distance = min(abs(center - _candidate_center(existing)) for existing in ranked)
    return _clamp_ratio(distance / max(1.0, float(sample_count)))


def _representative_score(
    candidate: CycleCandidate,
    ranked: list[CycleCandidate],
    represented_segments: set[int],
    *,
    sample_count: int,
    quality_weight: float,
    temporal_novelty_weight: float,
    segment_novelty_weight: float,
) -> tuple[float, float, float]:
    temporal = _temporal_novelty(candidate, ranked, sample_count)
    segment = 1.0 if candidate.segment_index not in represented_segments else 0.0
    score = _clamp_ratio(
        quality_weight * candidate.composite_score
        + temporal_novelty_weight * temporal
        + segment_novelty_weight * segment
    )
    return temporal, segment, score


def _rank_candidates(
    candidates: tuple[CycleCandidate, ...],
    *,
    forced_candidate_index: int | None,
    sample_count: int,
    quality_weight: float,
    temporal_novelty_weight: float,
    segment_novelty_weight: float,
) -> list[tuple[CycleCandidate, float, float, float, bool]]:
    remaining = list(candidates)
    ranked_candidates: list[CycleCandidate] = []
    represented_segments: set[int] = set()
    result: list[tuple[CycleCandidate, float, float, float, bool]] = []

    while remaining:
        if not ranked_candidates and forced_candidate_index is not None:
            chosen = next(
                candidate
                for candidate in remaining
                if candidate.index == forced_candidate_index
            )
            temporal, segment, score = _representative_score(
                chosen,
                ranked_candidates,
                represented_segments,
                sample_count=sample_count,
                quality_weight=quality_weight,
                temporal_novelty_weight=temporal_novelty_weight,
                segment_novelty_weight=segment_novelty_weight,
            )
            forced = True
        else:
            evaluated = []
            for candidate in remaining:
                temporal, segment, score = _representative_score(
                    candidate,
                    ranked_candidates,
                    represented_segments,
                    sample_count=sample_count,
                    quality_weight=quality_weight,
                    temporal_novelty_weight=temporal_novelty_weight,
                    segment_novelty_weight=segment_novelty_weight,
                )
                evaluated.append((candidate, temporal, segment, score))
            chosen, temporal, segment, score = max(
                evaluated,
                key=lambda item: (
                    item[3],
                    item[0].composite_score,
                    item[0].seam_score,
                    item[0].spectral_consistency_score,
                    -item[0].period_error_ratio,
                    -item[0].index,
                ),
            )
            forced = False
        remaining.remove(chosen)
        ranked_candidates.append(chosen)
        represented_segments.add(chosen.segment_index)
        result.append((chosen, temporal, segment, score, forced))
    return result


def select_representative_cycles(
    cycle_discovery_analysis: CycleDiscoveryAnalysis,
    *,
    policy: CycleSelectionPolicy | str = CycleSelectionPolicy.AUTO,
    top_n: int = 16,
    forced_candidate_index: int | None = None,
    allow_rejected_forced_candidate: bool = False,
    quality_weight: float = 0.70,
    temporal_novelty_weight: float = 0.20,
    segment_novelty_weight: float = 0.10,
    minimum_temporal_separation_periods: float = 1.0,
    tool_version: str = __version__,
) -> SelectedCycleSet:
    """Rank V6-C candidates and select a deterministic representative top-N set."""

    selected_policy = CycleSelectionPolicy(policy)
    if not 1 <= int(top_n) <= 61:
        raise ValueError("top_n must be between 1 and 61")
    top_n = int(top_n)
    weights = (
        _require_ratio(quality_weight, name="quality_weight"),
        _require_ratio(
            temporal_novelty_weight,
            name="temporal_novelty_weight",
        ),
        _require_ratio(segment_novelty_weight, name="segment_novelty_weight"),
    )
    if not math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("selection weights must sum to one")
    separation_periods = _require_non_negative(
        minimum_temporal_separation_periods,
        name="minimum_temporal_separation_periods",
    )
    candidates = tuple(cycle_discovery_analysis.candidates)
    candidate_by_index = {candidate.index: candidate for candidate in candidates}

    if selected_policy is CycleSelectionPolicy.AUTO:
        if forced_candidate_index is not None:
            raise ValueError("forced_candidate_index is only valid with force policy")
        eligible = tuple(
            candidate
            for candidate in candidates
            if candidate.status is CycleCandidateStatus.ACCEPTED
        )
    else:
        if forced_candidate_index is None:
            raise ValueError("force policy requires forced_candidate_index")
        if forced_candidate_index not in candidate_by_index:
            raise ValueError("forced_candidate_index is outside the candidate range")
        forced = candidate_by_index[forced_candidate_index]
        if (
            forced.status is CycleCandidateStatus.REJECTED
            and not allow_rejected_forced_candidate
        ):
            raise ValueError(
                "forced rejected candidate requires allow_rejected_forced_candidate"
            )
        eligible_list = [
            candidate
            for candidate in candidates
            if candidate.status is CycleCandidateStatus.ACCEPTED
        ]
        if forced not in eligible_list:
            eligible_list.append(forced)
        eligible = tuple(eligible_list)

    if not candidates:
        decision = (
            CycleSelectionDecision.PITCH_UNAVAILABLE
            if cycle_discovery_analysis.source_period_samples is None
            else CycleSelectionDecision.NO_CANDIDATES
        )
        reason = (
            "No source-domain cycle candidates are available because working pitch is unavailable."
            if decision is CycleSelectionDecision.PITCH_UNAVAILABLE
            else "V6-C produced no source-domain cycle candidates to rank."
        )
        ranking_data: list[
            tuple[CycleCandidate, float, float, float, bool]
        ] = []
    elif not eligible:
        decision = CycleSelectionDecision.NO_ACCEPTED_CANDIDATES
        reason = (
            "V6-C produced cycle candidates, but none satisfy every quality gate."
        )
        ranking_data = []
    else:
        decision = CycleSelectionDecision.SELECTED
        ranking_data = _rank_candidates(
            eligible,
            forced_candidate_index=(
                forced_candidate_index
                if selected_policy is CycleSelectionPolicy.FORCE
                else None
            ),
            sample_count=cycle_discovery_analysis.sample_count,
            quality_weight=weights[0],
            temporal_novelty_weight=weights[1],
            segment_novelty_weight=weights[2],
        )
        reason = ""

    selected_candidate_indexes: list[int] = []
    selected_centers: list[float] = []
    minimum_distance = (
        0.0
        if cycle_discovery_analysis.source_period_samples is None
        else separation_periods
        * float(cycle_discovery_analysis.source_period_samples)
    )
    selection_flags: dict[int, bool] = {}
    selection_reasons: dict[int, str] = {}
    for candidate, _, _, _, forced in ranking_data:
        if forced:
            selected = True
            candidate_reason = (
                "Selected first by the explicit forced-cycle override."
            )
        elif len(selected_candidate_indexes) >= top_n:
            selected = False
            candidate_reason = "Not selected because the configured top-N limit is full."
        else:
            center = _candidate_center(candidate)
            separated = all(
                abs(center - existing_center) + 1.0e-12 >= minimum_distance
                for existing_center in selected_centers
            )
            selected = separated
            candidate_reason = (
                "Selected as a deterministic representative cycle."
                if selected
                else "Not selected because it is inside the configured temporal-separation radius."
            )
        selection_flags[candidate.index] = selected
        selection_reasons[candidate.index] = candidate_reason
        if selected:
            selected_candidate_indexes.append(candidate.index)
            selected_centers.append(_candidate_center(candidate))

    ranked_entries = tuple(
        RankedCycleCandidate(
            rank=rank,
            candidate_index=candidate.index,
            candidate_sha256=candidate.candidate_sha256,
            segment_index=candidate.segment_index,
            local_index=candidate.local_index,
            start_sample=candidate.start_sample,
            end_sample=candidate.end_sample,
            quality_score=candidate.composite_score,
            temporal_novelty_score=temporal,
            segment_novelty_score=segment,
            representative_score=score,
            forced=forced,
            selected=selection_flags[candidate.index],
            selection_reason=selection_reasons[candidate.index],
        )
        for rank, (candidate, temporal, segment, score, forced) in enumerate(
            ranking_data,
            start=1,
        )
    )
    selected_entries = tuple(entry for entry in ranked_entries if entry.selected)

    if decision is CycleSelectionDecision.SELECTED:
        selected_count = len(selected_entries)
        forced_text = (
            " The forced candidate is authoritative."
            if selected_policy is CycleSelectionPolicy.FORCE
            else ""
        )
        reason = (
            f"Ranked {len(ranked_entries)} eligible cycle candidates and selected "
            f"{selected_count} representative cycles within the configured top-N and "
            f"temporal-separation constraints.{forced_text}"
        )

    return SelectedCycleSet(
        schema_version=1,
        tool_version=tool_version,
        sample_rate=cycle_discovery_analysis.sample_rate,
        sample_count=cycle_discovery_analysis.sample_count,
        sample_sha256=cycle_discovery_analysis.sample_sha256,
        cycle_discovery_analysis_sha256=(
            cycle_discovery_analysis.analysis_sha256
        ),
        source_period_samples=cycle_discovery_analysis.source_period_samples,
        policy=selected_policy,
        decision=decision,
        top_n=top_n,
        forced_candidate_index=forced_candidate_index,
        allow_rejected_forced_candidate=bool(
            allow_rejected_forced_candidate
        ),
        quality_weight=weights[0],
        temporal_novelty_weight=weights[1],
        segment_novelty_weight=weights[2],
        minimum_temporal_separation_periods=separation_periods,
        ranked_candidates=ranked_entries,
        selected_candidate_indices=tuple(
            entry.candidate_index for entry in selected_entries
        ),
        selected_candidate_sha256=tuple(
            entry.candidate_sha256 for entry in selected_entries
        ),
        selected_ranking_sha256=tuple(
            entry.ranking_sha256 for entry in selected_entries
        ),
        representative_segment_indices=tuple(
            sorted({entry.segment_index for entry in selected_entries})
        ),
        decision_reason=reason,
    )


def analyze_audio_source_cycle_selection(
    source: Any,
    *,
    working_pitch_policy: WorkingPitchPolicy | str = WorkingPitchPolicy.AUTO,
    locked_frequency_hz: float | None = None,
    attack_policy: AttackPolicy | str = AttackPolicy.AUTO,
    selection_policy: CycleSelectionPolicy | str = CycleSelectionPolicy.AUTO,
    top_n: int = 16,
    forced_candidate_index: int | None = None,
    allow_rejected_forced_candidate: bool = False,
    cycle_discovery_kwargs: dict[str, float | int] | None = None,
    **selection_kwargs: float,
) -> SelectedCycleSet:
    """Run the canonical V6-A through V6-D chain for one source."""

    cycles = analyze_audio_source_cycles(
        source,
        working_pitch_policy=working_pitch_policy,
        locked_frequency_hz=locked_frequency_hz,
        attack_policy=attack_policy,
        **dict(cycle_discovery_kwargs or {}),
    )
    return select_representative_cycles(
        cycles,
        policy=selection_policy,
        top_n=top_n,
        forced_candidate_index=forced_candidate_index,
        allow_rejected_forced_candidate=(
            allow_rejected_forced_candidate
        ),
        **selection_kwargs,
    )
