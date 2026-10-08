from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from functools import lru_cache

from v8d_placement_helpers import variants_context
from v8e_transition_helpers import relaxed_continuity_thresholds, smooth_candidates

from w_mwxt_wavetable_tool.wavetable import (
    analyze_wavetable_candidates,
    build_wavetable_placement_variants,
    build_wavetable_transitions,
    default_wavetable_build_policy,
    select_wavetable_keyframes,
)
from w_mwxt_wavetable_tool.wavetable.factory_style import FactoryStylePolicy, apply_factory_style
from w_mwxt_wavetable_tool.wavetable.hardware_gate import (
    HARDWARE_GATE_SCHEMA_VERSION,
    HardwareGateEvidence,
    build_code_v8f,
)
from w_mwxt_wavetable_tool.wavetable.wctd import materialize_wctd_models


def _artifact(label: str) -> str:
    return sha256(label.encode("ascii")).hexdigest()


@lru_cache(maxsize=32)
def build_v8e_context(
    count: int = 2,
    *,
    factory_style: bool = False,
    requested_variants: int = 1,
):
    items = smooth_candidates(count)
    request, v8b, v8c, _ = variants_context(
        count,
        candidates=items,
        requested_variants=requested_variants,
    )
    request = replace(
        request,
        policy=default_wavetable_build_policy(
            requested_variant_count=requested_variants,
            progression_curve=request.policy.progression_curve,
            allow_mixed_provenance=request.policy.allow_mixed_provenance,
            preserve_chronology=request.policy.preserve_chronology,
            allow_intentional_breaks=request.policy.allow_intentional_breaks,
            factory_style=factory_style,
        ),
    )
    v8b = analyze_wavetable_candidates(request)
    v8c = select_wavetable_keyframes(request, v8b)
    v8d = build_wavetable_placement_variants(request, v8b, v8c)
    v8e = build_wavetable_transitions(
        request,
        v8b,
        v8c,
        v8d,
        continuity_thresholds=relaxed_continuity_thresholds(),
    )
    return request, v8b, v8c, v8d, v8e


def allocation_map(factory_style_analysis, *, start: int = 1000):
    references = tuple(start + index for index in range(61))
    return {variant.variant_id: references for variant in factory_style_analysis.variants}


def passing_hardware_evidence(model):
    words = model.reference_words
    return (
        HardwareGateEvidence(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-known-reference-pair",
            _artifact("known-pair"),
            True,
            (0, 60),
            (words[0], words[60]),
            None,
            ("two references read from hardware",),
            "Known pair matched the planned WCTD reference words.",
        ),
        HardwareGateEvidence(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-intermediate-positions",
            _artifact("intermediate"),
            True,
            (30,),
            (words[30],),
            None,
            ("intermediate position observed",),
            "Intermediate position matched the planned reference.",
        ),
        HardwareGateEvidence(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-tail-positions-60-63",
            _artifact("tail"),
            True,
            (60, 61, 62, 63),
            tuple(words[index] for index in (60, 61, 62, 63)),
            None,
            ("tail positions read from hardware",),
            "Final user position and fixed tail matched the model.",
        ),
        HardwareGateEvidence(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-slow-scan",
            _artifact("slow-scan"),
            True,
            (),
            (),
            None,
            ("controlled slow scan passed",),
            "Slow scan accepted under controlled observation.",
        ),
        HardwareGateEvidence(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-fast-scan",
            _artifact("fast-scan"),
            True,
            (),
            (),
            None,
            ("controlled fast scan passed",),
            "Fast scan accepted under controlled observation.",
        ),
        HardwareGateEvidence(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-read-back",
            _artifact("read-back"),
            True,
            tuple(range(64)),
            words,
            model.reference_payload_sha256,
            ("complete 64-reference read-back",),
            "Complete reference payload matched exactly.",
        ),
    )


def failing_hardware_evidence(model):
    evidence = list(passing_hardware_evidence(model))
    evidence[0] = replace(
        evidence[0],
        passed=False,
        reason="Synthetic hardware failure for V8-F tests.",
    )
    return tuple(evidence)


@lru_cache(maxsize=32)
def v8f_context(
    count: int = 2,
    *,
    factory_style: bool = False,
    resolved: bool = False,
    evidence_mode: str = "none",
    requested_variants: int = 1,
    policy: FactoryStylePolicy | None = None,
):
    request, v8b, v8c, v8d, v8e = build_v8e_context(
        count,
        factory_style=factory_style,
        requested_variants=requested_variants,
    )
    selected_policy = FactoryStylePolicy() if policy is None else policy
    factory = apply_factory_style(request, v8e, selected_policy)
    allocations = allocation_map(factory) if resolved else None
    models = materialize_wctd_models(factory, allocations)
    hardware_evidence = ()
    if evidence_mode == "pass":
        hardware_evidence = passing_hardware_evidence(models.primary_model)
    elif evidence_mode == "fail":
        hardware_evidence = failing_hardware_evidence(models.primary_model)
    elif evidence_mode != "none":
        raise ValueError("unsupported evidence mode")
    result = build_code_v8f(
        request,
        v8e,
        selected_policy,
        allocations,
        hardware_evidence,
    )
    return request, v8b, v8c, v8d, v8e, result


__all__ = [
    "allocation_map",
    "build_v8e_context",
    "failing_hardware_evidence",
    "passing_hardware_evidence",
    "v8f_context",
]
