from __future__ import annotations

from dataclasses import replace

from v8b_helpers import (
    candidate,
    fixed_tail,
    metrics,
    ready_preflight,
    request,
    required_chronology,
    required_lock,
    sine,
    square,
)

from w_mwxt_wavetable_tool.wavetable import (
    GenerationMethod,
    KeyframeSelectionPolicy,
    WaveOrigin,
    analyze_wavetable_candidates,
    select_wavetable_keyframes,
)


def corpus(count: int):
    return tuple(
        candidate(
            f"c-{index:03d}",
            tuple(((sample_index * (index + 3) + index * 17) % 255) - 127 for sample_index in range(64)),
            source_index=index,
            seed=min(0.5, index / max(1, count) * 0.4),
        )
        for index in range(count)
    )


def mixed_corpus(count: int):
    items = list(corpus(count))
    for index in range(1, count, 2):
        items[index] = replace(
            items[index],
            origin=WaveOrigin.REPAIRED_RECONSTRUCTED,
            generation_method=GenerationMethod.AUTO_REPAIR,
            reason="Synthetic reconstructed V8-C candidate.",
        )
    return tuple(items)


def selection_for(candidates, *, locks=(), chronology=(), policy=None):
    req = request(tuple(candidates), locks=tuple(locks), chronology=tuple(chronology))
    v8b = analyze_wavetable_candidates(req)
    result = select_wavetable_keyframes(
        req,
        v8b,
        policy if policy is not None else KeyframeSelectionPolicy(),
    )
    return req, v8b, result


__all__ = [
    "candidate",
    "corpus",
    "fixed_tail",
    "metrics",
    "mixed_corpus",
    "ready_preflight",
    "request",
    "required_chronology",
    "required_lock",
    "selection_for",
    "sine",
    "square",
]
