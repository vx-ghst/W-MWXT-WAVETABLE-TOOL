from __future__ import annotations

from types import SimpleNamespace

from w_mwxt_wavetable_tool.wavetable import (
    ChronologyConstraint,
    ConstraintStrength,
    FixedTailContract,
    GenerationMethod,
    PositionLock,
    WaveBuildMetrics,
    WaveOrigin,
    WavetableCandidate,
    create_wavetable_build_request,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def ramp(offset: int = 0, scale: int = 1) -> tuple[int, ...]:
    return tuple(max(-127, min(127, ((index * 4 + offset) % 255) - 127)) * scale for index in range(64))


def sine(amplitude: int = 100, harmonic: int = 1, phase: float = 0.0) -> tuple[int, ...]:
    import math

    return tuple(
        max(-127, min(127, round(amplitude * math.sin(2.0 * math.pi * harmonic * index / 128.0 + phase))))
        for index in range(64)
    )


def square(amplitude: int = 100, duty: int = 32) -> tuple[int, ...]:
    return tuple(amplitude if index < duty else -amplitude for index in range(64))


def metrics(seed: float = 0.0, *, usefulness: float | None = None) -> WaveBuildMetrics:
    values = [min(1.0, 0.25 + seed + index * 0.05) for index in range(9)]
    if usefulness is not None:
        values[1] = usefulness
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
        reason="Deterministic V8-B metrics.",
    )


def candidate(
    candidate_id: str,
    samples: tuple[int, ...],
    *,
    source_index: int,
    source_time_seconds: float | None = None,
    structural_eligible: bool = True,
    seed: float = 0.0,
    usefulness: float | None = None,
) -> WavetableCandidate:
    return WavetableCandidate(
        schema_version=1,
        candidate_id=candidate_id,
        source_artifact_sha256=HASH_A,
        origin=WaveOrigin.REPAIRED_REAL,
        generation_method=GenerationMethod.AUTO_REPAIR,
        stored_samples=samples,
        metrics=metrics(seed, usefulness=usefulness),
        source_time_seconds=(source_index / 10.0 if source_time_seconds is None else source_time_seconds),
        source_index=source_index,
        structural_eligible=structural_eligible,
        evidence=("synthetic V8-B evidence",),
        reason="Synthetic V8-B candidate.",
    )


def ready_preflight(count: int):
    return SimpleNamespace(
        status=SimpleNamespace(value="ready"),
        analysis_sha256=HASH_C,
        source_chain=SimpleNamespace(
            sample_rate=48000,
            sample_count=96000,
            sample_sha256=HASH_D,
        ),
        decision_plan=SimpleNamespace(
            repaired_wave_count=count,
            selected_mode="hybrid",
            selected_profile="pad",
        ),
    )


def fixed_tail() -> FixedTailContract:
    return FixedTailContract(
        schema_version=1,
        source_wctd_sha256=HASH_B,
        references=(1, 2, 3),
        reason="Preserve fixed tail.",
    )


def request(
    candidates: tuple[WavetableCandidate, ...],
    *,
    locks: tuple[PositionLock, ...] = (),
    chronology: tuple[ChronologyConstraint, ...] = (),
):
    return create_wavetable_build_request(
        ready_preflight(len(candidates)),
        candidates,
        fixed_tail(),
        position_locks=locks,
        chronology_constraints=chronology,
    )


def required_lock(position: int, candidate_id: str) -> PositionLock:
    return PositionLock(
        position=position,
        candidate_id=candidate_id,
        strength=ConstraintStrength.REQUIRED,
        reason="Required lock for V8-B test.",
    )


def required_chronology(before: str, after: str) -> ChronologyConstraint:
    return ChronologyConstraint(
        before_candidate_id=before,
        after_candidate_id=after,
        strength=ConstraintStrength.REQUIRED,
        reason="Required chronology for V8-B test.",
    )
