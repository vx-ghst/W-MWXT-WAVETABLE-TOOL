from __future__ import annotations

from dataclasses import replace

import pytest

from w_mwxt_wavetable_tool.allocation import UserWaveAllocation
from w_mwxt_wavetable_tool.constants import (
    INTERPOLATED_WAVE_REFERENCE,
    PATCH_NAME_LENGTH,
    PATCH_NAME_OFFSET,
    PATCH_WAVETABLE_OFFSET,
    DumpType,
)
from w_mwxt_wavetable_tool.destinations import (
    DeviceAddress,
    SoundDestination,
    UserWavetableDestination,
)
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.errors import PackageBuildError, SafetyError
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable
from w_mwxt_wavetable_tool.package import PackageRequest, build_package, plan_package
from w_mwxt_wavetable_tool.safety import MemoryTarget, MemoryTargetKind


def _samples(seed: int) -> tuple[int, ...]:
    return tuple(((seed * 17 + index * 5) % 256) - 128 for index in range(64))


def _request(
    *,
    wave_count: int = 3,
    start_number: int = 1100,
    device: DeviceAddress | None = None,
    sound_destination: SoundDestination | None = None,
    require_self_contained: bool = True,
    reserved_targets: tuple[MemoryTarget, ...] = (),
) -> PackageRequest:
    source_waves = tuple(
        UserWave(0, 1000 + index, _samples(index))
        for index in range(wave_count)
    )
    references = [INTERPOLATED_WAVE_REFERENCE] * 64
    for index, wave in enumerate(source_waves[:61]):
        references[index] = wave.number
    references[61:] = [0, 1, 2]
    source_wavetable = UserWavetable.from_display_number(0, 97, tuple(references))
    return PackageRequest(
        device=DeviceAddress(0) if device is None else device,
        source_waves=source_waves,
        allocation=UserWaveAllocation(start_number, wave_count),
        source_wavetable=source_wavetable,
        wavetable_destination=UserWavetableDestination(97),
        source_sound=SoundProgram(0, 0, 0, bytes(256)),
        sound_destination=(
            SoundDestination.parse("A001")
            if sound_destination is None
            else sound_destination
        ),
        sound_name="V2B TEST",
        reserved_targets=reserved_targets,
        require_self_contained=require_self_contained,
    )


def test_plan_lists_deterministic_order_and_mapping() -> None:
    plan = plan_package(_request())
    assert plan.wave_mapping == ((1000, 1100), (1001, 1101), (1002, 1102))
    assert plan.message_order == (
        "WAVD 1100",
        "WAVD 1101",
        "WAVD 1102",
        "WCTD 097",
        "SNDD A001",
    )
    assert plan.message_count == 5
    assert not plan.collision_report.has_collisions


def test_reserved_collision_blocks_build() -> None:
    reserved = (MemoryTarget(MemoryTargetKind.USER_WAVE, 1101),)
    request = _request(reserved_targets=reserved)
    with pytest.raises(SafetyError, match="User Wave 1101"):
        build_package(request)


def test_wave_count_must_match_allocation() -> None:
    request = _request()
    request = replace(request, allocation=UserWaveAllocation(1100, 4))
    with pytest.raises(PackageBuildError, match="Wave count mismatch"):
        plan_package(request)


def test_source_wave_numbers_must_be_unique() -> None:
    request = _request()
    duplicate = replace(request.source_waves[1], number=request.source_waves[0].number)
    request = replace(request, source_waves=(request.source_waves[0], duplicate, request.source_waves[2]))
    with pytest.raises(PackageBuildError, match="must be unique"):
        plan_package(request)


@pytest.mark.parametrize("name", ["", "../escape", "bad/name", "x" * 65])
def test_invalid_package_names_are_rejected(name: str) -> None:
    with pytest.raises(PackageBuildError, match="Package name"):
        replace(_request(), package_name=name)


def test_edit_buffer_can_be_planned_but_not_built() -> None:
    request = _request(sound_destination=SoundDestination.edit_buffer())
    plan = plan_package(request)
    assert "SNDD EDIT_BUFFER" == plan.message_order[-1]
    assert any("Edit Buffer" in warning for warning in plan.warnings)
    with pytest.raises(PackageBuildError, match="wire address"):
        build_package(request)


def test_build_order_counts_and_addresses() -> None:
    result = build_package(_request())
    assert len(result.dump.messages) == 5
    assert [int(message.dump_type) for message in result.dump.messages] == [
        int(DumpType.USER_WAVE),
        int(DumpType.USER_WAVE),
        int(DumpType.USER_WAVE),
        int(DumpType.USER_WAVETABLE),
        int(DumpType.SOUND),
    ]
    assert [message.address for message in result.dump.messages] == [1100, 1101, 1102, 96, 0]


def test_build_readdresses_device_and_user_waves() -> None:
    request = _request(device=DeviceAddress(12), start_number=1189)
    result = build_package(request)
    assert {message.device_id for message in result.dump.messages} == {12}
    assert [message.address for message in result.dump.messages[:3]] == [1189, 1190, 1191]


def test_wavetable_references_are_remapped_to_destinations() -> None:
    result = build_package(_request())
    table = UserWavetable.from_message(result.dump.messages[-2])
    assert table.references[:3] == (1100, 1101, 1102)
    assert table.references[3:61] == (INTERPOLATED_WAVE_REFERENCE,) * 58
    assert table.references[61:] == (0, 1, 2)


def test_sound_is_named_and_points_to_the_target_wavetable() -> None:
    result = build_package(_request())
    sound = SoundProgram.from_message(result.dump.messages[-1])
    assert sound.display_location == "A001"
    assert sound.name == "V2B TEST"
    assert sound.wavetable_parameter_raw == 96
    assert sound.data[PATCH_NAME_OFFSET : PATCH_NAME_OFFSET + PATCH_NAME_LENGTH] == b"V2B TEST        "
    assert sound.data[PATCH_WAVETABLE_OFFSET] == 96


def test_sound_destination_b128_uses_address_255() -> None:
    request = _request(sound_destination=SoundDestination.parse("B128"))
    result = build_package(request)
    assert result.dump.messages[-1].address == 255
    assert result.manifest.sound_destination == "B128"


def test_generated_package_validates_and_roundtrips() -> None:
    result = build_package(_request())
    assert result.dump.validate() == ()
    reparsed = DumpFile.from_bytes(result.package_bytes)
    assert reparsed.to_bytes() == result.package_bytes
    assert all(message.checksum_is_valid for message in reparsed.messages)


def test_unresolved_user_wave_reference_is_rejected_in_self_contained_mode() -> None:
    request = _request()
    references = list(request.source_wavetable.references)
    references[10] = 1249
    request = replace(
        request,
        source_wavetable=UserWavetable.from_display_number(0, 97, tuple(references)),
    )
    with pytest.raises(PackageBuildError, match="1249"):
        build_package(request)


def test_external_user_wave_reference_is_allowed_only_when_explicit() -> None:
    request = _request(require_self_contained=False)
    references = list(request.source_wavetable.references)
    references[10] = 1249
    request = replace(
        request,
        source_wavetable=UserWavetable.from_display_number(0, 97, tuple(references)),
    )
    result = build_package(request)
    table = UserWavetable.from_message(result.dump.messages[-2])
    assert table.references[10] == 1249
    assert any("Self-contained validation is disabled" in warning for warning in result.manifest.warnings)


def test_broadcast_package_requires_explicit_address_and_is_manifested() -> None:
    result = build_package(_request(device=DeviceAddress(127, allow_broadcast=True)))
    assert {message.device_id for message in result.dump.messages} == {127}
    assert result.manifest.broadcast is True
    assert any("broadcast" in warning.lower() for warning in result.manifest.warnings)


def test_source_objects_are_not_mutated() -> None:
    request = _request()
    before_waves = request.source_waves
    before_refs = request.source_wavetable.references
    before_sound = request.source_sound.data
    build_package(request)
    assert request.source_waves == before_waves
    assert request.source_wavetable.references == before_refs
    assert request.source_sound.data == before_sound


def test_source_sound_payload_length_is_checked() -> None:
    with pytest.raises(PackageBuildError, match="256 bytes"):
        replace(_request(), source_sound=SoundProgram(0, 0, 0, bytes(255)))
