from __future__ import annotations

from dataclasses import dataclass

from .errors import FramingError, ProtocolError


@dataclass(frozen=True, slots=True)
class IdentityReply:
    manufacturer_id: int
    family_code: int
    member_code: int
    version: str

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> "IdentityReply":
        raw = bytes(data)
        # Waldorf's documented/reported reply is the 14-byte shortened form:
        # F0 7E 06 02 3E <family lsb> <family msb> <member lsb> <member msb>
        # <4 ASCII version bytes> F7
        if len(raw) != 14 or raw[0] != 0xF0 or raw[-1] != 0xF7:
            raise FramingError("Expected a 14-byte Waldorf Universal Identity Reply")
        if raw[1:4] != bytes((0x7E, 0x06, 0x02)):
            raise ProtocolError(f"Unexpected identity header: {raw[1:4].hex(' ')}")
        if raw[4] != 0x3E:
            raise ProtocolError(f"Unexpected manufacturer: {raw[4]:#04x}")
        version = raw[9:13].decode("ascii", errors="strict")
        return cls(
            manufacturer_id=raw[4],
            family_code=raw[5] | (raw[6] << 8),
            member_code=raw[7] | (raw[8] << 8),
            version=version,
        )

    @property
    def is_xt_10_voice_non_expandable(self) -> bool:
        return self.family_code == 0x000E and self.member_code == 0x0003
