from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.constants import DumpType
from w_mwxt_wavetable_tool.errors import ChecksumError, FramingError
from w_mwxt_wavetable_tool.message import SysExMessage


def test_synthetic_message_roundtrip() -> None:
    message = SysExMessage(
        device_id=0,
        dump_type=DumpType.GLOBAL,
        address=0,
        payload=bytes(range(30)),
    )
    encoded = message.to_bytes()
    decoded = SysExMessage.from_bytes(encoded)
    assert decoded.to_bytes() == encoded


def test_checksum_is_payload_sum_modulo_128() -> None:
    payload = bytes((0x7F, 0x7F, 0x02))
    message = SysExMessage(0, DumpType.GLOBAL, 0, payload)
    assert message.computed_checksum == 0


def test_corrupt_checksum_is_rejected() -> None:
    message = SysExMessage(0, DumpType.GLOBAL, 0, bytes(range(30)))
    encoded = bytearray(message.to_bytes())
    encoded[-2] ^= 1
    with pytest.raises(ChecksumError):
        SysExMessage.from_bytes(encoded)


def test_bad_framing_is_rejected() -> None:
    with pytest.raises(FramingError):
        SysExMessage.from_bytes(bytes((0x00,) * 20))
