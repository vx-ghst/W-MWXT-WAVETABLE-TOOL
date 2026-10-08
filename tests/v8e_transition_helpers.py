from __future__ import annotations

from dataclasses import replace
import math

from v8d_placement_helpers import (
    candidate,
    corpus,
    mixed_corpus,
    required_chronology,
    required_lock,
    variants_context,
)

from w_mwxt_wavetable_tool.wavetable import (
    CodeV8DStatus,
    ContinuityThresholds,
    GenerationMethod,
    InterpolationPolicy,
    TransitionDensityPolicy,
    build_wavetable_transitions,
)


def smooth_candidates(count: int):
    if count < 1:
        raise ValueError("count must be positive")
    result = []
    for index in range(count):
        mix = index / max(1, count - 1)
        samples = tuple(
            max(
                -127,
                min(
                    127,
                    round(
                        (92.0 - 8.0 * mix)
                        * math.sin(2.0 * math.pi * sample_index / 128.0)
                        + 24.0
                        * mix
                        * math.sin(
                            4.0 * math.pi * sample_index / 128.0 + 0.35 * mix
                        )
                        + 12.0
                        * mix
                        * mix
                        * math.sin(6.0 * math.pi * sample_index / 128.0)
                    ),
                ),
            )
            for sample_index in range(64)
        )
        result.append(
            candidate(
                f"smooth-{index:03d}",
                samples,
                source_index=index,
                source_time_seconds=index / 10.0,
                seed=min(0.35, mix * 0.25),
            )
        )
    return tuple(result)


def relaxed_continuity_thresholds() -> ContinuityThresholds:
    return ContinuityThresholds(
        warning_perceptual_distance=0.98,
        failure_perceptual_distance=1.0,
        warning_spectral_distance=0.98,
        failure_spectral_distance=1.0,
        warning_level_delta=0.98,
        failure_level_delta=1.0,
        warning_fundamental_delta=0.98,
        failure_fundamental_delta=1.0,
        warning_maximum_sample_distance=0.98,
        failure_maximum_sample_distance=1.0,
        failure_correlation_floor=-1.0,
    )


def transition_context(
    count: int = 2,
    *,
    candidates=None,
    locks=(),
    chronology=(),
    requested_variants: int = 1,
    interpolation_policy: InterpolationPolicy | None = None,
    density_policy: TransitionDensityPolicy | None = None,
    relaxed: bool = True,
):
    items = smooth_candidates(count) if candidates is None else tuple(candidates)
    request, v8b, v8c, v8d = variants_context(
        len(items),
        candidates=items,
        locks=tuple(locks),
        chronology=tuple(chronology),
        requested_variants=requested_variants,
    )
    result = build_wavetable_transitions(
        request,
        v8b,
        v8c,
        v8d,
        InterpolationPolicy() if interpolation_policy is None else interpolation_policy,
        TransitionDensityPolicy() if density_policy is None else density_policy,
        relaxed_continuity_thresholds() if relaxed else ContinuityThresholds(),
    )
    return request, v8b, v8c, v8d, result


def rejected_v8d(v8d):
    return replace(
        v8d,
        status=CodeV8DStatus.REJECTED,
        variants=(),
        primary_variant_id=None,
        blockers=("synthetic rejected V8-D input",),
        reason="Synthetic rejected V8-D input for V8-E tests.",
    )


ALL_INTERPOLATION_METHODS = (
    GenerationMethod.WAVEFORM_INTERPOLATION,
    GenerationMethod.AMPLITUDE_INTERPOLATION,
    GenerationMethod.PHASE_AWARE_INTERPOLATION,
    GenerationMethod.SPECTRAL_INTERPOLATION,
    GenerationMethod.HARMONIC_INTERPOLATION,
    GenerationMethod.PERCEPTUAL_INTERPOLATION,
)


__all__ = [
    "ALL_INTERPOLATION_METHODS",
    "candidate",
    "corpus",
    "mixed_corpus",
    "rejected_v8d",
    "relaxed_continuity_thresholds",
    "required_chronology",
    "required_lock",
    "smooth_candidates",
    "transition_context",
]
