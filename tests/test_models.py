from __future__ import annotations

from w_mwxt_wavetable_tool.constants import INTERPOLATED_WAVE_REFERENCE, DumpType
from w_mwxt_wavetable_tool.message import SysExMessage
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable


def test_user_wave_roundtrip_and_reconstruction() -> None:
    samples = tuple(range(64))
    wave = UserWave(device_id=0, number=1000, stored_samples=samples)
    message = wave.to_message()
    assert message.dump_type == DumpType.USER_WAVE
    decoded = UserWave.from_message(SysExMessage.from_bytes(message.to_bytes()))
    assert decoded == wave
    reconstructed = wave.reconstruct()
    assert reconstructed[:64] == samples
    assert reconstructed[64:] == tuple(-x for x in reversed(samples))


def test_user_wavetable_roundtrip() -> None:
    refs = [INTERPOLATED_WAVE_REFERENCE] * 64
    refs[0] = 1000
    refs[60] = 1060
    refs[61:] = [0, 0, 0]
    table = UserWavetable.from_display_number(0, 97, tuple(refs))
    decoded = UserWavetable.from_message(SysExMessage.from_bytes(table.to_message().to_bytes()))
    assert decoded == table
    assert decoded.display_number == 97
    assert decoded.explicit_positions == (0, 60, 61, 62, 63)


def test_sound_name_field() -> None:
    program = SoundProgram(0, 0, 0, bytes(256)).with_name("TEST PATCH")
    decoded = SoundProgram.from_message(SysExMessage.from_bytes(program.to_message().to_bytes()))
    assert decoded.name == "TEST PATCH"
    assert decoded.display_location == "A001"
