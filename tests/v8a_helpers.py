from __future__ import annotations

from types import SimpleNamespace

from w_mwxt_wavetable_tool.wavetable import (
    ConstraintStrength,
    FixedTailContract,
    GenerationMethod,
    WaveBuildMetrics,
    WaveOrigin,
    WaveRole,
    WavetableBuild,
    WavetableBuildStatus,
    WavetableCandidate,
    WavetableSlot,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def samples(offset: int = 0) -> tuple[int, ...]:
    return tuple(max(-127, min(127, ((index * 7 + offset) % 255) - 127)) for index in range(64))


def metrics(seed: float = 0.0) -> WaveBuildMetrics:
    values = [min(1.0, 0.10 + seed + index * 0.07) for index in range(9)]
    return WaveBuildMetrics(
        quality_score=values[0],
        usefulness_score=values[1],
        stability_score=values[2],
        harmonic_richness=values[3],
        brightness=values[4],
        bass_power=values[5],
        source_fidelity=values[6],
        xt_compatibility=values[7],
        perceptual_novelty=values[8],
        reason="Deterministic synthetic metrics.",
    )


def candidate(
    candidate_id: str = "candidate-01",
    *,
    origin: WaveOrigin = WaveOrigin.REPAIRED_REAL,
    generation_method: GenerationMethod = GenerationMethod.AUTO_REPAIR,
    source_index: int = 0,
    offset: int = 0,
) -> WavetableCandidate:
    return WavetableCandidate(
        schema_version=1,
        candidate_id=candidate_id,
        source_artifact_sha256=HASH_A,
        origin=origin,
        generation_method=generation_method,
        stored_samples=samples(offset),
        metrics=metrics(offset / 1000.0),
        source_time_seconds=source_index / 10.0,
        source_index=source_index,
        structural_eligible=True,
        evidence=("synthetic evidence",),
        reason="Synthetic candidate for contract tests.",
    )


def fixed_tail() -> FixedTailContract:
    return FixedTailContract(
        schema_version=1,
        source_wctd_sha256=HASH_B,
        references=(1, 2, 3),
        reason="Preserve the three baseline fixed references.",
    )


def ready_preflight(*, repaired_wave_count: int = 2):
    return SimpleNamespace(
        status=SimpleNamespace(value="ready"),
        analysis_sha256=HASH_C,
        source_chain=SimpleNamespace(
            sample_rate=48000,
            sample_count=96000,
            sample_sha256=HASH_D,
        ),
        decision_plan=SimpleNamespace(
            repaired_wave_count=repaired_wave_count,
            selected_mode="hybrid",
            selected_profile="pad",
        ),
    )


def rejected_preflight():
    result = ready_preflight()
    result.status = SimpleNamespace(value="rejected")
    result.decision_plan.selected_mode = None
    return result


def slot(
    position: int,
    *,
    role: WaveRole = WaveRole.STABLE,
    origin: WaveOrigin = WaveOrigin.REPAIRED_REAL,
    method: GenerationMethod = GenerationMethod.AUTO_REPAIR,
    structural: bool = False,
    candidate_ids: tuple[str, ...] = ("candidate-01",),
) -> WavetableSlot:
    return WavetableSlot(
        schema_version=1,
        position=position,
        stored_samples=samples(position),
        role=role,
        origin=origin,
        generation_method=method,
        metrics=metrics(position / 1000.0),
        source_candidate_ids=candidate_ids,
        source_time_seconds=position / 10.0,
        locked=False,
        structural=structural,
        transition=role is WaveRole.TRANSITION,
        redundant=role is WaveRole.REDUNDANT,
        evidence=("slot evidence",),
        reason="Synthetic slot.",
    )


def complete_slots() -> tuple[WavetableSlot, ...]:
    result = []
    for position in range(61):
        if position == 0:
            result.append(slot(position, role=WaveRole.ESSENTIAL, structural=True))
        elif position == 30:
            result.append(slot(position, role=WaveRole.STRUCTURAL, structural=True))
        else:
            result.append(slot(position))
    return tuple(result)


def complete_build(variant_id: str = "variant-01") -> WavetableBuild:
    return WavetableBuild(
        schema_version=1,
        tool_version="0.7.0",
        request_sha256=HASH_A,
        preflight_analysis_sha256=HASH_C,
        variant_id=variant_id,
        status=WavetableBuildStatus.COMPLETE,
        slots=complete_slots(),
        fixed_tail=fixed_tail(),
        blockers=(),
        warnings=(),
        reason="Complete synthetic build.",
    )
