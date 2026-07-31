from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from .codec import checksum, decode_14bit, encode_14bit
from .constants import (
    EXPECTED_PAYLOAD_LENGTHS,
    MAX_MIDI_DATA_BYTE,
    MICROWAVE_II_XT_EQUIPMENT_ID,
    SYSEX_END,
    SYSEX_START,
    WALDORF_MANUFACTURER_ID,
    DumpType,
)
from .errors import ChecksumError, FramingError, PayloadLengthError, ProtocolError


@dataclass(frozen=True, slots=True)
class SysExMessage:
    """One Waldorf Microwave II/XT dump message.

    Wire layout observed in the reference dumps::

        F0 3E 0E <device> <type> <addr_msb> <addr_lsb>
        <payload...> <sum(payload) & 7F> F7
    """

    device_id: int
    dump_type: DumpType | int
    address: int
    payload: bytes
    checksum_byte: int | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.device_id <= MAX_MIDI_DATA_BYTE:
            raise ProtocolError(f"Device ID out of range: {self.device_id}")
        if not 0 <= int(self.dump_type) <= MAX_MIDI_DATA_BYTE:
            raise ProtocolError(f"Dump type out of range: {int(self.dump_type)}")
        if not 0 <= self.address <= 0x3FFF:
            raise ProtocolError(f"Address out of 14-bit range: {self.address}")
        if any(byte > MAX_MIDI_DATA_BYTE for byte in self.payload):
            raise ProtocolError("Payload contains a byte above 0x7F")
        if self.checksum_byte is not None and not 0 <= self.checksum_byte <= MAX_MIDI_DATA_BYTE:
            raise ProtocolError(f"Checksum out of range: {self.checksum_byte}")

    @property
    def computed_checksum(self) -> int:
        return checksum(self.payload)

    @property
    def checksum_is_valid(self) -> bool:
        return self.checksum_byte is None or self.checksum_byte == self.computed_checksum

    @property
    def expected_payload_length(self) -> int | None:
        try:
            known_type = DumpType(int(self.dump_type))
        except ValueError:
            return None
        return EXPECTED_PAYLOAD_LENGTHS.get(known_type)

    def validate(self, *, strict_length: bool = True) -> tuple[str, ...]:
        issues: list[str] = []
        if not self.checksum_is_valid:
            issues.append(
                f"checksum mismatch: stored={self.checksum_byte:#04x}, "
                f"computed={self.computed_checksum:#04x}"
            )
        expected = self.expected_payload_length
        if strict_length and expected is not None and len(self.payload) != expected:
            issues.append(
                f"payload length mismatch for type {int(self.dump_type):#04x}: "
                f"got={len(self.payload)}, expected={expected}"
            )
        return tuple(issues)

    def assert_valid(self, *, strict_length: bool = True) -> None:
        issues = self.validate(strict_length=strict_length)
        if not issues:
            return
        if any("checksum" in issue for issue in issues):
            raise ChecksumError("; ".join(issues))
        raise PayloadLengthError("; ".join(issues))

    def to_bytes(self, *, recompute_checksum: bool = True) -> bytes:
        address_msb, address_lsb = encode_14bit(self.address)
        check = self.computed_checksum if recompute_checksum else self.checksum_byte
        if check is None:
            check = self.computed_checksum
        return bytes(
            (
                SYSEX_START,
                WALDORF_MANUFACTURER_ID,
                MICROWAVE_II_XT_EQUIPMENT_ID,
                self.device_id,
                int(self.dump_type),
                address_msb,
                address_lsb,
            )
        ) + self.payload + bytes((check, SYSEX_END))

    @classmethod
    def from_bytes(
        cls,
        data: bytes | bytearray | memoryview,
        *,
        validate_checksum: bool = True,
        strict_length: bool = True,
    ) -> Self:
        raw = bytes(data)
        if len(raw) < 9:
            raise FramingError(f"Message is too short: {len(raw)} bytes")
        if raw[0] != SYSEX_START or raw[-1] != SYSEX_END:
            raise FramingError("Message must start with F0 and end with F7")
        if raw[1] != WALDORF_MANUFACTURER_ID:
            raise ProtocolError(f"Unexpected manufacturer ID: {raw[1]:#04x}")
        if raw[2] != MICROWAVE_II_XT_EQUIPMENT_ID:
            raise ProtocolError(f"Unexpected equipment ID: {raw[2]:#04x}")
        if any(byte > MAX_MIDI_DATA_BYTE for byte in raw[1:-1]):
            raise ProtocolError("SysEx body contains a byte above 0x7F")

        raw_type = raw[4]
        try:
            dump_type: DumpType | int = DumpType(raw_type)
        except ValueError:
            dump_type = raw_type

        message = cls(
            device_id=raw[3],
            dump_type=dump_type,
            address=decode_14bit(raw[5], raw[6]),
            payload=raw[7:-2],
            checksum_byte=raw[-2],
        )
        if validate_checksum:
            message.assert_valid(strict_length=strict_length)
        elif strict_length:
            expected = message.expected_payload_length
            if expected is not None and len(message.payload) != expected:
                raise PayloadLengthError(
                    f"Payload length {len(message.payload)} != expected {expected}"
                )
        return message
