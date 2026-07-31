from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.codec import (
    bytes_to_nibbles,
    decode_14bit,
    encode_14bit,
    nibbles_to_bytes,
    pack_u16_nibbles,
    unpack_u16_nibbles,
)
from w_mwxt_wavetable_tool.errors import ProtocolError


def test_14bit_codec_boundaries() -> None:
    for value in (0, 1, 127, 128, 1000, 1249, 16383):
        assert decode_14bit(*encode_14bit(value)) == value


def test_byte_nibble_roundtrip() -> None:
    source = bytes(range(256))
    assert nibbles_to_bytes(bytes_to_nibbles(source)) == source


def test_u16_nibble_roundtrip() -> None:
    source = (0, 29, 1000, 1249, 0xFFFF)
    assert unpack_u16_nibbles(pack_u16_nibbles(source)) == source


def test_invalid_nibble_is_rejected() -> None:
    with pytest.raises(ProtocolError):
        nibbles_to_bytes(bytes((0x10, 0x00)))
