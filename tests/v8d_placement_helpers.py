from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from v8b_helpers import required_chronology, required_lock
from v8c_selection_helpers import (
    candidate,
    corpus,
    mixed_corpus,
    selection_for,
    sine,
    square,
)

from w_mwxt_wavetable_tool.wavetable import (
    ChronologyConstraint,
    ConstraintStrength,
    KeyframeSelectionPolicy,
    OrderingStrategy,
    PlacementBias,
    PlacementPolicy,
    PositionLock,
    analyze_wavetable_candidates,
    build_wavetable_placement_variants,
    default_wavetable_build_policy,
    order_wavetable_keyframes,
    place_wavetable_ordering,
    select_wavetable_keyframes,
)


def preference_lock(position: int, candidate_id: str) -> PositionLock:
    return PositionLock(
        position=position,
        candidate_id=candidate_id,
        strength=ConstraintStrength.PREFERENCE,
        reason="Preference lock for V8-D test.",
    )


def preference_chronology(before: str, after: str) -> ChronologyConstraint:
    return ChronologyConstraint(
        before_candidate_id=before,
        after_candidate_id=after,
        strength=ConstraintStrength.PREFERENCE,
        reason="Preference chronology for V8-D test.",
    )


def _build_placement_context(
    count: int,
    *,
    candidates=None,
    locks=(),
    chronology=(),
    requested_variants: int = 1,
    selection_policy: KeyframeSelectionPolicy | None = None,
):
    items = tuple(corpus(count) if candidates is None else candidates)
    req, v8b, v8c = selection_for(
        items,
        locks=tuple(locks),
        chronology=tuple(chronology),
        policy=selection_policy,
    )
    req = replace(
        req,
        policy=default_wavetable_build_policy(
            requested_variant_count=requested_variants,
            allow_mixed_provenance=req.policy.allow_mixed_provenance,
            preserve_chronology=req.policy.preserve_chronology,
            allow_intentional_breaks=req.policy.allow_intentional_breaks,
            factory_style=req.policy.factory_style,
        ),
    )
    v8b = analyze_wavetable_candidates(req)
    v8c = select_wavetable_keyframes(
        req,
        v8b,
        selection_policy if selection_policy is not None else KeyframeSelectionPolicy(),
    )
    return req, v8b, v8c


@lru_cache(maxsize=64)
def _cached_placement_context(
    count: int,
    *,
    candidates=None,
    locks=(),
    chronology=(),
    requested_variants: int = 1,
    selection_policy: KeyframeSelectionPolicy | None = None,
):
    return _build_placement_context(
        count,
        candidates=candidates,
        locks=locks,
        chronology=chronology,
        requested_variants=requested_variants,
        selection_policy=selection_policy,
    )


def placement_context(
    count: int,
    *,
    candidates=None,
    locks=(),
    chronology=(),
    requested_variants: int = 1,
    selection_policy: KeyframeSelectionPolicy | None = None,
):
    builder = _cached_placement_context if count <= 16 else _build_placement_context
    return builder(
        count,
        candidates=candidates,
        locks=locks,
        chronology=chronology,
        requested_variants=requested_variants,
        selection_policy=selection_policy,
    )


def clear_placement_context_cache() -> None:
    _cached_placement_context.cache_clear()


def ordered_context(
    count: int,
    *,
    candidates=None,
    locks=(),
    chronology=(),
    requested_variants: int = 1,
    selection_policy: KeyframeSelectionPolicy | None = None,
    strategy: OrderingStrategy = OrderingStrategy.BALANCED,
    bias: PlacementBias = PlacementBias.BALANCED,
):
    req, v8b, v8c = placement_context(
        count,
        candidates=candidates,
        locks=locks,
        chronology=chronology,
        requested_variants=requested_variants,
        selection_policy=selection_policy,
    )
    ordering = order_wavetable_keyframes(req, v8b, v8c, strategy)
    placement = place_wavetable_ordering(
        req, v8b, v8c, ordering, PlacementPolicy(bias=bias)
    )
    return req, v8b, v8c, ordering, placement


def variants_context(
    count: int,
    *,
    candidates=None,
    locks=(),
    chronology=(),
    requested_variants: int = 1,
    selection_policy: KeyframeSelectionPolicy | None = None,
):
    req, v8b, v8c = placement_context(
        count,
        candidates=candidates,
        locks=locks,
        chronology=chronology,
        requested_variants=requested_variants,
        selection_policy=selection_policy,
    )
    result = build_wavetable_placement_variants(req, v8b, v8c)
    return req, v8b, v8c, result


__all__ = [
    "candidate",
    "clear_placement_context_cache",
    "corpus",
    "mixed_corpus",
    "ordered_context",
    "placement_context",
    "preference_chronology",
    "preference_lock",
    "required_chronology",
    "required_lock",
    "sine",
    "square",
    "variants_context",
]
