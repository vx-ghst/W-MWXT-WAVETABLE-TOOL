from __future__ import annotations

from hashlib import sha256

from w_mwxt_wavetable_tool.allocation import UserWaveAllocation
from w_mwxt_wavetable_tool.constants import DumpType
from w_mwxt_wavetable_tool.destinations import DeviceAddress, SoundDestination, UserWavetableDestination
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable
from w_mwxt_wavetable_tool.package import PackageRequest, build_package


def _golden_request() -> PackageRequest:
    waves = tuple(
        UserWave(
            0,
            1000 + wave_index,
            tuple(((wave_index * 19 + sample_index * 7) % 256) - 128 for sample_index in range(64)),
        )
        for wave_index in range(61)
    )
    references = tuple(range(1000, 1061)) + (0, 1, 2)
    return PackageRequest(
        device=DeviceAddress(0),
        source_waves=waves,
        allocation=UserWaveAllocation.complete_table(1100),
        source_wavetable=UserWavetable.from_display_number(0, 97, references),
        wavetable_destination=UserWavetableDestination(97),
        source_sound=SoundProgram(0, 0, 0, bytes(256)),
        sound_destination=SoundDestination.parse("A001"),
        sound_name="CODE V2 GOLDEN",
        package_name="CODE_V2_GOLDEN",
    )


def test_complete_golden_package_shape_and_hash() -> None:
    result = build_package(_golden_request())
    assert len(result.dump.messages) == 63
    assert result.dump.type_counts == {
        "SOUND": 1,
        "USER_WAVE": 61,
        "USER_WAVETABLE": 1,
    }
    assert len(result.package_bytes) == 8887
    assert sha256(result.package_bytes).hexdigest() == "e9a6294b78ef41ec85db24850270dfe85228f3a2ea622e33a70bd6df04858caa"


def test_complete_golden_package_is_deterministic() -> None:
    first = build_package(_golden_request())
    second = build_package(_golden_request())
    assert first.package_bytes == second.package_bytes
    assert first.manifest.to_json() == second.manifest.to_json()
    assert first.manifest.to_markdown() == second.manifest.to_markdown()


def test_complete_golden_package_roundtrips() -> None:
    result = build_package(_golden_request())
    reparsed = DumpFile.from_bytes(result.package_bytes)
    assert reparsed.to_bytes() == result.package_bytes
    assert [message.address for message in reparsed.messages[:61]] == list(range(1100, 1161))
    assert reparsed.messages[61].address == 96
    assert reparsed.messages[62].address == 0
    assert int(reparsed.messages[61].dump_type) == int(DumpType.USER_WAVETABLE)
    assert int(reparsed.messages[62].dump_type) == int(DumpType.SOUND)
