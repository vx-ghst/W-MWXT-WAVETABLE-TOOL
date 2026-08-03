from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .metrics import WavePairDistance, WaveShapeMetrics, analyze_wave_shape, compare_wave_shapes
from .models import WavetableBuildRequest, WavetableCandidate, WavetableContractError

WAVETABLE_USEFULNESS_SCHEMA_VERSION = 1
_USEFULNESS_PRECISION = 12


def _q(value: float) -> float:
    return round(float(value), _USEFULNESS_PRECISION)


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _ratio(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked) or not 0.0 <= checked <= 1.0:
        raise WavetableContractError(f"{name} must be finite and between 0 and 1")
    return checked


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


class CandidateStructureClass(str, Enum):
    INELIGIBLE = "ineligible"
    STABLE = "stable"
    TRANSITION = "transition"
    BREAKPOINT = "breakpoint"
    STRUCTURAL = "structural"
    EXTREME = "extreme"


class IntervalClass(str, Enum):
    STABLE = "stable"
    TRANSITION = "transition"
    BREAKPOINT = "breakpoint"


class BreakpointKind(str, Enum):
    WAVEFORM = "waveform"
    SPECTRAL = "spectral"
    LEVEL = "level"
    BRIGHTNESS = "brightness"
    BASS = "bass"
    POLARITY = "polarity"
    COMPOSITE = "composite"


@dataclass(frozen=True, slots=True)
class UsefulnessThresholds:
    schema_version: int = WAVETABLE_USEFULNESS_SCHEMA_VERSION
    stable_distance: float = 0.055
    transition_distance: float = 0.180
    breakpoint_distance: float = 0.320
    structural_score: float = 0.600
    extreme_feature_span: float = 0.180
    extreme_edge_fraction: float = 0.100

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_USEFULNESS_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported usefulness-threshold schema version")
        for name in (
            "stable_distance",
            "transition_distance",
            "breakpoint_distance",
            "structural_score",
            "extreme_feature_span",
            "extreme_edge_fraction",
        ):
            _ratio(getattr(self, name), name=name)
        if not self.stable_distance < self.transition_distance < self.breakpoint_distance:
            raise WavetableContractError(
                "usefulness distances must satisfy stable < transition < breakpoint"
            )
        if self.extreme_edge_fraction > 0.5:
            raise WavetableContractError("extreme_edge_fraction must not exceed 0.5")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "stable_distance": self.stable_distance,
            "transition_distance": self.transition_distance,
            "breakpoint_distance": self.breakpoint_distance,
            "structural_score": self.structural_score,
            "extreme_feature_span": self.extreme_feature_span,
            "extreme_edge_fraction": self.extreme_edge_fraction,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_USEFULNESS_THRESHOLDS = UsefulnessThresholds()


@dataclass(frozen=True, slots=True)
class WavetableIntervalAnalysis:
    schema_version: int
    left_candidate_id: str
    right_candidate_id: str
    source_order_index: int
    distance: WavePairDistance
    interval_class: IntervalClass
    breakpoint_kinds: tuple[BreakpointKind, ...]
    transition_strength: float
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_USEFULNESS_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported interval-analysis schema version")
        _normalized(self.left_candidate_id, name="left_candidate_id")
        _normalized(self.right_candidate_id, name="right_candidate_id")
        if self.left_candidate_id == self.right_candidate_id:
            raise WavetableContractError("interval candidates must be distinct")
        if isinstance(self.source_order_index, bool) or not isinstance(self.source_order_index, int) or self.source_order_index < 0:
            raise WavetableContractError("source_order_index must be non-negative")
        if not isinstance(self.distance, WavePairDistance):
            raise WavetableContractError("distance must be WavePairDistance")
        if not isinstance(self.interval_class, IntervalClass):
            raise WavetableContractError("interval_class must be IntervalClass")
        kinds = tuple(self.breakpoint_kinds)
        object.__setattr__(self, "breakpoint_kinds", kinds)
        if any(not isinstance(item, BreakpointKind) for item in kinds):
            raise WavetableContractError("breakpoint_kinds must contain BreakpointKind values")
        if len(set(kinds)) != len(kinds):
            raise WavetableContractError("breakpoint_kinds must be unique")
        if self.interval_class is IntervalClass.BREAKPOINT and not kinds:
            raise WavetableContractError("breakpoint intervals require breakpoint kinds")
        if self.interval_class is not IntervalClass.BREAKPOINT and kinds:
            raise WavetableContractError("non-breakpoint intervals cannot carry breakpoint kinds")
        _ratio(self.transition_strength, name="transition_strength")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "left_candidate_id": self.left_candidate_id,
            "right_candidate_id": self.right_candidate_id,
            "source_order_index": self.source_order_index,
            "distance": self.distance.to_dict(),
            "interval_class": self.interval_class.value,
            "breakpoint_kinds": [item.value for item in self.breakpoint_kinds],
            "transition_strength": self.transition_strength,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class CandidateUsefulnessAnalysis:
    schema_version: int
    candidate_id: str
    inventory_index: int
    source_order_index: int
    shape_metrics: WaveShapeMetrics
    left_interval_sha256: str | None
    right_interval_sha256: str | None
    neighborhood_novelty: float
    structural_score: float
    effective_usefulness_score: float
    structure_class: CandidateStructureClass
    structural_candidate: bool
    breakpoint_candidate: bool
    transition_candidate: bool
    stable_candidate: bool
    extreme_features: tuple[str, ...]
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_USEFULNESS_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported candidate-usefulness schema version")
        _normalized(self.candidate_id, name="candidate_id")
        for name in ("inventory_index", "source_order_index"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise WavetableContractError(f"{name} must be non-negative")
        if not isinstance(self.shape_metrics, WaveShapeMetrics):
            raise WavetableContractError("shape_metrics must be WaveShapeMetrics")
        for name in ("left_interval_sha256", "right_interval_sha256"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
        for name in (
            "neighborhood_novelty",
            "structural_score",
            "effective_usefulness_score",
        ):
            _ratio(getattr(self, name), name=name)
        if not isinstance(self.structure_class, CandidateStructureClass):
            raise WavetableContractError("structure_class must be CandidateStructureClass")
        for name in (
            "structural_candidate",
            "breakpoint_candidate",
            "transition_candidate",
            "stable_candidate",
        ):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        flags = sum(
            (
                self.breakpoint_candidate,
                self.transition_candidate,
                self.stable_candidate,
            )
        )
        if flags > 1:
            raise WavetableContractError("breakpoint, transition and stable flags are exclusive")
        extremes = _entries(self.extreme_features, name="extreme_features")
        object.__setattr__(self, "extreme_features", extremes)
        evidence = _entries(self.evidence, name="evidence", allow_empty=False)
        object.__setattr__(self, "evidence", evidence)
        _normalized(self.reason, name="reason")
        expected_structural = self.structure_class in {
            CandidateStructureClass.STRUCTURAL,
            CandidateStructureClass.BREAKPOINT,
            CandidateStructureClass.EXTREME,
        }
        if self.structural_candidate != expected_structural:
            raise WavetableContractError("structural_candidate disagrees with structure_class")
        if self.breakpoint_candidate != (self.structure_class is CandidateStructureClass.BREAKPOINT):
            raise WavetableContractError("breakpoint_candidate disagrees with structure_class")
        if self.transition_candidate != (self.structure_class is CandidateStructureClass.TRANSITION):
            raise WavetableContractError("transition_candidate disagrees with structure_class")
        if self.stable_candidate != (self.structure_class is CandidateStructureClass.STABLE):
            raise WavetableContractError("stable_candidate disagrees with structure_class")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "inventory_index": self.inventory_index,
            "source_order_index": self.source_order_index,
            "shape_metrics": self.shape_metrics.to_dict(),
            "left_interval_sha256": self.left_interval_sha256,
            "right_interval_sha256": self.right_interval_sha256,
            "neighborhood_novelty": self.neighborhood_novelty,
            "structural_score": self.structural_score,
            "effective_usefulness_score": self.effective_usefulness_score,
            "structure_class": self.structure_class.value,
            "structural_candidate": self.structural_candidate,
            "breakpoint_candidate": self.breakpoint_candidate,
            "transition_candidate": self.transition_candidate,
            "stable_candidate": self.stable_candidate,
            "extreme_features": list(self.extreme_features),
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class WavetableStructureAnalysis:
    schema_version: int
    request_sha256: str
    candidate_inventory_sha256: str
    thresholds: UsefulnessThresholds
    source_order_candidate_ids: tuple[str, ...]
    candidates: tuple[CandidateUsefulnessAnalysis, ...]
    intervals: tuple[WavetableIntervalAnalysis, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_USEFULNESS_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported structure-analysis schema version")
        for name in ("request_sha256", "candidate_inventory_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
        if not isinstance(self.thresholds, UsefulnessThresholds):
            raise WavetableContractError("thresholds must be UsefulnessThresholds")
        order = _entries(self.source_order_candidate_ids, name="source_order_candidate_ids", allow_empty=False)
        candidates = tuple(self.candidates)
        intervals = tuple(self.intervals)
        warnings = _entries(self.warnings, name="warnings")
        object.__setattr__(self, "source_order_candidate_ids", order)
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "intervals", intervals)
        object.__setattr__(self, "warnings", warnings)
        if any(not isinstance(item, CandidateUsefulnessAnalysis) for item in candidates):
            raise WavetableContractError("candidates must contain CandidateUsefulnessAnalysis")
        if any(not isinstance(item, WavetableIntervalAnalysis) for item in intervals):
            raise WavetableContractError("intervals must contain WavetableIntervalAnalysis")
        if tuple(item.candidate_id for item in candidates) != order:
            raise WavetableContractError("candidate analyses must follow source order")
        if len(intervals) != max(0, len(candidates) - 1):
            raise WavetableContractError("interval count must equal candidate count minus one")
        for index, interval in enumerate(intervals):
            if (
                interval.source_order_index != index
                or interval.left_candidate_id != order[index]
                or interval.right_candidate_id != order[index + 1]
            ):
                raise WavetableContractError("intervals must follow adjacent source order")
        _normalized(self.reason, name="reason")

    @property
    def structural_candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_id for item in self.candidates if item.structural_candidate)

    @property
    def breakpoint_candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_id for item in self.candidates if item.breakpoint_candidate)

    @property
    def transition_candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_id for item in self.candidates if item.transition_candidate)

    @property
    def stable_candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_id for item in self.candidates if item.stable_candidate)

    @property
    def ineligible_candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            item.candidate_id
            for item in self.candidates
            if item.structure_class is CandidateStructureClass.INELIGIBLE
        )

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request_sha256,
            "candidate_inventory_sha256": self.candidate_inventory_sha256,
            "thresholds": self.thresholds.to_dict(),
            "source_order_candidate_ids": list(self.source_order_candidate_ids),
            "candidates": [item.to_dict() for item in self.candidates],
            "intervals": [item.to_dict() for item in self.intervals],
            "structural_candidate_ids": list(self.structural_candidate_ids),
            "breakpoint_candidate_ids": list(self.breakpoint_candidate_ids),
            "transition_candidate_ids": list(self.transition_candidate_ids),
            "stable_candidate_ids": list(self.stable_candidate_ids),
            "ineligible_candidate_ids": list(self.ineligible_candidate_ids),
            "warnings": list(self.warnings),
            "reason": self.reason,
            "boundaries": {
                "selects_keyframes": False,
                "assigns_user_positions": False,
                "orders_final_table": False,
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
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"


def _source_order(request: WavetableBuildRequest) -> tuple[tuple[int, WavetableCandidate], ...]:
    indexed = tuple(enumerate(request.candidates))

    def key(item: tuple[int, WavetableCandidate]) -> tuple[object, ...]:
        inventory_index, candidate = item
        return (
            candidate.source_time_seconds is None,
            0.0 if candidate.source_time_seconds is None else candidate.source_time_seconds,
            candidate.source_index is None,
            0 if candidate.source_index is None else candidate.source_index,
            inventory_index,
            candidate.candidate_id,
        )

    return tuple(sorted(indexed, key=key))


def _breakpoint_kinds(
    left: WavetableCandidate,
    right: WavetableCandidate,
    distance: WavePairDistance,
    left_shape: WaveShapeMetrics,
    right_shape: WaveShapeMetrics,
) -> tuple[BreakpointKind, ...]:
    result: list[BreakpointKind] = []
    if distance.waveform_distance >= 0.32:
        result.append(BreakpointKind.WAVEFORM)
    if distance.spectral_distance >= 0.24:
        result.append(BreakpointKind.SPECTRAL)
    if abs(left_shape.rms - right_shape.rms) >= 0.20:
        result.append(BreakpointKind.LEVEL)
    if abs(left.metrics.brightness - right.metrics.brightness) >= 0.28:
        result.append(BreakpointKind.BRIGHTNESS)
    if abs(left.metrics.bass_power - right.metrics.bass_power) >= 0.28:
        result.append(BreakpointKind.BASS)
    if distance.polarity_equivalent or distance.correlation <= -0.80:
        result.append(BreakpointKind.POLARITY)
    if not result:
        result.append(BreakpointKind.COMPOSITE)
    return tuple(result)


def _extreme_features(
    candidate: WavetableCandidate,
    shape: WaveShapeMetrics,
    all_candidates: Sequence[WavetableCandidate],
    all_shapes: Sequence[WaveShapeMetrics],
    thresholds: UsefulnessThresholds,
) -> tuple[str, ...]:
    features: dict[str, tuple[float, tuple[float, ...]]] = {
        "brightness": (candidate.metrics.brightness, tuple(item.metrics.brightness for item in all_candidates)),
        "bass_power": (candidate.metrics.bass_power, tuple(item.metrics.bass_power for item in all_candidates)),
        "harmonic_richness": (
            candidate.metrics.harmonic_richness,
            tuple(item.metrics.harmonic_richness for item in all_candidates),
        ),
        "complexity": (shape.complexity, tuple(item.complexity for item in all_shapes)),
        "rms": (shape.rms, tuple(item.rms for item in all_shapes)),
    }
    result: list[str] = []
    for name, (value, population) in features.items():
        span = max(population) - min(population)
        if span < thresholds.extreme_feature_span:
            continue
        edge = span * thresholds.extreme_edge_fraction
        if value <= min(population) + edge:
            result.append(f"{name}:minimum")
        elif value >= max(population) - edge:
            result.append(f"{name}:maximum")
    return tuple(result)


def analyze_candidate_structure(
    request: WavetableBuildRequest,
    thresholds: UsefulnessThresholds = DEFAULT_USEFULNESS_THRESHOLDS,
) -> WavetableStructureAnalysis:
    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(thresholds, UsefulnessThresholds):
        raise WavetableContractError("thresholds must be UsefulnessThresholds")

    ordered = _source_order(request)
    candidates = tuple(candidate for _, candidate in ordered)
    shapes = tuple(analyze_wave_shape(candidate) for candidate in candidates)
    intervals: list[WavetableIntervalAnalysis] = []
    for index, (left, right) in enumerate(zip(candidates, candidates[1:])):
        distance = compare_wave_shapes(left, right)
        if distance.perceptual_distance <= thresholds.stable_distance:
            interval_class = IntervalClass.STABLE
            kinds: tuple[BreakpointKind, ...] = ()
            reason = "Adjacent candidates are perceptually stable."
        elif distance.perceptual_distance >= thresholds.breakpoint_distance:
            interval_class = IntervalClass.BREAKPOINT
            kinds = _breakpoint_kinds(
                left,
                right,
                distance,
                shapes[index],
                shapes[index + 1],
            )
            reason = "Adjacent candidates form a structural breakpoint candidate."
        else:
            interval_class = IntervalClass.TRANSITION
            kinds = ()
            reason = (
                "Adjacent candidates form a strong transition interval."
                if distance.perceptual_distance >= thresholds.transition_distance
                else "Adjacent candidates form a moderate transition interval."
            )
        transition_strength = min(
            1.0,
            max(0.0, distance.perceptual_distance - thresholds.stable_distance)
            / max(thresholds.breakpoint_distance - thresholds.stable_distance, 1e-12),
        )
        intervals.append(
            WavetableIntervalAnalysis(
                schema_version=WAVETABLE_USEFULNESS_SCHEMA_VERSION,
                left_candidate_id=left.candidate_id,
                right_candidate_id=right.candidate_id,
                source_order_index=index,
                distance=distance,
                interval_class=interval_class,
                breakpoint_kinds=kinds,
                transition_strength=_q(transition_strength),
                reason=reason,
            )
        )

    analyses: list[CandidateUsefulnessAnalysis] = []
    for source_order_index, ((inventory_index, candidate), shape) in enumerate(zip(ordered, shapes)):
        left_interval = intervals[source_order_index - 1] if source_order_index > 0 else None
        right_interval = intervals[source_order_index] if source_order_index < len(intervals) else None
        adjacent = tuple(
            interval
            for interval in (left_interval, right_interval)
            if interval is not None
        )
        novelty = max((item.distance.perceptual_distance for item in adjacent), default=1.0)
        extremes = _extreme_features(candidate, shape, candidates, shapes, thresholds)
        endpoint = source_order_index in {0, len(candidates) - 1}
        breakpoint = any(item.interval_class is IntervalClass.BREAKPOINT for item in adjacent)
        stable = bool(adjacent) and all(item.interval_class is IntervalClass.STABLE for item in adjacent)
        transition = bool(adjacent) and not breakpoint and any(
            item.interval_class is IntervalClass.TRANSITION for item in adjacent
        )
        structural_score = (
            0.20 * candidate.metrics.usefulness_score
            + 0.15 * candidate.metrics.quality_score
            + 0.10 * candidate.metrics.stability_score
            + 0.15 * candidate.metrics.source_fidelity
            + 0.10 * candidate.metrics.xt_compatibility
            + 0.10 * candidate.metrics.perceptual_novelty
            + 0.15 * novelty
            + 0.05 * min(1.0, len(extremes) / 2.0)
        )
        effective_usefulness = (
            0.55 * candidate.metrics.usefulness_score
            + 0.20 * candidate.metrics.quality_score
            + 0.15 * novelty
            + 0.10 * candidate.metrics.xt_compatibility
        )
        if not candidate.structural_eligible:
            structure_class = CandidateStructureClass.INELIGIBLE
            reason = "Candidate is explicitly ineligible for structural use."
        elif breakpoint:
            structure_class = CandidateStructureClass.BREAKPOINT
            reason = "Candidate borders at least one breakpoint interval."
        elif extremes:
            structure_class = CandidateStructureClass.EXTREME
            reason = "Candidate preserves one or more feature extremes."
        elif endpoint or structural_score >= thresholds.structural_score:
            structure_class = CandidateStructureClass.STRUCTURAL
            reason = "Candidate is a structural candidate; V8-C will decide final keyframes."
        elif transition:
            structure_class = CandidateStructureClass.TRANSITION
            reason = "Candidate belongs to a transition region."
        else:
            structure_class = CandidateStructureClass.STABLE
            reason = "Candidate belongs to a stable region."

        evidence = [
            f"inventory-index={inventory_index}",
            f"source-order-index={source_order_index}",
            f"neighborhood-novelty={_q(novelty):.12f}",
            f"structural-score={_q(structural_score):.12f}",
        ]
        evidence.extend(extremes)
        analyses.append(
            CandidateUsefulnessAnalysis(
                schema_version=WAVETABLE_USEFULNESS_SCHEMA_VERSION,
                candidate_id=candidate.candidate_id,
                inventory_index=inventory_index,
                source_order_index=source_order_index,
                shape_metrics=shape,
                left_interval_sha256=None if left_interval is None else left_interval.analysis_sha256,
                right_interval_sha256=None if right_interval is None else right_interval.analysis_sha256,
                neighborhood_novelty=_q(min(1.0, novelty)),
                structural_score=_q(min(1.0, structural_score)),
                effective_usefulness_score=_q(min(1.0, effective_usefulness)),
                structure_class=structure_class,
                structural_candidate=structure_class in {
                    CandidateStructureClass.STRUCTURAL,
                    CandidateStructureClass.BREAKPOINT,
                    CandidateStructureClass.EXTREME,
                },
                breakpoint_candidate=structure_class is CandidateStructureClass.BREAKPOINT,
                transition_candidate=structure_class is CandidateStructureClass.TRANSITION,
                stable_candidate=structure_class is CandidateStructureClass.STABLE,
                extreme_features=extremes,
                evidence=tuple(evidence),
                reason=reason,
            )
        )

    warnings: list[str] = []
    if len(candidates) == 1:
        warnings.append("Only one candidate is available; no transition interval can be measured.")
    if not any(item.structural_candidate for item in analyses):
        warnings.append("No structural candidate was identified; V8-C must reject or override explicitly.")

    return WavetableStructureAnalysis(
        schema_version=WAVETABLE_USEFULNESS_SCHEMA_VERSION,
        request_sha256=request.analysis_sha256,
        candidate_inventory_sha256=request.candidate_inventory_sha256,
        thresholds=thresholds,
        source_order_candidate_ids=tuple(candidate.candidate_id for candidate in candidates),
        candidates=tuple(analyses),
        intervals=tuple(intervals),
        warnings=tuple(warnings),
        reason=(
            "Measured usefulness, stable regions, transition intervals, breakpoints and structural candidates without selecting final V8-C keyframes."
        ),
    )
