from __future__ import annotations

from dataclasses import replace

from v8d_placement_helpers import variants_context
from v8e_transition_helpers import smooth_candidates
from v8g_helpers import region_analysis

from w_mwxt_wavetable_tool import (
    analyze_wavetable_candidates,
    build_wavetable_placement_variants,
    select_wavetable_keyframes,
)


def v8h_context(
    count: int = 6,
    *,
    profile: str = "pad",
    factory_style: bool = True,
    requested_variants: int = 3,
    locks=(),
    chronology=(),
):
    candidates = smooth_candidates(count)
    request, _, _, _ = variants_context(
        count,
        candidates=candidates,
        locks=tuple(locks),
        chronology=tuple(chronology),
        requested_variants=requested_variants,
    )
    request = replace(
        request,
        selected_profile=profile,
        policy=replace(request.policy, factory_style=factory_style),
    )
    v8b = analyze_wavetable_candidates(request)
    v8c = select_wavetable_keyframes(request, v8b)
    v8d = build_wavetable_placement_variants(request, v8b, v8c)
    return request, v8b, v8c, v8d, region_analysis()


__all__ = ["v8h_context"]
