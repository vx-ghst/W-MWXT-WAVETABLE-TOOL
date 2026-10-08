from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256

from v8h_helpers import v8h_context
from v8i_helpers import identical_build

from w_mwxt_wavetable_tool import (
    DumpFile,
    GenerationMethod,
    INTERPOLATED_WAVE_REFERENCE,
    InventoryDumpSource,
    InventorySourceKind,
    UserWave,
    UserWavetable,
    ValidatedEmptyWaveSignature,
    WaveOrigin,
    WaveRole,
    build_code_v8h,
    build_code_v8i,
    consolidate_wavetable_build,
)
from w_mwxt_wavetable_tool.wavetable.consolidation import PhysicalWaveSet


def samples_for_number(number: int) -> tuple[int, ...]:
    return tuple(((number * 11 + index * 7) % 255) - 127 for index in range(64))


def empty_samples() -> tuple[int, ...]:
    return (0,) * 64


def make_complete_dump(
    *,
    empty_numbers: tuple[int, ...] = (1100, 1101, 1102, 1103),
    referenced_numbers: tuple[int, ...] = (1000, 1001, 1002),
    device_id: int = 0,
) -> DumpFile:
    empty = set(empty_numbers)
    messages = [
        UserWave(
            device_id=device_id,
            number=number,
            stored_samples=empty_samples() if number in empty else samples_for_number(number),
        ).to_message()
        for number in range(1000, 1250)
    ]
    for display in range(97, 129):
        refs = [INTERPOLATED_WAVE_REFERENCE] * 64
        if display == 97:
            for index, number in enumerate(referenced_numbers):
                refs[index] = number
        messages.append(
            UserWavetable.from_display_number(device_id, display, tuple(refs)).to_message()
        )
    return DumpFile(tuple(messages))


def make_partial_dump(*, device_id: int = 0) -> DumpFile:
    table_refs = (1000,) + (INTERPOLATED_WAVE_REFERENCE,) * 63
    return DumpFile(
        (
            UserWave(device_id, 1000, samples_for_number(1000)).to_message(),
            UserWave(device_id, 1100, empty_samples()).to_message(),
            UserWavetable.from_display_number(device_id, 97, table_refs).to_message(),
        )
    )


def complete_source(**kwargs) -> InventoryDumpSource:
    return InventoryDumpSource(
        source_id="everything-current",
        source_kind=InventorySourceKind.BACKUP_EVERYTHING,
        dump=make_complete_dump(**kwargs),
        captured_current_state=True,
    )


def partial_source() -> InventoryDumpSource:
    return InventoryDumpSource(
        source_id="partial-current",
        source_kind=InventorySourceKind.CURRENT_EXTERNAL_CAPTURE,
        dump=make_partial_dump(),
        captured_current_state=True,
    )


def validated_empty_signature() -> ValidatedEmptyWaveSignature:
    return ValidatedEmptyWaveSignature(
        schema_version=1,
        stored_samples=empty_samples(),
        hardware_evidence_sha256=sha256(b"validated-empty-wave-hardware-evidence").hexdigest(),
        evidence_ids=("V8K-EMPTY-WAVE-READBACK",),
        validated_on_hardware=True,
        reason="Synthetic test fixture representing later V8-K hardware validation.",
    )


def physical_set(count: int) -> PhysicalWaveSet:
    if not 1 <= count <= 61:
        raise ValueError("count must be in 1..61")
    analysis = consolidate_wavetable_build(identical_build())
    assert analysis.physical_wave_set is not None
    prototype = analysis.physical_wave_set.waves[0]
    waves = []
    for index in range(count):
        samples = list(prototype.stored_samples)
        samples[index % 64] = max(-127, min(127, samples[index % 64] + index))
        waves.append(
            replace(
                prototype,
                physical_index=index,
                wave_id=f"v8j-wave-{index:02d}",
                representative_position=index,
                stored_samples=tuple(samples),
                logical_positions=(index,),
                logical_slot_sha256s=(sha256(f"slot-{index}".encode()).hexdigest(),),
                source_candidate_ids=(f"candidate-{index:02d}",),
                origins=(WaveOrigin.REAL_CYCLE,),
                generation_methods=(GenerationMethod.SOURCE_CYCLE,),
                roles=(WaveRole.STRUCTURAL,),
                exact_group=False,
                near_group=False,
                reason="Synthetic physical wave for V8-J allocation tests.",
            )
        )
    return PhysicalWaveSet(
        schema_version=1,
        waves=tuple(waves),
        reason="Synthetic physical wave set for V8-J tests.",
    )


@lru_cache(maxsize=1)
def complete_v8i_analysis():
    request, v8b, v8c, v8d, regions = v8h_context(requested_variants=1)
    return build_code_v8i(build_code_v8h(request, v8b, v8c, v8d, regions))


__all__ = [
    "samples_for_number",
    "empty_samples",
    "make_complete_dump",
    "make_partial_dump",
    "complete_source",
    "partial_source",
    "validated_empty_signature",
    "physical_set",
    "complete_v8i_analysis",
]
