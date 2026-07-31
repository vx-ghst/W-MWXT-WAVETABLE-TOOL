from __future__ import annotations

from dataclasses import replace
import json

import pytest

from w_mwxt_wavetable_tool.allocation import UserWaveAllocation
from w_mwxt_wavetable_tool.constants import DumpType
from w_mwxt_wavetable_tool.destinations import (
    DeviceAddress,
    SoundDestination,
    UserWavetableDestination,
)
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.errors import HardwareValidationError
from w_mwxt_wavetable_tool.hardware_validation import (
    ComparisonStatus,
    HardwareValidationStatus,
    compare_hardware_readback,
    inspect_hardware_package,
    prepare_hardware_validation,
)
from w_mwxt_wavetable_tool.message import SysExMessage
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable
from w_mwxt_wavetable_tool.package import PackageRequest, build_package


def _samples(seed: int) -> tuple[int, ...]:
    return tuple(((seed * 37 + index * 11) % 256) - 128 for index in range(64))


def _package(
    *,
    wave_count: int = 61,
    destination_start: int = 1100,
    device_id: int = 0,
    reverse_table: bool = False,
    seed_offset: int = 0,
    sound_name: str = "V2C TEST",
) -> DumpFile:
    source_waves = tuple(
        UserWave(0, 1000 + index, _samples(seed_offset + index))
        for index in range(wave_count)
    )
    source_numbers = [wave.number for wave in source_waves]
    if reverse_table:
        source_numbers.reverse()
    references = source_numbers + [0xFFFF] * (61 - wave_count) + [0, 1, 2]
    request = PackageRequest(
        device=DeviceAddress(device_id),
        source_waves=source_waves,
        allocation=UserWaveAllocation(destination_start, wave_count),
        source_wavetable=UserWavetable.from_display_number(
            0, 97, tuple(references)
        ),
        wavetable_destination=UserWavetableDestination(97),
        source_sound=SoundProgram(0, 0, 0, bytes(256)),
        sound_destination=SoundDestination.parse("A001"),
        sound_name=sound_name,
        package_name="V2C_TEST",
    )
    return build_package(request).dump


def _replace_message(
    dump: DumpFile, index: int, message: SysExMessage
) -> DumpFile:
    messages = list(dump.messages)
    messages[index] = message
    return DumpFile(tuple(messages))


def test_acceptance_package_profile() -> None:
    profile = inspect_hardware_package(_package())
    assert profile.device_id == 0
    assert profile.wave_addresses == tuple(range(1100, 1161))
    assert profile.wave_range == "1100–1160"
    assert profile.wavetable_internal_number == 96
    assert profile.wavetable_display_number == 97
    assert profile.sound_location == "A001"
    assert profile.message_count == 63


def test_empty_package_is_rejected() -> None:
    with pytest.raises(HardwareValidationError, match="empty"):
        inspect_hardware_package(DumpFile(()))


def test_acceptance_shape_requires_61_waves() -> None:
    with pytest.raises(HardwareValidationError, match="61 USER_WAVE"):
        inspect_hardware_package(_package(wave_count=3))


def test_non_acceptance_shape_can_be_inspected_explicitly() -> None:
    profile = inspect_hardware_package(
        _package(wave_count=3), required_wave_count=None
    )
    assert len(profile.wave_addresses) == 3
    assert profile.message_count == 5


def test_broadcast_device_is_rejected_for_hardware_validation() -> None:
    dump = _package()
    broadcast = DumpFile(
        tuple(replace(message, device_id=127) for message in dump.messages)
    )
    with pytest.raises(HardwareValidationError, match="direct Device ID"):
        inspect_hardware_package(broadcast)


def test_message_order_is_strict() -> None:
    dump = _package()
    messages = list(dump.messages)
    messages[0], messages[-1] = messages[-1], messages[0]
    with pytest.raises(HardwareValidationError, match="order"):
        inspect_hardware_package(DumpFile(tuple(messages)))


def test_wave_addresses_must_be_consecutive() -> None:
    dump = _package()
    changed = replace(dump.messages[10], address=1200)
    with pytest.raises(HardwareValidationError, match="consecutive"):
        inspect_hardware_package(_replace_message(dump, 10, changed))


def test_unresolved_user_wave_reference_is_rejected() -> None:
    dump = _package()
    table = UserWavetable.from_message(dump.messages[-2])
    references = list(table.references)
    references[5] = 1249
    changed = replace(table, references=tuple(references)).to_message()
    with pytest.raises(HardwareValidationError, match="1249"):
        inspect_hardware_package(_replace_message(dump, -2, changed))


def test_sound_must_point_to_packaged_wavetable() -> None:
    dump = _package()
    sound = SoundProgram.from_message(dump.messages[-1])
    data = bytearray(sound.data)
    data[25] = 97
    changed = replace(sound, data=bytes(data)).to_message()
    with pytest.raises(HardwareValidationError, match="does not point"):
        inspect_hardware_package(_replace_message(dump, -1, changed))


def test_preflight_builds_exact_restore_bundle_and_is_ready() -> None:
    sent = _package(seed_offset=0, sound_name="SENT")
    baseline = _package(
        seed_offset=100,
        reverse_table=True,
        sound_name="BASELINE",
    )
    preparation = prepare_hardware_validation(sent, baseline)
    assert preparation.report.ready_for_transmission
    assert preparation.report.all_targets_exercised
    assert preparation.report.unchanged_payload_targets == ()
    assert len(preparation.restore_bundle.messages) == 63
    assert preparation.restore_bundle.to_bytes() == baseline.to_bytes()
    assert preparation.report.restore_bundle_sha256


def test_preflight_detects_unchanged_target_payload() -> None:
    sent = _package(seed_offset=0, sound_name="SENT")
    baseline = _package(
        seed_offset=100,
        reverse_table=True,
        sound_name="BASELINE",
    )
    baseline_messages = list(baseline.messages)
    baseline_messages[7] = sent.messages[7]
    preparation = prepare_hardware_validation(
        sent, DumpFile(tuple(baseline_messages))
    )
    assert not preparation.report.ready_for_transmission
    assert preparation.report.unchanged_payload_targets == ("User Wave 1107",)
    with pytest.raises(HardwareValidationError, match="1107"):
        preparation.report.assert_ready_for_transmission()


def test_preflight_rejects_missing_baseline_target() -> None:
    sent = _package()
    baseline = DumpFile(_package(seed_offset=100).messages[:-1])
    with pytest.raises(HardwareValidationError, match="Sound A001"):
        prepare_hardware_validation(sent, baseline)


def test_preflight_rejects_duplicate_baseline_target() -> None:
    sent = _package()
    baseline_messages = list(_package(seed_offset=100).messages)
    baseline_messages.append(baseline_messages[0])
    with pytest.raises(HardwareValidationError, match="2 copies"):
        prepare_hardware_validation(sent, DumpFile(tuple(baseline_messages)))


def test_preflight_reports_are_deterministic() -> None:
    preparation = prepare_hardware_validation(
        _package(sound_name="SENT"),
        _package(seed_offset=100, reverse_table=True, sound_name="BASE"),
    )
    assert preparation.report.to_json() == preparation.report.to_json()
    data = json.loads(preparation.report.to_json())
    assert data["ready_for_transmission"] is True
    assert data["message_count"] == 63
    assert len(data["targets"]) == 63
    markdown = preparation.report.to_markdown()
    assert "Status: **READY**" in markdown
    assert "Every destination payload changed: `yes`" in markdown


def test_preparation_write_creates_restore_and_reports(tmp_path) -> None:
    preparation = prepare_hardware_validation(
        _package(sound_name="SENT"),
        _package(seed_offset=100, reverse_table=True, sound_name="BASE"),
    )
    paths = preparation.write(tmp_path, stem="V2C_PREFLIGHT")
    assert paths.restore_bundle.read_bytes() == preparation.restore_bundle.to_bytes()
    assert paths.json_report.read_text(encoding="utf-8") == preparation.report.to_json()
    assert paths.markdown_report.read_text(encoding="utf-8") == preparation.report.to_markdown()


def test_preparation_write_rejects_unsafe_stem(tmp_path) -> None:
    preparation = prepare_hardware_validation(
        _package(sound_name="SENT"),
        _package(seed_offset=100, reverse_table=True, sound_name="BASE"),
    )
    with pytest.raises(HardwareValidationError, match="Output stem"):
        preparation.write(tmp_path, stem="../escape")


def test_exact_readback_inside_larger_dump_passes() -> None:
    expected = _package()
    extra = SysExMessage(0, DumpType.GLOBAL, 0, bytes(30))
    readback = DumpFile((extra,) + expected.messages)
    result = compare_hardware_readback(expected, readback)
    assert result.report.status is HardwareValidationStatus.PASS_EXACT
    assert result.report.exact_count == 63
    assert result.report.status_counts == {"exact": 63}
    assert result.extracted_targets.to_bytes() == expected.to_bytes()


def test_device_id_change_requires_review() -> None:
    expected = _package()
    observed = replace(expected.messages[0], device_id=1)
    readback = _replace_message(expected, 0, observed)
    result = compare_hardware_readback(expected, readback)
    assert result.report.status is HardwareValidationStatus.REVIEW_NORMALIZATION
    assert result.report.comparisons[0].status is ComparisonStatus.DEVICE_ID_CHANGED


def test_payload_change_fails_and_reports_offsets() -> None:
    expected = _package()
    first = expected.messages[0]
    payload = bytearray(first.payload)
    payload[3] = (payload[3] + 1) & 0x7F
    observed = replace(first, payload=bytes(payload), checksum_byte=None)
    readback = _replace_message(expected, 0, observed)
    result = compare_hardware_readback(expected, readback)
    comparison = result.report.comparisons[0]
    assert result.report.status is HardwareValidationStatus.FAIL
    assert comparison.status is ComparisonStatus.PAYLOAD_CHANGED
    assert comparison.differing_payload_offsets == (3,)


def test_missing_message_fails() -> None:
    expected = _package()
    readback = DumpFile(expected.messages[1:])
    result = compare_hardware_readback(expected, readback)
    assert result.report.status is HardwareValidationStatus.FAIL
    assert result.report.comparisons[0].status is ComparisonStatus.MISSING


def test_unique_address_relocation_requires_review() -> None:
    expected = _package()
    relocated = replace(expected.messages[0], address=1249)
    readback = DumpFile((relocated,) + expected.messages[1:])
    result = compare_hardware_readback(expected, readback)
    comparison = result.report.comparisons[0]
    assert result.report.status is HardwareValidationStatus.REVIEW_NORMALIZATION
    assert comparison.status is ComparisonStatus.ADDRESS_CHANGED
    assert comparison.observed_address == 1249


def test_ambiguous_relocation_fails() -> None:
    expected = _package()
    first = expected.messages[0]
    relocated_a = replace(first, address=1248)
    relocated_b = replace(first, address=1249)
    readback = DumpFile((relocated_a, relocated_b) + expected.messages[1:])
    result = compare_hardware_readback(expected, readback)
    assert result.report.status is HardwareValidationStatus.FAIL
    assert (
        result.report.comparisons[0].status
        is ComparisonStatus.AMBIGUOUS_RELOCATION
    )


def test_duplicate_expected_destination_fails() -> None:
    expected = _package()
    readback = DumpFile((expected.messages[0],) + expected.messages)
    result = compare_hardware_readback(expected, readback)
    assert result.report.status is HardwareValidationStatus.FAIL
    assert result.report.comparisons[0].status is ComparisonStatus.DUPLICATE


def test_readback_report_json_and_markdown() -> None:
    expected = _package()
    result = compare_hardware_readback(expected, expected)
    data = json.loads(result.report.to_json())
    assert data["hardware_validation_status"] == "pass_exact"
    assert data["exact_count"] == 63
    assert len(data["comparisons"]) == 63
    markdown = result.report.to_markdown()
    assert "Status: **pass_exact**" in markdown
    assert "| 1 | USER_WAVE | 1100 | User Wave 1100 | exact" in markdown


def test_readback_write_creates_reports_and_extracted_targets(tmp_path) -> None:
    expected = _package()
    result = compare_hardware_readback(expected, expected)
    paths = result.write(tmp_path, stem="V2C_READBACK")
    assert paths.json_report.read_text(encoding="utf-8") == result.report.to_json()
    assert paths.markdown_report.read_text(encoding="utf-8") == result.report.to_markdown()
    assert paths.extracted_targets.read_bytes() == expected.to_bytes()


def test_readback_write_rejects_unsafe_stem(tmp_path) -> None:
    result = compare_hardware_readback(_package(), _package())
    with pytest.raises(HardwareValidationError, match="Output stem"):
        result.write(tmp_path, stem="bad/name")


def test_restore_bundle_compare_can_disable_package_link_checks() -> None:
    expected = _package()
    table = UserWavetable.from_message(expected.messages[-2])
    references = list(table.references)
    references[0] = 1249
    table_message = replace(table, references=tuple(references)).to_message()
    sound = SoundProgram.from_message(expected.messages[-1])
    sound_data = bytearray(sound.data)
    sound_data[25] = 125
    sound_message = replace(sound, data=bytes(sound_data)).to_message()
    restore = DumpFile(expected.messages[:-2] + (table_message, sound_message))
    with pytest.raises(HardwareValidationError):
        compare_hardware_readback(restore, restore)
    result = compare_hardware_readback(
        restore,
        restore,
        require_package_links=False,
    )
    assert result.report.status is HardwareValidationStatus.PASS_EXACT
