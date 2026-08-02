from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from .codec import (
    bytes_to_nibbles,
    decode_offset_binary_i8,
    encode_offset_binary_i8,
    nibbles_to_bytes,
    pack_u16_nibbles,
    signed_i8,
    unpack_u16_nibbles,
)
from .constants import (
    INTERPOLATED_WAVE_REFERENCE,
    PATCH_NAME_LENGTH,
    PATCH_NAME_OFFSET,
    PATCH_WAVETABLE_OFFSET,
    USER_WAVE_FIRST,
    USER_WAVE_LAST,
    USER_WAVETABLE_DISPLAY_FIRST,
    USER_WAVETABLE_DISPLAY_LAST,
    USER_WAVETABLE_INTERNAL_FIRST,
    USER_WAVETABLE_INTERNAL_LAST,
    DumpType,
)
from .errors import PayloadLengthError, ProtocolError
from .message import SysExMessage


@dataclass(frozen=True, slots=True)
class SoundProgram:
    device_id: int
    bank: int
    slot: int
    data: bytes

    @classmethod
    def from_message(cls, message: SysExMessage) -> "SoundProgram":
        _require_type(message, DumpType.SOUND)
        _require_payload_length(message, 256)
        return cls(
            device_id=message.device_id,
            bank=message.address >> 7,
            slot=message.address & 0x7F,
            data=message.payload,
        )

    @property
    def display_location(self) -> str:
        bank_name = (
            chr(ord("A") + self.bank) if 0 <= self.bank <= 25 else f"B{self.bank}"
        )
        return f"{bank_name}{self.slot + 1:03d}"

    @property
    def name_bytes(self) -> bytes:
        return self.data[PATCH_NAME_OFFSET : PATCH_NAME_OFFSET + PATCH_NAME_LENGTH]

    @property
    def name(self) -> str:
        return self.name_bytes.decode("ascii", errors="replace").rstrip(" \x00")

    @property
    def wavetable_parameter_raw(self) -> int:
        return self.data[PATCH_WAVETABLE_OFFSET]

    def with_name(self, name: str) -> "SoundProgram":
        encoded = name.encode("ascii", errors="replace")[:PATCH_NAME_LENGTH]
        encoded = encoded.ljust(PATCH_NAME_LENGTH, b" ")
        data = bytearray(self.data)
        data[PATCH_NAME_OFFSET : PATCH_NAME_OFFSET + PATCH_NAME_LENGTH] = encoded
        return replace(self, data=bytes(data))

    def to_message(self) -> SysExMessage:
        if not 0 <= self.bank <= 0x7F or not 0 <= self.slot <= 0x7F:
            raise ProtocolError(
                f"Invalid sound location: bank={self.bank}, slot={self.slot}"
            )
        return SysExMessage(
            device_id=self.device_id,
            dump_type=DumpType.SOUND,
            address=(self.bank << 7) | self.slot,
            payload=self.data,
        )


@dataclass(frozen=True, slots=True)
class MultiProgram:
    device_id: int
    slot: int
    data: bytes

    @classmethod
    def from_message(cls, message: SysExMessage) -> "MultiProgram":
        _require_type(message, DumpType.MULTI)
        _require_payload_length(message, 256)
        return cls(message.device_id, message.address, message.payload)

    def to_message(self) -> SysExMessage:
        return SysExMessage(self.device_id, DumpType.MULTI, self.slot, self.data)


@dataclass(frozen=True, slots=True)
class UserWave:
    """One Microwave II/XT User Wave as 64 stored signed 8-bit samples.

    WAVD transports 128 MIDI-safe nibbles, representing 64 independent sample
    bytes. Those bytes use offset-binary coding: the most-significant bit must
    be flipped before interpreting the value as signed int8.

    The documented logical cycle contains 128 points. Its second half is the
    sign-inverted reverse of the stored half. Negating -128 produces +128,
    which is intentionally preserved by the ``documented``/``mathematical``
    policies until the XT's negative-full-scale edge behavior is measured.
    """

    device_id: int
    number: int
    stored_samples: tuple[int, ...]

    @classmethod
    def from_message(cls, message: SysExMessage) -> "UserWave":
        _require_type(message, DumpType.USER_WAVE)
        _require_payload_length(message, 128)
        raw_samples = nibbles_to_bytes(message.payload)
        samples = tuple(decode_offset_binary_i8(value) for value in raw_samples)
        return cls(message.device_id, message.address, samples)

    def __post_init__(self) -> None:
        if not USER_WAVE_FIRST <= self.number <= USER_WAVE_LAST:
            raise ProtocolError(f"User Wave number out of range: {self.number}")
        if len(self.stored_samples) != 64:
            raise PayloadLengthError(
                f"A User Wave must contain 64 stored samples, got {len(self.stored_samples)}"
            )
        for sample in self.stored_samples:
            if not -128 <= sample <= 127:
                raise ProtocolError(f"User Wave sample out of int8 range: {sample}")

    @property
    def payload(self) -> bytes:
        raw = bytes(
            encode_offset_binary_i8(sample) for sample in self.stored_samples
        )
        return bytes_to_nibbles(raw)

    @property
    def has_negative_full_scale(self) -> bool:
        """Whether the stored half contains -128, whose negation is +128."""
        return -128 in self.stored_samples

    def reconstruct(
        self,
        policy: Literal[
            "documented",
            "mathematical",
            "wrap_i8",
            "saturate_i8",
        ] = "documented",
    ) -> tuple[int, ...]:
        """Reconstruct the documented 128-point logical cycle.

        ``documented`` and ``mathematical`` implement the manual's rule without
        silently forcing the result back into int8. ``wrap_i8`` and
        ``saturate_i8`` are explicit diagnostic edge policies for -128 only.
        """
        mirrored = [-sample for sample in reversed(self.stored_samples)]
        if policy == "wrap_i8":
            mirrored = [signed_i8(value & 0xFF) for value in mirrored]
        elif policy == "saturate_i8":
            mirrored = [max(-128, min(127, value)) for value in mirrored]
        elif policy not in {"documented", "mathematical"}:
            raise ProtocolError(f"Unknown reconstruction policy: {policy}")
        return self.stored_samples + tuple(mirrored)

    def to_message(self) -> SysExMessage:
        return SysExMessage(
            device_id=self.device_id,
            dump_type=DumpType.USER_WAVE,
            address=self.number,
            payload=self.payload,
        )


@dataclass(frozen=True, slots=True)
class UserWavetable:
    device_id: int
    internal_number: int
    references: tuple[int, ...]

    @classmethod
    def from_message(cls, message: SysExMessage) -> "UserWavetable":
        _require_type(message, DumpType.USER_WAVETABLE)
        _require_payload_length(message, 256)
        return cls(
            device_id=message.device_id,
            internal_number=message.address,
            references=unpack_u16_nibbles(message.payload),
        )

    def __post_init__(self) -> None:
        if not (
            USER_WAVETABLE_INTERNAL_FIRST
            <= self.internal_number
            <= USER_WAVETABLE_INTERNAL_LAST
        ):
            raise ProtocolError(
                f"User Wavetable internal number out of range: {self.internal_number}"
            )
        if len(self.references) != 64:
            raise PayloadLengthError(
                f"A User Wavetable must contain 64 references, got {len(self.references)}"
            )
        for reference in self.references:
            if not 0 <= reference <= 0xFFFF:
                raise ProtocolError(f"Wave reference out of range: {reference}")

    @property
    def display_number(self) -> int:
        return self.internal_number + 1

    @classmethod
    def from_display_number(
        cls, device_id: int, display_number: int, references: tuple[int, ...]
    ) -> "UserWavetable":
        if not (
            USER_WAVETABLE_DISPLAY_FIRST
            <= display_number
            <= USER_WAVETABLE_DISPLAY_LAST
        ):
            raise ProtocolError(
                f"User Wavetable display number out of range: {display_number}"
            )
        return cls(device_id, display_number - 1, references)

    @property
    def explicit_positions(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, reference in enumerate(self.references)
            if reference != INTERPOLATED_WAVE_REFERENCE
        )

    def to_message(self) -> SysExMessage:
        return SysExMessage(
            device_id=self.device_id,
            dump_type=DumpType.USER_WAVETABLE,
            address=self.internal_number,
            payload=pack_u16_nibbles(self.references),
        )


@dataclass(frozen=True, slots=True)
class GlobalParameters:
    device_id: int
    data: bytes

    @classmethod
    def from_message(cls, message: SysExMessage) -> "GlobalParameters":
        _require_type(message, DumpType.GLOBAL)
        _require_payload_length(message, 30)
        return cls(message.device_id, message.payload)

    def to_message(self) -> SysExMessage:
        return SysExMessage(self.device_id, DumpType.GLOBAL, 0, self.data)


def decode_typed(
    message: SysExMessage,
) -> (
    SoundProgram
    | MultiProgram
    | UserWave
    | UserWavetable
    | GlobalParameters
    | SysExMessage
):
    try:
        dump_type = DumpType(int(message.dump_type))
    except ValueError:
        return message
    if dump_type is DumpType.SOUND:
        return SoundProgram.from_message(message)
    if dump_type is DumpType.MULTI:
        return MultiProgram.from_message(message)
    if dump_type is DumpType.USER_WAVE:
        return UserWave.from_message(message)
    if dump_type is DumpType.USER_WAVETABLE:
        return UserWavetable.from_message(message)
    if dump_type is DumpType.GLOBAL:
        return GlobalParameters.from_message(message)
    return message


def _require_type(message: SysExMessage, dump_type: DumpType) -> None:
    if int(message.dump_type) != int(dump_type):
        raise ProtocolError(
            f"Expected dump type {int(dump_type):#04x}, got {int(message.dump_type):#04x}"
        )


def _require_payload_length(message: SysExMessage, expected: int) -> None:
    if len(message.payload) != expected:
        raise PayloadLengthError(
            f"Expected payload length {expected}, got {len(message.payload)}"
        )
