from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.codec import (
    decode_offset_binary_i8,
    encode_offset_binary_i8,
    nibbles_to_bytes,
)
from w_mwxt_wavetable_tool.errors import ProtocolError
from w_mwxt_wavetable_tool.message import SysExMessage
from w_mwxt_wavetable_tool.models import UserWave


def test_offset_binary_golden_vectors() -> None:
    raw = (0x00, 0x01, 0x7F, 0x80, 0x81, 0xFE, 0xFF)
    signed = (-128, -127, -1, 0, 1, 126, 127)
    assert tuple(decode_offset_binary_i8(value) for value in raw) == signed
    assert tuple(encode_offset_binary_i8(value) for value in signed) == raw


def test_offset_binary_rejects_out_of_range_values() -> None:
    with pytest.raises(ProtocolError):
        decode_offset_binary_i8(256)
    with pytest.raises(ProtocolError):
        encode_offset_binary_i8(128)


def test_user_wave_payload_uses_offset_binary_before_nibble_encoding() -> None:
    anchors = (-128, -127, -1, 0, 1, 126, 127)
    samples = anchors + (0,) * (64 - len(anchors))
    wave = UserWave(0, 1000, samples)
    raw = nibbles_to_bytes(wave.payload)
    assert raw[:7] == bytes((0x00, 0x01, 0x7F, 0x80, 0x81, 0xFE, 0xFF))


def test_user_wave_offset_binary_roundtrip_is_logically_exact() -> None:
    samples = tuple(((index * 41 + 9) % 256) - 128 for index in range(64))
    wave = UserWave(0, 1000, samples)
    encoded = wave.to_message().to_bytes()
    decoded = UserWave.from_message(SysExMessage.from_bytes(encoded))
    assert decoded == wave
    assert decoded.to_message().to_bytes() == encoded


def test_documented_reconstruction_and_negative_full_scale_policies() -> None:
    samples = tuple([-128] + list(range(-31, 32)))
    wave = UserWave(0, 1000, samples)

    mathematical = wave.reconstruct("documented")
    wrapped = wave.reconstruct("wrap_i8")
    saturated = wave.reconstruct("saturate_i8")

    assert mathematical[:64] == samples
    assert mathematical[64:] == tuple(-value for value in reversed(samples))
    assert mathematical[-1] == 128
    assert wrapped[-1] == -128
    assert saturated[-1] == 127
    assert wave.has_negative_full_scale is True
