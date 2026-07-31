from __future__ import annotations

import json

import pytest

from w_mwxt_wavetable_tool.constants import INTERPOLATED_WAVE_REFERENCE
from w_mwxt_wavetable_tool.destinations import DeviceAddress, SoundDestination, UserWavetableDestination
from w_mwxt_wavetable_tool.allocation import UserWaveAllocation
from w_mwxt_wavetable_tool.errors import PackageBuildError
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable
from w_mwxt_wavetable_tool.package import PackageRequest, build_package


def _result():
    waves = tuple(
        UserWave(0, 1000 + index, tuple(((index + sample) % 64) - 32 for sample in range(64)))
        for index in range(2)
    )
    refs = [INTERPOLATED_WAVE_REFERENCE] * 64
    refs[0] = 1000
    refs[60] = 1001
    refs[61:] = [0, 1, 2]
    request = PackageRequest(
        device=DeviceAddress(0),
        source_waves=waves,
        allocation=UserWaveAllocation(1200, 2),
        source_wavetable=UserWavetable.from_display_number(0, 128, tuple(refs)),
        wavetable_destination=UserWavetableDestination(128),
        source_sound=SoundProgram(0, 0, 0, bytes(256)),
        sound_destination=SoundDestination.parse("B128"),
        sound_name="MANIFEST",
        package_name="MANIFEST_TEST",
    )
    return build_package(request)


def test_json_manifest_is_deterministic_and_complete() -> None:
    result = _result()
    first = result.manifest.to_json()
    second = result.manifest.to_json()
    assert first == second
    data = json.loads(first)
    assert data["schema_version"] == 1
    assert data["package_name"] == "MANIFEST_TEST"
    assert data["package_sha256"] == result.sha256
    assert data["message_count"] == 4
    assert data["user_wave_range"] == "1200–1201"
    assert data["wavetable_display_number"] == 128
    assert data["wavetable_internal_number"] == 127
    assert data["sound_destination"] == "B128"
    assert len(data["messages"]) == 4


def test_markdown_manifest_contains_ordered_evidence() -> None:
    markdown = _result().manifest.to_markdown()
    assert "# MANIFEST_TEST" in markdown
    assert "## Overwrite targets" in markdown
    assert "User Wave 1200" in markdown
    assert "User Wavetable 128" in markdown
    assert "Sound B128" in markdown
    assert "## Ordered messages" in markdown
    assert "USER_WAVE" in markdown
    assert "USER_WAVETABLE" in markdown
    assert "SOUND" in markdown
    assert "Read-back required: `yes`" in markdown


def test_manifest_message_lengths_match_wire_messages() -> None:
    result = _result()
    expected = tuple(len(message.to_bytes()) for message in result.dump.messages)
    actual = tuple(message.byte_length for message in result.manifest.messages)
    assert actual == expected
    assert actual == (137, 137, 265, 265)


def test_write_creates_sysex_and_both_manifests(tmp_path) -> None:
    result = _result()
    paths = result.write(tmp_path)
    assert paths.sysex.read_bytes() == result.package_bytes
    assert paths.json_manifest.read_text(encoding="utf-8") == result.manifest.to_json()
    assert paths.markdown_manifest.read_text(encoding="utf-8") == result.manifest.to_markdown()


def test_write_rejects_unsafe_output_stem(tmp_path) -> None:
    with pytest.raises(PackageBuildError, match="Output stem"):
        _result().write(tmp_path, stem="../escape")
