from __future__ import annotations

from dataclasses import replace

from v8a_helpers import complete_build, metrics, samples

from w_mwxt_wavetable_tool import (
    GenerationMethod,
    WaveOrigin,
    WaveRole,
    WavetableBuild,
)


def build_with_slots(slots, *, variant_id: str = "variant-v8i") -> WavetableBuild:
    base = complete_build(variant_id)
    return replace(base, slots=tuple(slots), reason="Synthetic final build for V8-I tests.")


def identical_build() -> WavetableBuild:
    base = complete_build("identical-v8i")
    shared = samples(17)
    slots = tuple(
        replace(
            slot,
            stored_samples=shared,
            metrics=metrics(0.01),
            source_candidate_ids=(f"candidate-{slot.position:02d}",),
            reason="Exact shared XT-native wave.",
        )
        for slot in base.slots
    )
    return replace(base, slots=slots)


def distinct_build() -> WavetableBuild:
    return complete_build("distinct-v8i")


def exact_mixed_provenance_build() -> WavetableBuild:
    base = complete_build("mixed-v8i")
    shared = samples(29)
    slots = list(base.slots)
    slots[5] = replace(
        slots[5],
        stored_samples=shared,
        origin=WaveOrigin.REAL_CYCLE,
        generation_method=GenerationMethod.SOURCE_CYCLE,
        source_candidate_ids=("real-cycle",),
        reason="Real source position.",
    )
    slots[6] = replace(
        slots[6],
        stored_samples=shared,
        origin=WaveOrigin.RECONSTRUCTED_CYCLE,
        generation_method=GenerationMethod.SPECTRAL_RECONSTRUCTION,
        source_candidate_ids=("reconstructed-cycle",),
        reason="Reconstructed source position.",
    )
    return replace(base, slots=tuple(slots))


def near_pair_build(*, protected: bool = False) -> WavetableBuild:
    base = complete_build("near-v8i-protected" if protected else "near-v8i")
    slots = list(base.slots)
    first = list(samples(40))
    second = list(first)
    second[7] = max(-127, min(127, second[7] + 1))
    common = dict(
        role=WaveRole.TRANSITION,
        origin=WaveOrigin.INTERPOLATED_TRANSITION,
        generation_method=GenerationMethod.WAVEFORM_INTERPOLATION,
        metrics=metrics(0.02),
        source_candidate_ids=("left", "right"),
        structural=False,
        transition=True,
        redundant=False,
    )
    slots[10] = replace(
        slots[10],
        stored_samples=tuple(first),
        locked=protected,
        reason="Near-pair representative.",
        **common,
    )
    slots[11] = replace(
        slots[11],
        stored_samples=tuple(second),
        locked=False,
        reason="Near-pair candidate.",
        **common,
    )
    return replace(base, slots=tuple(slots))


def polarity_pair_build() -> WavetableBuild:
    base = complete_build("polarity-v8i")
    slots = list(base.slots)
    first = samples(53)
    slots[20] = replace(slots[20], stored_samples=first, metrics=metrics(0.03))
    slots[21] = replace(
        slots[21],
        stored_samples=tuple(-value for value in first),
        metrics=metrics(0.03),
    )
    return replace(base, slots=tuple(slots))


__all__ = [
    "build_with_slots",
    "identical_build",
    "distinct_build",
    "exact_mixed_provenance_build",
    "near_pair_build",
    "polarity_pair_build",
]
