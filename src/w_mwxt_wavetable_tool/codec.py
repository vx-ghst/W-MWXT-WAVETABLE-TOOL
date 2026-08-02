from __future__ import annotations

from collections.abc import Iterable, Sequence

from .constants import MAX_MIDI_DATA_BYTE
from .errors import ProtocolError


def encode_14bit(value: int) -> tuple[int, int]:
    """Encode an integer from 0 to 16383 as two 7-bit MIDI bytes."""
    if not 0 <= value <= 0x3FFF:
        raise ProtocolError(f"14-bit value out of range: {value}")
    return (value >> 7) & 0x7F, value & 0x7F


def decode_14bit(msb: int, lsb: int) -> int:
    """Decode two 7-bit MIDI bytes into an integer."""
    _require_midi_byte(msb, "14-bit MSB")
    _require_midi_byte(lsb, "14-bit LSB")
    return (msb << 7) | lsb


def checksum(payload: bytes | bytearray | memoryview | Sequence[int]) -> int:
    """Microwave II/XT dump checksum: sum of payload bytes modulo 128."""
    return sum(payload) & 0x7F


def bytes_to_nibbles(data: bytes | bytearray | memoryview | Iterable[int]) -> bytes:
    """Encode arbitrary 8-bit bytes as high-nibble/low-nibble MIDI bytes."""
    out = bytearray()
    for value in data:
        if not 0 <= int(value) <= 0xFF:
            raise ProtocolError(f"8-bit value out of range: {value}")
        out.extend(((int(value) >> 4) & 0x0F, int(value) & 0x0F))
    return bytes(out)


def nibbles_to_bytes(
    nibbles: bytes | bytearray | memoryview | Sequence[int],
) -> bytes:
    """Decode high-nibble/low-nibble MIDI bytes into 8-bit bytes."""
    if len(nibbles) % 2:
        raise ProtocolError("Nibble payload length must be even")
    out = bytearray()
    for index in range(0, len(nibbles), 2):
        high = int(nibbles[index])
        low = int(nibbles[index + 1])
        if not 0 <= high <= 0x0F or not 0 <= low <= 0x0F:
            raise ProtocolError(
                f"Invalid nibble pair at {index}: high={high:#x}, low={low:#x}"
            )
        out.append((high << 4) | low)
    return bytes(out)


def signed_i8(value: int) -> int:
    """Interpret an unsigned byte as signed two's-complement int8."""
    if not 0 <= value <= 0xFF:
        raise ProtocolError(f"8-bit value out of range: {value}")
    return value - 0x100 if value >= 0x80 else value


def unsigned_i8(value: int) -> int:
    """Encode a signed int8 value as an unsigned two's-complement byte."""
    if not -128 <= value <= 127:
        raise ProtocolError(f"Signed int8 out of range: {value}")
    return value & 0xFF


def decode_offset_binary_i8(value: int) -> int:
    """Decode one Waldorf User Wave sample from 8-bit offset binary.

    The Microwave II/XT SysEx specification states that User Wave samples are
    not transmitted in two's-complement form. Flipping the most-significant bit
    yields the conventional signed int8 representation.
    """
    if not 0 <= value <= 0xFF:
        raise ProtocolError(f"8-bit offset-binary value out of range: {value}")
    return signed_i8(value ^ 0x80)


def encode_offset_binary_i8(value: int) -> int:
    """Encode one signed int8 sample as Waldorf User Wave offset binary."""
    return unsigned_i8(value) ^ 0x80


def pack_u16_nibbles(values: Sequence[int]) -> bytes:
    """Encode 16-bit values as four high-to-low nibbles each."""
    out = bytearray()
    for value in values:
        if not 0 <= value <= 0xFFFF:
            raise ProtocolError(f"16-bit value out of range: {value}")
        out.extend(
            (
                (value >> 12) & 0x0F,
                (value >> 8) & 0x0F,
                (value >> 4) & 0x0F,
                value & 0x0F,
            )
        )
    return bytes(out)


def unpack_u16_nibbles(
    data: bytes | bytearray | memoryview | Sequence[int],
) -> tuple[int, ...]:
    """Decode groups of four nibbles into 16-bit values."""
    if len(data) % 4:
        raise ProtocolError("16-bit nibble payload length must be divisible by four")
    values: list[int] = []
    for index in range(0, len(data), 4):
        chunk = [int(x) for x in data[index : index + 4]]
        if any(not 0 <= x <= 0x0F for x in chunk):
            raise ProtocolError(f"Invalid 16-bit nibble group at byte {index}: {chunk}")
        values.append(
            (chunk[0] << 12) | (chunk[1] << 8) | (chunk[2] << 4) | chunk[3]
        )
    return tuple(values)


def _require_midi_byte(value: int, label: str) -> None:
    if not 0 <= value <= MAX_MIDI_DATA_BYTE:
        raise ProtocolError(f"{label} is not a 7-bit MIDI byte: {value:#x}")
