from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .deduplication import CodeV8BAnalysis
from .models import (
    ConstraintStrength,
    USER_POSITION_COUNT,
    WavetableBuildRequest,
    WavetableContractError,
)
from .ordering import (
    ConstraintOutcome,
    ConstraintOutcomeStatus,
    OrderingStatus,
    PlacementConstraintKind,
    WAVETABLE_ORDERING_SCHEMA_VERSION,
    WavetableOrdering,
)
from .selection import CodeV8CAnalysis
from .usefulness import CandidateStructureClass

WAVETABLE_PLACEMENT_SCHEMA_VERSION = 1
_PLACEMENT_PRECISION = 12


def _q(value: float) -> float:
    return round(float(value), _PLACEMENT_PRECISION)


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


def _entries(
    values: Sequence[str], *, name: str, allow_empty: bool = True
) -> tuple[str, ...]:
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


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


class PlacementStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


class PlacementBias(str, Enum):
    BALANCED = "balanced"
    EARLY = "early"
    LATE = "late"
    CENTER = "center"
    EDGE_EXPANDED = "edge_expanded"


@dataclass(frozen=True, slots=True)
class PlacementPolicy:
    schema_version: int = WAVETABLE_PLACEMENT_SCHEMA_VERSION
    bias: PlacementBias = PlacementBias.BALANCED
    ordering_weight: float = 0.40
    spacing_weight: float = 0.25
    lock_weight: float = 0.20
    chronology_weight: float = 0.15
    honor_preference_locks: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported placement-policy schema version")
        if not isinstance(self.bias, PlacementBias):
            raise WavetableContractError("bias must be PlacementBias")
        weights = (
            "ordering_weight",
            "spacing_weight",
            "lock_weight",
            "chronology_weight",
        )
        for name in weights:
            _ratio(getattr(self, name), name=name)
        if abs(sum(getattr(self, name) for name in weights) - 1.0) > 1e-9:
            raise WavetableContractError("placement objective weights must sum to one")
        if not isinstance(self.honor_preference_locks, bool):
            raise WavetableContractError("honor_preference_locks must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "bias": self.bias.value,
            "ordering_weight": self.ordering_weight,
            "spacing_weight": self.spacing_weight,
            "lock_weight": self.lock_weight,
            "chronology_weight": self.chronology_weight,
            "honor_preference_locks": self.honor_preference_locks,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_PLACEMENT_POLICY = PlacementPolicy()


@dataclass(frozen=True, slots=True)
class PositionAssignment:
    schema_version: int
    candidate_id: str
    position: int
    order_index: int
    source_order_index: int
    essential: bool
    forced: bool
    required_locked: bool
    preference_locked: bool
    structure_class: CandidateStructureClass
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported position-assignment schema version")
        _normalized(self.candidate_id, name="candidate_id")
        if (
            isinstance(self.position, bool)
            or not isinstance(self.position, int)
            or not 0 <= self.position < USER_POSITION_COUNT
        ):
            raise WavetableContractError("position must be an integer from 0 to 60")
        for name in ("order_index", "source_order_index"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise WavetableContractError(f"{name} must be non-negative")
        for name in (
            "essential",
            "forced",
            "required_locked",
            "preference_locked",
        ):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        if self.required_locked and self.preference_locked:
            raise WavetableContractError(
                "assignment cannot be both required- and preference-locked"
            )
        if not isinstance(self.structure_class, CandidateStructureClass):
            raise WavetableContractError("structure_class must be CandidateStructureClass")
        evidence = _entries(self.evidence, name="evidence", allow_empty=False)
        object.__setattr__(self, "evidence", evidence)
        _normalized(self.reason, name="reason")

    @property
    def display_position(self) -> int:
        return self.position + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "position": self.position,
            "display_position": self.display_position,
            "order_index": self.order_index,
            "order_rank": self.order_index + 1,
            "source_order_index": self.source_order_index,
            "source_order_rank": self.source_order_index + 1,
            "essential": self.essential,
            "forced": self.forced,
            "required_locked": self.required_locked,
            "preference_locked": self.preference_locked,
            "structure_class": self.structure_class.value,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class PlacementScore:
    schema_version: int
    objective_score: float
    ordering_score: float
    spacing_evenness_score: float
    position_lock_score: float
    chronology_score: float
    mean_gap: float
    maximum_gap: int

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported placement-score schema version")
        for name in (
            "objective_score",
            "ordering_score",
            "spacing_evenness_score",
            "position_lock_score",
            "chronology_score",
        ):
            _ratio(getattr(self, name), name=name)
        if not math.isfinite(float(self.mean_gap)) or self.mean_gap < 0.0:
            raise WavetableContractError("mean_gap must be finite and non-negative")
        if isinstance(self.maximum_gap, bool) or not isinstance(self.maximum_gap, int):
            raise WavetableContractError("maximum_gap must be an integer")
        if self.maximum_gap < 0:
            raise WavetableContractError("maximum_gap must be non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "objective_score": self.objective_score,
            "ordering_score": self.ordering_score,
            "spacing_evenness_score": self.spacing_evenness_score,
            "position_lock_score": self.position_lock_score,
            "chronology_score": self.chronology_score,
            "mean_gap": self.mean_gap,
            "maximum_gap": self.maximum_gap,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class WavetablePlacement:
    schema_version: int
    status: PlacementStatus
    request_sha256: str
    v8b_analysis_sha256: str
    v8c_analysis_sha256: str
    ordering_sha256: str
    policy: PlacementPolicy
    assignments: tuple[PositionAssignment, ...]
    occupied_positions: tuple[int, ...]
    open_positions: tuple[int, ...]
    constraint_outcomes: tuple[ConstraintOutcome, ...]
    score: PlacementScore | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_PLACEMENT_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported wavetable-placement schema version")
        if not isinstance(self.status, PlacementStatus):
            raise WavetableContractError("status must be PlacementStatus")
        for name in (
            "request_sha256",
            "v8b_analysis_sha256",
            "v8c_analysis_sha256",
            "ordering_sha256",
        ):
            _sha256(getattr(self, name), name=name)
        if not isinstance(self.policy, PlacementPolicy):
            raise WavetableContractError("policy must be PlacementPolicy")
        assignments = tuple(self.assignments)
        outcomes = tuple(self.constraint_outcomes)
        occupied = tuple(self.occupied_positions)
        open_positions = tuple(self.open_positions)
        warnings = _entries(self.warnings, name="warnings")
        blockers = _entries(self.blockers, name="blockers")
        object.__setattr__(self, "assignments", assignments)
        object.__setattr__(self, "constraint_outcomes", outcomes)
        object.__setattr__(self, "occupied_positions", occupied)
        object.__setattr__(self, "open_positions", open_positions)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "blockers", blockers)
        if any(not isinstance(item, PositionAssignment) for item in assignments):
            raise WavetableContractError("assignments must contain PositionAssignment")
        if any(not isinstance(item, ConstraintOutcome) for item in outcomes):
            raise WavetableContractError("constraint_outcomes contain invalid values")
        if occupied != tuple(sorted(occupied)) or len(set(occupied)) != len(occupied):
            raise WavetableContractError("occupied_positions must be unique and sorted")
        if open_positions != tuple(sorted(open_positions)) or len(set(open_positions)) != len(
            open_positions
        ):
            raise WavetableContractError("open_positions must be unique and sorted")
        if set(occupied) & set(open_positions):
            raise WavetableContractError("occupied and open positions must be disjoint")
        if set(occupied) | set(open_positions) != set(range(USER_POSITION_COUNT)):
            raise WavetableContractError("occupied and open positions must partition 0..60")
        assignment_positions = tuple(sorted(item.position for item in assignments))
        if assignment_positions != occupied:
            raise WavetableContractError("assignment positions disagree with occupied_positions")
        assignment_ids = tuple(item.candidate_id for item in assignments)
        if len(set(assignment_ids)) != len(assignment_ids):
            raise WavetableContractError("candidate assignments must be unique")
        if tuple(item.order_index for item in sorted(assignments, key=lambda item: item.order_index)) != tuple(
            range(len(assignments))
        ):
            raise WavetableContractError("assignments require canonical order indices")
        _normalized(self.reason, name="reason")
        if self.status is PlacementStatus.COMPLETE:
            if blockers:
                raise WavetableContractError("complete placement cannot contain blockers")
            if not assignments or self.score is None:
                raise WavetableContractError("complete placement requires assignments and score")
            by_order = tuple(sorted(assignments, key=lambda item: item.order_index))
            if tuple(item.position for item in by_order) != tuple(
                sorted(item.position for item in by_order)
            ):
                raise WavetableContractError("positions must increase with final order")
            if any(
                item.strength is ConstraintStrength.REQUIRED
                and item.status is not ConstraintOutcomeStatus.SATISFIED
                for item in outcomes
            ):
                raise WavetableContractError("complete placement violates required constraints")
        else:
            if not blockers:
                raise WavetableContractError("rejected placement requires blockers")
            if assignments or occupied or self.score is not None:
                raise WavetableContractError("rejected placement cannot expose partial assignment")
            if open_positions != tuple(range(USER_POSITION_COUNT)):
                raise WavetableContractError("rejected placement must leave all positions open")

    @property
    def assigned_candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            item.candidate_id for item in sorted(self.assignments, key=lambda item: item.order_index)
        )

    @property
    def assigned_candidate_count(self) -> int:
        return len(self.assignments)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "v8b_analysis_sha256": self.v8b_analysis_sha256,
            "v8c_analysis_sha256": self.v8c_analysis_sha256,
            "ordering_sha256": self.ordering_sha256,
            "policy": self.policy.to_dict(),
            "assigned_candidate_count": self.assigned_candidate_count,
            "assigned_candidate_ids": list(self.assigned_candidate_ids),
            "assignments": [item.to_dict() for item in self.assignments],
            "occupied_positions": list(self.occupied_positions),
            "display_occupied_positions": [item + 1 for item in self.occupied_positions],
            "open_positions": list(self.open_positions),
            "display_open_positions": [item + 1 for item in self.open_positions],
            "constraint_outcomes": [item.to_dict() for item in self.constraint_outcomes],
            "score": None if self.score is None else self.score.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "assigns_selected_keyframes": True,
                "fills_all_61_positions": self.assigned_candidate_count == USER_POSITION_COUNT,
                "interpolates_transitions": False,
                "materializes_wctd": False,
                "generates_sysex": False,
                "opens_midi_port": False,
                "transmits_midi": False,
            },
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ) + "\n"


def _anchor_feasible(
    order_count: int, anchors: Mapping[int, int]
) -> bool:
    items = sorted(anchors.items())
    if len(set(anchors.values())) != len(anchors):
        return False
    if any(
        left_index >= right_index or left_position >= right_position
        for (left_index, left_position), (right_index, right_position) in zip(
            items, items[1:]
        )
    ):
        return False
    if items:
        first_index, first_position = items[0]
        if first_index > first_position:
            return False
        for (left_index, left_position), (right_index, right_position) in zip(
            items, items[1:]
        ):
            if right_index - left_index > right_position - left_position:
                return False
        last_index, last_position = items[-1]
        if order_count - 1 - last_index > USER_POSITION_COUNT - 1 - last_position:
            return False
    return all(0 <= position < USER_POSITION_COUNT for position in anchors.values())


def _segment_positions(
    available: Sequence[int], count: int, bias: PlacementBias
) -> tuple[int, ...]:
    positions = tuple(available)
    if count == 0:
        return ()
    if count > len(positions):
        raise WavetableContractError("segment capacity is smaller than candidate count")
    if count == len(positions):
        return positions
    if bias is PlacementBias.EARLY:
        return positions[:count]
    if bias is PlacementBias.LATE:
        return positions[-count:]
    if bias is PlacementBias.CENTER:
        start = (len(positions) - count) // 2
        return positions[start : start + count]
    if count == 1:
        return (positions[len(positions) // 2],)
    if bias is PlacementBias.EDGE_EXPANDED:
        indexes = [
            round((index / (count - 1)) ** 1.35 * (len(positions) - 1))
            for index in range(count)
        ]
    else:
        indexes = [
            round(index * (len(positions) - 1) / (count - 1))
            for index in range(count)
        ]
    # Rounding is collision-free when available count >= count in most cases, but
    # canonicalize defensively by moving each index to the nearest unused slot.
    used: set[int] = set()
    result: list[int] = []
    for desired in indexes:
        candidates = sorted(
            (index for index in range(len(positions)) if index not in used),
            key=lambda index: (abs(index - desired), index),
        )
        chosen = candidates[0]
        used.add(chosen)
        result.append(positions[chosen])
    return tuple(sorted(result))


def _assign_positions(
    order: Sequence[str], anchors: Mapping[int, int], bias: PlacementBias
) -> tuple[int, ...]:
    if not _anchor_feasible(len(order), anchors):
        raise WavetableContractError("anchor set is not position-feasible")
    result: list[int | None] = [None] * len(order)
    for index, position in anchors.items():
        result[index] = position
    sentinels = [(-1, -1), *sorted(anchors.items()), (len(order), USER_POSITION_COUNT)]
    for (left_index, left_position), (right_index, right_position) in zip(
        sentinels, sentinels[1:]
    ):
        candidate_indices = tuple(range(left_index + 1, right_index))
        available = tuple(range(left_position + 1, right_position))
        selected_positions = _segment_positions(available, len(candidate_indices), bias)
        for index, position in zip(candidate_indices, selected_positions):
            result[index] = position
    if any(item is None for item in result):
        raise WavetableContractError("placement left an unassigned candidate")
    return tuple(int(item) for item in result)


def _constraint_outcomes(
    request: WavetableBuildRequest,
    order: Sequence[str],
    positions: Mapping[str, int] | None,
    accepted_preference_locks: frozenset[str],
    rejected: bool,
    honor_preference_locks: bool,
) -> tuple[ConstraintOutcome, ...]:
    selected = frozenset(order)
    outcomes: list[ConstraintOutcome] = []
    for index, lock in enumerate(request.position_locks):
        applicable = lock.candidate_id in selected
        if not applicable:
            status = (
                ConstraintOutcomeStatus.BLOCKED
                if lock.strength is ConstraintStrength.REQUIRED
                else ConstraintOutcomeStatus.NOT_APPLICABLE
            )
            reason = "Position lock references a candidate outside V8-C selection."
        elif (
            lock.strength is ConstraintStrength.PREFERENCE
            and not honor_preference_locks
        ):
            status = ConstraintOutcomeStatus.NOT_APPLICABLE
            reason = "Preference position locks are disabled by placement policy."
        elif rejected or positions is None:
            status = ConstraintOutcomeStatus.BLOCKED
            reason = "Position lock could not be evaluated because placement was rejected."
        elif positions[lock.candidate_id] == lock.position:
            status = ConstraintOutcomeStatus.SATISFIED
            reason = "Candidate occupies the requested locked position."
        else:
            status = (
                ConstraintOutcomeStatus.BLOCKED
                if lock.strength is ConstraintStrength.REQUIRED
                else ConstraintOutcomeStatus.VIOLATED
            )
            reason = "Candidate could not occupy the preferred locked position."
        evidence = [lock.reason]
        if lock.candidate_id in accepted_preference_locks:
            evidence.append("preference lock was accepted as a placement anchor")
        outcomes.append(
            ConstraintOutcome(
                schema_version=WAVETABLE_ORDERING_SCHEMA_VERSION,
                constraint_id=f"position-lock-{index:03d}",
                kind=PlacementConstraintKind.POSITION_LOCK,
                strength=lock.strength,
                candidate_ids=(lock.candidate_id,),
                target_position=lock.position,
                status=status,
                evidence=tuple(evidence),
                reason=reason,
            )
        )
    for index, constraint in enumerate(request.chronology_constraints):
        applicable = (
            constraint.before_candidate_id in selected
            and constraint.after_candidate_id in selected
        )
        if not applicable:
            status = (
                ConstraintOutcomeStatus.BLOCKED
                if constraint.strength is ConstraintStrength.REQUIRED
                else ConstraintOutcomeStatus.NOT_APPLICABLE
            )
            reason = "Chronology references a candidate outside V8-C selection."
        elif rejected or positions is None:
            status = ConstraintOutcomeStatus.BLOCKED
            reason = "Chronology could not be evaluated because placement was rejected."
        elif positions[constraint.before_candidate_id] < positions[constraint.after_candidate_id]:
            status = ConstraintOutcomeStatus.SATISFIED
            reason = "Candidate positions satisfy the chronology constraint."
        else:
            status = (
                ConstraintOutcomeStatus.BLOCKED
                if constraint.strength is ConstraintStrength.REQUIRED
                else ConstraintOutcomeStatus.VIOLATED
            )
            reason = "Candidate positions violate the chronology preference."
        outcomes.append(
            ConstraintOutcome(
                schema_version=WAVETABLE_ORDERING_SCHEMA_VERSION,
                constraint_id=f"chronology-{index:03d}",
                kind=PlacementConstraintKind.CHRONOLOGY,
                strength=constraint.strength,
                candidate_ids=(
                    constraint.before_candidate_id,
                    constraint.after_candidate_id,
                ),
                target_position=None,
                status=status,
                evidence=(constraint.reason,),
                reason=reason,
            )
        )
    return tuple(outcomes)


def _constraint_score(
    outcomes: Sequence[ConstraintOutcome], kind: PlacementConstraintKind
) -> float:
    applicable = tuple(
        item
        for item in outcomes
        if item.kind is kind
        and item.status is not ConstraintOutcomeStatus.NOT_APPLICABLE
    )
    if not applicable:
        return 1.0
    values = []
    for item in applicable:
        if item.status is ConstraintOutcomeStatus.SATISFIED:
            values.append(1.0)
        elif item.strength is ConstraintStrength.REQUIRED:
            values.append(0.0)
        else:
            values.append(0.25)
    return sum(values) / len(values)


def _spacing_score(positions: Sequence[int]) -> tuple[float, float, int]:
    ordered = tuple(sorted(positions))
    if len(ordered) <= 1:
        return 1.0, 0.0, 0
    gaps = tuple(right - left for left, right in zip(ordered, ordered[1:]))
    mean_gap = sum(gaps) / len(gaps)
    ideal = (USER_POSITION_COUNT - 1) / (len(ordered) - 1)
    deviation = sum(abs(gap - ideal) for gap in gaps) / len(gaps)
    score = max(0.0, 1.0 - deviation / max(1.0, ideal))
    return _q(score), _q(mean_gap), max(gaps)


def place_wavetable_ordering(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
    ordering: WavetableOrdering,
    policy: PlacementPolicy = DEFAULT_PLACEMENT_POLICY,
) -> WavetablePlacement:
    """Assign one complete V8-D ordering to sparse positions 0..60."""

    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(v8b_analysis, CodeV8BAnalysis):
        raise WavetableContractError("v8b_analysis must be CodeV8BAnalysis")
    if not isinstance(v8c_analysis, CodeV8CAnalysis):
        raise WavetableContractError("v8c_analysis must be CodeV8CAnalysis")
    if not isinstance(ordering, WavetableOrdering):
        raise WavetableContractError("ordering must be WavetableOrdering")
    if not isinstance(policy, PlacementPolicy):
        raise WavetableContractError("policy must be PlacementPolicy")
    if ordering.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("ordering does not link to the request")
    if ordering.v8b_analysis_sha256 != v8b_analysis.analysis_sha256:
        raise WavetableContractError("ordering does not link to V8-B")
    if ordering.v8c_analysis_sha256 != v8c_analysis.analysis_sha256:
        raise WavetableContractError("ordering does not link to V8-C")

    warnings = list(ordering.warnings)
    blockers = list(ordering.blockers)
    order = ordering.ordered_candidate_ids
    accepted_preference_locks: set[str] = set()
    positions_by_id: dict[str, int] | None = None
    assignments: tuple[PositionAssignment, ...] = ()
    score: PlacementScore | None = None
    occupied: tuple[int, ...] = ()
    if ordering.status is not OrderingStatus.COMPLETE:
        blockers.append("V8-D ordering is rejected; placement cannot expose partial assignments")
    elif len(order) > USER_POSITION_COUNT:
        blockers.append("selected keyframes exceed 61 editable positions")
    else:
        rank = {candidate_id: index for index, candidate_id in enumerate(order)}
        anchors: dict[int, int] = {}
        for lock in request.position_locks:
            if lock.strength is not ConstraintStrength.REQUIRED:
                continue
            if lock.candidate_id not in rank:
                blockers.append(
                    f"required position lock candidate {lock.candidate_id} is absent from ordering"
                )
                continue
            anchors[rank[lock.candidate_id]] = lock.position
        if not blockers and not _anchor_feasible(len(order), anchors):
            blockers.append(
                "required position locks leave insufficient capacity for the final order"
            )
        if not blockers and policy.honor_preference_locks:
            preferences = sorted(
                (
                    lock.position,
                    lock.candidate_id,
                    index,
                )
                for index, lock in enumerate(request.position_locks)
                if lock.strength is ConstraintStrength.PREFERENCE
                and lock.candidate_id in rank
            )
            for position, candidate_id, _ in preferences:
                proposed = dict(anchors)
                proposed[rank[candidate_id]] = position
                if _anchor_feasible(len(order), proposed):
                    anchors = proposed
                    accepted_preference_locks.add(candidate_id)
                else:
                    warnings.append(
                        f"preference position lock for {candidate_id} was not feasible"
                    )
        if not blockers:
            try:
                positions = _assign_positions(order, anchors, policy.bias)
                positions_by_id = dict(zip(order, positions))
            except WavetableContractError as exc:
                blockers.append(str(exc))

    outcomes = _constraint_outcomes(
        request,
        order,
        positions_by_id,
        frozenset(accepted_preference_locks),
        bool(blockers),
        policy.honor_preference_locks,
    )
    if not blockers and any(
        item.strength is ConstraintStrength.REQUIRED
        and item.status is not ConstraintOutcomeStatus.SATISFIED
        for item in outcomes
    ):
        blockers.append("required placement constraint is not satisfied")
        positions_by_id = None
        outcomes = _constraint_outcomes(
            request,
            order,
            None,
            frozenset(accepted_preference_locks),
            True,
            policy.honor_preference_locks,
        )

    if not blockers and positions_by_id is not None:
        structure_by_id = {
            item.candidate_id: item.structure_class
            for item in v8b_analysis.structure.candidates
        }
        decision_by_id = {
            item.candidate_id: item for item in v8c_analysis.selection.decisions
        }
        required_locked_ids = {
            lock.candidate_id
            for lock in request.position_locks
            if lock.strength is ConstraintStrength.REQUIRED
        }
        assignments = tuple(
            PositionAssignment(
                schema_version=WAVETABLE_PLACEMENT_SCHEMA_VERSION,
                candidate_id=candidate_id,
                position=positions_by_id[candidate_id],
                order_index=index,
                source_order_index=decision_by_id[candidate_id].source_order_index,
                essential=decision_by_id[candidate_id].essential,
                forced=decision_by_id[candidate_id].forced,
                required_locked=candidate_id in required_locked_ids,
                preference_locked=candidate_id in accepted_preference_locks,
                structure_class=structure_by_id[candidate_id],
                evidence=(
                    f"ordering {ordering.analysis_sha256}",
                    f"V8-C decision {decision_by_id[candidate_id].analysis_sha256}",
                ),
                reason="Selected keyframe assigned to one editable XT user position.",
            )
            for index, candidate_id in enumerate(order)
        )
        occupied = tuple(sorted(item.position for item in assignments))
        spacing, mean_gap, maximum_gap = _spacing_score(occupied)
        lock_score = _constraint_score(outcomes, PlacementConstraintKind.POSITION_LOCK)
        chronology_score = _constraint_score(outcomes, PlacementConstraintKind.CHRONOLOGY)
        ordering_score = ordering.score.objective_score if ordering.score else 0.0
        objective = _q(
            policy.ordering_weight * ordering_score
            + policy.spacing_weight * spacing
            + policy.lock_weight * lock_score
            + policy.chronology_weight * chronology_score
        )
        score = PlacementScore(
            schema_version=WAVETABLE_PLACEMENT_SCHEMA_VERSION,
            objective_score=objective,
            ordering_score=ordering_score,
            spacing_evenness_score=spacing,
            position_lock_score=_q(lock_score),
            chronology_score=_q(chronology_score),
            mean_gap=mean_gap,
            maximum_gap=maximum_gap,
        )

    status = PlacementStatus.REJECTED if blockers else PlacementStatus.COMPLETE
    open_positions = (
        tuple(range(USER_POSITION_COUNT))
        if blockers
        else tuple(item for item in range(USER_POSITION_COUNT) if item not in set(occupied))
    )
    reason = (
        "CODE V8-D rejected placement before exposing partial position assignments."
        if blockers
        else "CODE V8-D assigned selected keyframes to editable positions while leaving transition positions open for V8-E."
    )
    return WavetablePlacement(
        schema_version=WAVETABLE_PLACEMENT_SCHEMA_VERSION,
        status=status,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        ordering_sha256=ordering.analysis_sha256,
        policy=policy,
        assignments=assignments,
        occupied_positions=occupied,
        open_positions=open_positions,
        constraint_outcomes=outcomes,
        score=score,
        warnings=tuple(dict.fromkeys(warnings)),
        blockers=tuple(dict.fromkeys(blockers)),
        reason=reason,
    )


__all__ = [
    "DEFAULT_PLACEMENT_POLICY",
    "WAVETABLE_PLACEMENT_SCHEMA_VERSION",
    "PlacementBias",
    "PlacementPolicy",
    "PlacementScore",
    "PlacementStatus",
    "PositionAssignment",
    "WavetablePlacement",
    "place_wavetable_ordering",
]
