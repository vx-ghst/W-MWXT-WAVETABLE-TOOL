from __future__ import annotations

from dataclasses import replace
import json

from w_mwxt_wavetable_tool.allocation import UserWaveAllocation
from w_mwxt_wavetable_tool.cli import main
from w_mwxt_wavetable_tool.destinations import (
    DeviceAddress,
    SoundDestination,
    UserWavetableDestination,
)
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable
from w_mwxt_wavetable_tool.package import PackageRequest, build_package


def _samples(seed: int) -> tuple[int, ...]:
    return tuple(((seed * 29 + index * 7) % 256) - 128 for index in range(64))


def _package(*, seed_offset: int = 0, reverse: bool = False, name: str = "V2C") -> DumpFile:
    waves = tuple(
        UserWave(0, 1000 + index, _samples(seed_offset + index))
        for index in range(61)
    )
    refs = [wave.number for wave in waves]
    if reverse:
        refs.reverse()
    refs.extend([0, 1, 2])
    request = PackageRequest(
        device=DeviceAddress(0),
        source_waves=waves,
        allocation=UserWaveAllocation(1100, 61),
        source_wavetable=UserWavetable.from_display_number(0, 97, tuple(refs)),
        wavetable_destination=UserWavetableDestination(97),
        source_sound=SoundProgram(0, 0, 0, bytes(256)),
        sound_destination=SoundDestination.parse("A001"),
        sound_name=name,
        package_name="V2C_CLI",
    )
    return build_package(request).dump


def test_hardware_preflight_cli_ready(tmp_path, capsys) -> None:
    sent_path = tmp_path / "sent.syx"
    baseline_path = tmp_path / "baseline.syx"
    output = tmp_path / "out"
    sent_path.write_bytes(_package(name="SENT").to_bytes())
    baseline_path.write_bytes(
        _package(seed_offset=100, reverse=True, name="BASE").to_bytes()
    )
    code = main(
        [
            "hardware-preflight",
            str(sent_path),
            str(baseline_path),
            "--output-dir",
            str(output),
            "--stem",
            "CLI_TEST",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "READY"
    assert data["message_count"] == 63
    assert (output / "CLI_TEST.restore.syx").exists()
    assert (output / "CLI_TEST.preflight.json").exists()
    assert (output / "CLI_TEST.preflight.md").exists()


def test_hardware_preflight_cli_blocked_for_unchanged_target(tmp_path, capsys) -> None:
    sent = _package(name="SENT")
    baseline = _package(seed_offset=100, reverse=True, name="BASE")
    messages = list(baseline.messages)
    messages[0] = sent.messages[0]
    sent_path = tmp_path / "sent.syx"
    baseline_path = tmp_path / "baseline.syx"
    sent_path.write_bytes(sent.to_bytes())
    baseline_path.write_bytes(DumpFile(tuple(messages)).to_bytes())
    code = main(
        [
            "hardware-preflight",
            str(sent_path),
            str(baseline_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == 2
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "BLOCKED"
    assert data["unchanged_payload_targets"] == ["User Wave 1100"]


def test_hardware_compare_cli_exact(tmp_path, capsys) -> None:
    expected = _package()
    expected_path = tmp_path / "expected.syx"
    readback_path = tmp_path / "readback.syx"
    expected_path.write_bytes(expected.to_bytes())
    readback_path.write_bytes(expected.to_bytes())
    code = main(
        [
            "hardware-compare",
            str(expected_path),
            str(readback_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--stem",
            "COMPARE",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "pass_exact"
    assert data["exact_count"] == 63


def test_hardware_compare_cli_returns_two_on_difference(tmp_path, capsys) -> None:
    expected = _package()
    messages = list(expected.messages)
    changed = messages[0]
    payload = bytearray(changed.payload)
    payload[0] = (payload[0] + 1) & 0x7F
    messages[0] = replace(changed, payload=bytes(payload), checksum_byte=None)
    expected_path = tmp_path / "expected.syx"
    readback_path = tmp_path / "readback.syx"
    expected_path.write_bytes(expected.to_bytes())
    readback_path.write_bytes(DumpFile(tuple(messages)).to_bytes())
    code = main(
        [
            "hardware-compare",
            str(expected_path),
            str(readback_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == 2
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "fail"
    assert data["status_counts"]["payload_changed"] == 1


def test_hardware_compare_cli_reports_parse_error(tmp_path, capsys) -> None:
    bad = tmp_path / "bad.syx"
    bad.write_bytes(b"not sysex")
    code = main(
        [
            "hardware-compare",
            str(bad),
            str(bad),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == 1
    assert "ERROR:" in capsys.readouterr().err


def _baseline_for_builder() -> DumpFile:
    messages = []
    for number in range(1000, 1161):
        messages.append(
            UserWave(0, number, _samples(number)).to_message()
        )
    messages.append(
        UserWavetable(
            0,
            125,
            tuple(range(1000, 1061)) + (0, 1, 2),
        ).to_message()
    )
    messages.append(
        UserWavetable(
            0,
            96,
            tuple(reversed(range(1100, 1161))) + (0, 1, 2),
        ).to_message()
    )
    source_data = bytearray(256)
    source_data[25] = 125
    source_data[240:256] = b"SOURCE SOUND    "
    target_data = bytearray(256)
    target_data[25] = 120
    target_data[240:256] = b"TARGET BEFORE   "
    messages.append(SoundProgram(0, 0, 14, bytes(source_data)).to_message())
    messages.append(SoundProgram(0, 0, 0, bytes(target_data)).to_message())
    return DumpFile(tuple(messages))


def test_hardware_build_test_cli_ready(tmp_path, capsys) -> None:
    baseline_path = tmp_path / "everything.syx"
    baseline_path.write_bytes(_baseline_for_builder().to_bytes())
    output = tmp_path / "out"
    code = main(
        [
            "hardware-build-test",
            str(baseline_path),
            "--source-wave-start",
            "1000",
            "--source-wavetable",
            "126",
            "--source-sound",
            "A015",
            "--target-wave-start",
            "1100",
            "--target-wavetable",
            "97",
            "--target-sound",
            "A001",
            "--output-dir",
            str(output),
            "--stem",
            "V2C_CLI_BUILD",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "READY"
    assert data["message_count"] == 63
    assert (output / "V2C_CLI_BUILD.syx").exists()
    assert (output / "V2C_CLI_BUILD.restore.syx").exists()


def test_hardware_compare_cli_restore_bundle_flag(tmp_path, capsys) -> None:
    expected = _package()
    table = UserWavetable.from_message(expected.messages[-2])
    refs = list(table.references)
    refs[0] = 1249
    table_message = replace(table, references=tuple(refs)).to_message()
    sound = SoundProgram.from_message(expected.messages[-1])
    sound_data = bytearray(sound.data)
    sound_data[25] = 125
    sound_message = replace(sound, data=bytes(sound_data)).to_message()
    restore = DumpFile(expected.messages[:-2] + (table_message, sound_message))
    expected_path = tmp_path / "restore.syx"
    readback_path = tmp_path / "readback.syx"
    expected_path.write_bytes(restore.to_bytes())
    readback_path.write_bytes(restore.to_bytes())
    code = main(
        [
            "hardware-compare",
            str(expected_path),
            str(readback_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--restore-bundle",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "pass_exact"
