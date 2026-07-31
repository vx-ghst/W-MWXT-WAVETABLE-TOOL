from __future__ import annotations

from collections import Counter
from hashlib import sha256

from w_mwxt_wavetable_tool.constants import DumpType
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable


EXPECTED = {
    "WALDORF_MWXT_ALL_SOUNDS.syx": {
        "bytes": 67840,
        "sha256": "5a0996e68b183e9ca3afc5e2f0996945bd13493ba987f5d9af2d13673dd17451",
        "counts": {DumpType.SOUND: 256},
    },
    "WALDORF_MWXT_ALL_WAVETABLES_AND_WAVES.syx": {
        "bytes": 42730,
        "sha256": "19e24c0c58a45eeb22e80268e156d4baa594debc2aed3a17bb17150ea6878808",
        "counts": {DumpType.USER_WAVE: 250, DumpType.USER_WAVETABLE: 32},
    },
    "WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22.syx": {
        "bytes": 144529,
        "sha256": "4488e5fcb1a1991f429ff76044ea5f3bcba3061c3cc11ba60401f626d3510244",
        "counts": {
            DumpType.SOUND: 256,
            DumpType.MULTI: 128,
            DumpType.USER_WAVE: 250,
            DumpType.USER_WAVETABLE: 32,
            DumpType.GLOBAL: 1,
        },
    },
    "WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22_B.syx": {
        "bytes": 144529,
        "sha256": "4488e5fcb1a1991f429ff76044ea5f3bcba3061c3cc11ba60401f626d3510244",
        "counts": {
            DumpType.SOUND: 256,
            DumpType.MULTI: 128,
            DumpType.USER_WAVE: 250,
            DumpType.USER_WAVETABLE: 32,
            DumpType.GLOBAL: 1,
        },
    },
}


def test_all_four_real_dumps_validate_and_roundtrip(dump_paths) -> None:
    for filename, path in dump_paths.items():
        raw = path.read_bytes()
        dump = DumpFile.from_bytes(raw)
        expected = EXPECTED[filename]
        assert len(raw) == expected["bytes"]
        assert sha256(raw).hexdigest() == expected["sha256"]
        assert dump.to_bytes() == raw
        assert dump.validate() == ()
        assert set(dump.device_ids) == {0}
        assert Counter(message.dump_type for message in dump) == Counter(expected["counts"])


def test_reference_backups_are_byte_identical(dump_paths) -> None:
    first = dump_paths["WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22.syx"].read_bytes()
    second = dump_paths["WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22_B.syx"].read_bytes()
    assert first == second


def test_sound_addresses_and_names(dump_paths) -> None:
    dump = DumpFile.from_path(dump_paths["WALDORF_MWXT_ALL_SOUNDS.syx"])
    programs = [SoundProgram.from_message(message) for message in dump]
    assert programs[0].display_location == "A001"
    assert programs[-1].display_location == "B128"
    assert programs[0].name == "Cobalt  Blue"
    assert len(programs) == 256


def test_real_user_wave_and_wavetable_ranges(dump_paths) -> None:
    dump = DumpFile.from_path(
        dump_paths["WALDORF_MWXT_ALL_WAVETABLES_AND_WAVES.syx"]
    )
    waves = [
        UserWave.from_message(message)
        for message in dump
        if message.dump_type == DumpType.USER_WAVE
    ]
    tables = [
        UserWavetable.from_message(message)
        for message in dump
        if message.dump_type == DumpType.USER_WAVETABLE
    ]
    assert [wave.number for wave in waves] == list(range(1000, 1250))
    assert [table.internal_number for table in tables] == list(range(96, 128))
    assert [table.display_number for table in tables] == list(range(97, 129))
    assert all(UserWave.from_message(wave.to_message()) == wave for wave in waves)
    assert all(UserWavetable.from_message(table.to_message()) == table for table in tables)
