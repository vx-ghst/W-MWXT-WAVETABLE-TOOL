from __future__ import annotations

from dataclasses import replace

import pytest

from w_mwxt_wavetable_tool.constants import DumpType
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.errors import HardwareValidationError
from w_mwxt_wavetable_tool.hardware_test import build_hardware_test_from_backup
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable


def _samples(seed: int) -> tuple[int, ...]:
    return tuple(((seed * 43 + index * 13) % 256) - 128 for index in range(64))


def _baseline() -> DumpFile:
    messages = []
    for number in range(1000, 1161):
        messages.append(UserWave(0, number, _samples(number)).to_message())

    source_refs = tuple(range(1000, 1061)) + (0, 1, 2)
    target_refs = tuple(reversed(range(1100, 1161))) + (0, 1, 2)
    messages.append(UserWavetable(0, 125, source_refs).to_message())
    messages.append(UserWavetable(0, 96, target_refs).to_message())

    source_data = bytearray(256)
    source_data[25] = 125
    source_data[240:256] = b"SOURCE SOUND    "
    target_data = bytearray(256)
    target_data[25] = 120
    target_data[240:256] = b"TARGET BEFORE   "
    messages.append(SoundProgram(0, 0, 14, bytes(source_data)).to_message())
    messages.append(SoundProgram(0, 0, 0, bytes(target_data)).to_message())
    return DumpFile(tuple(messages))


def test_build_hardware_test_from_backup_creates_acceptance_package() -> None:
    build = build_hardware_test_from_backup(
        _baseline(),
        source_wave_start=1000,
        source_wavetable_display=126,
        source_sound="A015",
        target_wave_start=1100,
        target_wavetable_display=97,
        target_sound="A001",
        sound_name="V2C READBACK",
    )
    assert len(build.package_result.dump.messages) == 63
    assert build.preparation.report.profile.wave_range == "1100–1160"
    assert build.preparation.report.profile.wavetable_display_number == 97
    assert build.preparation.report.profile.sound_location == "A001"
    assert build.ready_for_transmission

    table = UserWavetable.from_message(build.package_result.dump.messages[-2])
    assert table.references[:61] == tuple(range(1100, 1161))
    assert table.references[61:] == (0, 1, 2)

    sound = SoundProgram.from_message(build.package_result.dump.messages[-1])
    assert sound.display_location == "A001"
    assert sound.name == "V2C READBACK"
    assert sound.wavetable_parameter_raw == 96


def test_build_uses_baseline_device_id() -> None:
    baseline = DumpFile(
        tuple(replace(message, device_id=12) for message in _baseline().messages)
    )
    build = build_hardware_test_from_backup(
        baseline,
        source_wave_start=1000,
        source_wavetable_display=126,
        source_sound="A015",
        target_wave_start=1100,
        target_wavetable_display=97,
        target_sound="A001",
    )
    assert {message.device_id for message in build.package_result.dump.messages} == {12}
    assert {message.device_id for message in build.preparation.restore_bundle.messages} == {12}


def test_build_rejects_overlapping_source_and_target_wave_ranges() -> None:
    with pytest.raises(HardwareValidationError, match="must not overlap"):
        build_hardware_test_from_backup(
            _baseline(),
            source_wave_start=1000,
            source_wavetable_display=126,
            source_sound="A015",
            target_wave_start=1000,
            target_wavetable_display=97,
            target_sound="A001",
        )


def test_build_marks_identical_target_wave_payloads_and_remains_ready() -> None:
    baseline = _baseline()
    messages = list(baseline.messages)
    source_wave = next(
        message
        for message in messages
        if int(message.dump_type) == int(DumpType.USER_WAVE)
        and message.address == 1000
    )
    target_index = next(
        index
        for index, message in enumerate(messages)
        if int(message.dump_type) == int(DumpType.USER_WAVE)
        and message.address == 1100
    )
    messages[target_index] = replace(source_wave, address=1100)
    build = build_hardware_test_from_backup(
        DumpFile(tuple(messages)),
        source_wave_start=1000,
        source_wavetable_display=126,
        source_sound="A015",
        target_wave_start=1100,
        target_wavetable_display=97,
        target_sound="A001",
    )
    assert build.ready_for_transmission
    assert any("User Wave 1100" in item for item in build.adjustments)
    assert any(
        "Hardware test marker: User Wave 1100" in warning
        for warning in build.package_result.manifest.warnings
    )
    assert build.preparation.report.unchanged_payload_targets == ()


def test_build_rejects_source_range_after_1189() -> None:
    with pytest.raises(HardwareValidationError, match="61 consecutive"):
        build_hardware_test_from_backup(
            _baseline(),
            source_wave_start=1190,
            source_wavetable_display=126,
            source_sound="A015",
            target_wave_start=1100,
            target_wavetable_display=97,
            target_sound="A001",
        )


def test_build_rejects_missing_source_message() -> None:
    baseline = DumpFile(
        tuple(
            message
            for message in _baseline().messages
            if not (
                int(message.dump_type) == int(DumpType.USER_WAVE)
                and message.address == 1030
            )
        )
    )
    with pytest.raises(HardwareValidationError, match="1030"):
        build_hardware_test_from_backup(
            baseline,
            source_wave_start=1000,
            source_wavetable_display=126,
            source_sound="A015",
            target_wave_start=1100,
            target_wavetable_display=97,
            target_sound="A001",
        )


def test_build_rejects_edit_buffer_source_or_target() -> None:
    with pytest.raises(HardwareValidationError, match="source_sound"):
        build_hardware_test_from_backup(
            _baseline(),
            source_wave_start=1000,
            source_wavetable_display=126,
            source_sound="EDIT_BUFFER",
            target_wave_start=1100,
            target_wavetable_display=97,
            target_sound="A001",
        )
    with pytest.raises(HardwareValidationError, match="target_sound"):
        build_hardware_test_from_backup(
            _baseline(),
            source_wave_start=1000,
            source_wavetable_display=126,
            source_sound="A015",
            target_wave_start=1100,
            target_wavetable_display=97,
            target_sound="EDIT_BUFFER",
        )


def test_build_write_creates_package_restore_and_reports(tmp_path) -> None:
    build = build_hardware_test_from_backup(
        _baseline(),
        source_wave_start=1000,
        source_wavetable_display=126,
        source_sound="A015",
        target_wave_start=1100,
        target_wavetable_display=97,
        target_sound="A001",
    )
    paths = build.write(tmp_path, stem="V2C_BUILD")
    assert paths.package.sysex.exists()
    assert paths.package.json_manifest.exists()
    assert paths.package.markdown_manifest.exists()
    assert paths.preflight.restore_bundle.exists()
    assert paths.preflight.json_report.exists()
    assert paths.preflight.markdown_report.exists()
