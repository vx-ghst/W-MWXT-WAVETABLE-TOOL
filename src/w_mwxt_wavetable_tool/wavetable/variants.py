from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from .deduplication import CodeV8BAnalysis
from .models import WavetableBuildRequest, WavetableContractError
from .ordering import (
    OrderingStrategy,
    WavetableOrdering,
    order_wavetable_keyframes,
)
from .placement import (
    PlacementBias,
    PlacementPolicy,
    PlacementStatus,
    WavetablePlacement,
    place_wavetable_ordering,
)
from .selection import CodeV8CAnalysis

WAVETABLE_VARIANTS_SCHEMA_VERSION = 1


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


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


class CodeV8DStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class WavetablePlacementVariant:
    schema_version: int
    variant_id: str
    rank: int
    ordering_strategy: OrderingStrategy
    placement_bias: PlacementBias
    ordering: WavetableOrdering
    placement: WavetablePlacement
    moved_candidate_ids: tuple[str, ...]
    mean_position_delta_from_primary: float
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_VARIANTS_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported placement-variant schema version")
        _normalized(self.variant_id, name="variant_id")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise WavetableContractError("rank must be a positive integer")
        if not isinstance(self.ordering_strategy, OrderingStrategy):
            raise WavetableContractError("ordering_strategy must be OrderingStrategy")
        if not isinstance(self.placement_bias, PlacementBias):
            raise WavetableContractError("placement_bias must be PlacementBias")
        if not isinstance(self.ordering, WavetableOrdering):
            raise WavetableContractError("ordering must be WavetableOrdering")
        if not isinstance(self.placement, WavetablePlacement):
            raise WavetableContractError("placement must be WavetablePlacement")
        if self.placement.status is not PlacementStatus.COMPLETE:
            raise WavetableContractError("placement variants must be complete")
        if self.placement.ordering_sha256 != self.ordering.analysis_sha256:
            raise WavetableContractError("placement does not link to ordering")
        moved = _entries(self.moved_candidate_ids, name="moved_candidate_ids")
        object.__setattr__(self, "moved_candidate_ids", moved)
        delta = float(self.mean_position_delta_from_primary)
        if delta < 0.0 or delta > 60.0:
            raise WavetableContractError(
                "mean_position_delta_from_primary must be between 0 and 60"
            )
        _normalized(self.reason, name="reason")

    @property
    def objective_score(self) -> float:
        assert self.placement.score is not None
        return self.placement.score.objective_score

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "rank": self.rank,
            "ordering_strategy": self.ordering_strategy.value,
            "placement_bias": self.placement_bias.value,
            "ordering": self.ordering.to_dict(),
            "placement": self.placement.to_dict(),
            "objective_score": self.objective_score,
            "moved_candidate_ids": list(self.moved_candidate_ids),
            "mean_position_delta_from_primary": self.mean_position_delta_from_primary,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class CodeV8DAnalysis:
    schema_version: int
    status: CodeV8DStatus
    request_sha256: str
    v8b_analysis_sha256: str
    v8c_analysis_sha256: str
    requested_variant_count: int
    variants: tuple[WavetablePlacementVariant, ...]
    primary_variant_id: str | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_VARIANTS_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-D schema version")
        if not isinstance(self.status, CodeV8DStatus):
            raise WavetableContractError("status must be CodeV8DStatus")
        for name in ("request_sha256", "v8b_analysis_sha256", "v8c_analysis_sha256"):
            _sha256(getattr(self, name), name=name)
        if (
            isinstance(self.requested_variant_count, bool)
            or not isinstance(self.requested_variant_count, int)
            or not 1 <= self.requested_variant_count <= 16
        ):
            raise WavetableContractError("requested_variant_count must be between 1 and 16")
        variants = tuple(self.variants)
        warnings = _entries(self.warnings, name="warnings")
        blockers = _entries(self.blockers, name="blockers")
        object.__setattr__(self, "variants", variants)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "blockers", blockers)
        if any(not isinstance(item, WavetablePlacementVariant) for item in variants):
            raise WavetableContractError("variants contain invalid values")
        variant_ids = tuple(item.variant_id for item in variants)
        if len(set(variant_ids)) != len(variant_ids):
            raise WavetableContractError("variant IDs must be unique")
        if tuple(item.rank for item in variants) != tuple(range(1, len(variants) + 1)):
            raise WavetableContractError("variant ranks must be canonical")
        if len(variants) > self.requested_variant_count:
            raise WavetableContractError("variant count exceeds request")
        _normalized(self.reason, name="reason")
        if self.status is CodeV8DStatus.COMPLETE:
            if blockers:
                raise WavetableContractError("complete V8-D analysis cannot contain blockers")
            if not variants or self.primary_variant_id is None:
                raise WavetableContractError("complete V8-D analysis requires variants")
            if self.primary_variant_id not in variant_ids:
                raise WavetableContractError("primary_variant_id is not present")
            if variants[0].variant_id != self.primary_variant_id:
                raise WavetableContractError("primary variant must have rank one")
            scores = tuple(item.objective_score for item in variants)
            if scores != tuple(sorted(scores, reverse=True)):
                raise WavetableContractError("variants must be ranked by score")
        else:
            if not blockers:
                raise WavetableContractError("rejected V8-D analysis requires blockers")
            if variants or self.primary_variant_id is not None:
                raise WavetableContractError("rejected V8-D analysis cannot expose variants")

    @property
    def produced_variant_count(self) -> int:
        return len(self.variants)

    @property
    def primary_variant(self) -> WavetablePlacementVariant | None:
        if self.primary_variant_id is None:
            return None
        return next(
            item for item in self.variants if item.variant_id == self.primary_variant_id
        )

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "v8b_analysis_sha256": self.v8b_analysis_sha256,
            "v8c_analysis_sha256": self.v8c_analysis_sha256,
            "requested_variant_count": self.requested_variant_count,
            "produced_variant_count": self.produced_variant_count,
            "primary_variant_id": self.primary_variant_id,
            "variants": [item.to_dict() for item in self.variants],
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "orders_final_keyframes": True,
                "assigns_user_positions": True,
                "generates_placement_variants": True,
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


def _variant_specs() -> tuple[tuple[OrderingStrategy, PlacementBias], ...]:
    strategies = (
        OrderingStrategy.BALANCED,
        OrderingStrategy.SOURCE_FIDELITY,
        OrderingStrategy.SCAN_SMOOTHNESS,
        OrderingStrategy.HARMONIC_DIVERSITY,
        OrderingStrategy.BASS_STRENGTH,
        OrderingStrategy.DISCONTINUITY_AVOIDANCE,
    )
    biases = (
        PlacementBias.BALANCED,
        PlacementBias.EDGE_EXPANDED,
        PlacementBias.EARLY,
        PlacementBias.LATE,
        PlacementBias.CENTER,
    )
    return tuple((strategy, bias) for bias in biases for strategy in strategies)


def _placement_signature(placement: WavetablePlacement) -> tuple[tuple[str, int], ...]:
    return tuple(
        (item.candidate_id, item.position)
        for item in sorted(placement.assignments, key=lambda item: item.candidate_id)
    )


def _difference(
    placement: WavetablePlacement,
    primary: WavetablePlacement,
) -> tuple[tuple[str, ...], float]:
    current = {item.candidate_id: item.position for item in placement.assignments}
    baseline = {item.candidate_id: item.position for item in primary.assignments}
    common = tuple(sorted(set(current) & set(baseline)))
    moved = tuple(item for item in common if current[item] != baseline[item])
    delta = (
        0.0
        if not common
        else sum(abs(current[item] - baseline[item]) for item in common) / len(common)
    )
    return moved, round(delta, 12)


def build_wavetable_placement_variants(
    request: WavetableBuildRequest,
    v8b_analysis: CodeV8BAnalysis,
    v8c_analysis: CodeV8CAnalysis,
) -> CodeV8DAnalysis:
    """Build and rank deterministic V8-D ordering and placement variants."""

    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(v8b_analysis, CodeV8BAnalysis):
        raise WavetableContractError("v8b_analysis must be CodeV8BAnalysis")
    if not isinstance(v8c_analysis, CodeV8CAnalysis):
        raise WavetableContractError("v8c_analysis must be CodeV8CAnalysis")
    requested = request.policy.requested_variant_count
    candidates: list[tuple[OrderingStrategy, PlacementBias, WavetableOrdering, WavetablePlacement]] = []
    signatures: set[tuple[tuple[str, int], ...]] = set()
    blockers: list[str] = []
    warnings = list(v8c_analysis.warnings)
    ordering_cache: dict[OrderingStrategy, WavetableOrdering] = {}
    for strategy, bias in _variant_specs():
        ordering = ordering_cache.get(strategy)
        if ordering is None:
            ordering = order_wavetable_keyframes(
                request,
                v8b_analysis,
                v8c_analysis,
                strategy,
            )
            ordering_cache[strategy] = ordering
        placement = place_wavetable_ordering(
            request,
            v8b_analysis,
            v8c_analysis,
            ordering,
            PlacementPolicy(bias=bias),
        )
        if placement.status is not PlacementStatus.COMPLETE:
            blockers.extend(placement.blockers)
            continue
        signature = _placement_signature(placement)
        if signature in signatures:
            continue
        signatures.add(signature)
        candidates.append((strategy, bias, ordering, placement))

    if not candidates:
        return CodeV8DAnalysis(
            schema_version=WAVETABLE_VARIANTS_SCHEMA_VERSION,
            status=CodeV8DStatus.REJECTED,
            request_sha256=request.analysis_sha256,
            v8b_analysis_sha256=v8b_analysis.analysis_sha256,
            v8c_analysis_sha256=v8c_analysis.analysis_sha256,
            requested_variant_count=requested,
            variants=(),
            primary_variant_id=None,
            warnings=tuple(dict.fromkeys(warnings)),
            blockers=tuple(dict.fromkeys(blockers)) or (
                "no complete ordering and placement variant was feasible",
            ),
            reason="CODE V8-D rejected the placement request without exposing partial variants.",
        )

    candidates.sort(
        key=lambda item: (
            -item[3].score.objective_score,
            item[0].value,
            item[1].value,
            item[3].analysis_sha256,
        )
    )
    unique_feasible_count = len(candidates)
    candidates = candidates[:requested]
    primary_placement = candidates[0][3]
    variants: list[WavetablePlacementVariant] = []
    for rank, (strategy, bias, ordering, placement) in enumerate(candidates, 1):
        moved, delta = _difference(placement, primary_placement)
        variants.append(
            WavetablePlacementVariant(
                schema_version=WAVETABLE_VARIANTS_SCHEMA_VERSION,
                variant_id=f"v8d-{rank:02d}-{strategy.value}-{bias.value}",
                rank=rank,
                ordering_strategy=strategy,
                placement_bias=bias,
                ordering=ordering,
                placement=placement,
                moved_candidate_ids=moved,
                mean_position_delta_from_primary=delta,
                reason=(
                    "Primary deterministic V8-D placement variant."
                    if rank == 1
                    else "Alternative deterministic V8-D ordering or spacing variant."
                ),
            )
        )
    if unique_feasible_count < requested:
        warnings.append(
            f"only {unique_feasible_count} unique feasible placement variants exist for the requested {requested}"
        )
    return CodeV8DAnalysis(
        schema_version=WAVETABLE_VARIANTS_SCHEMA_VERSION,
        status=CodeV8DStatus.COMPLETE,
        request_sha256=request.analysis_sha256,
        v8b_analysis_sha256=v8b_analysis.analysis_sha256,
        v8c_analysis_sha256=v8c_analysis.analysis_sha256,
        requested_variant_count=requested,
        variants=tuple(variants),
        primary_variant_id=variants[0].variant_id,
        warnings=tuple(dict.fromkeys(warnings)),
        blockers=(),
        reason="CODE V8-D ranked deterministic explainable ordering and sparse placement variants for V8-E.",
    )


__all__ = [
    "WAVETABLE_VARIANTS_SCHEMA_VERSION",
    "CodeV8DAnalysis",
    "CodeV8DStatus",
    "WavetablePlacementVariant",
    "build_wavetable_placement_variants",
]
