from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .constants import (
    DEVICE_ID_BROADCAST,
    DEVICE_ID_FIRST,
    DEVICE_ID_LAST,
    PATCH_NAME_LENGTH,
    SOUND_SLOT_DISPLAY_FIRST,
    SOUND_SLOT_DISPLAY_LAST,
    USER_WAVETABLE_DISPLAY_FIRST,
    USER_WAVETABLE_DISPLAY_LAST,
    USER_WAVETABLE_INTERNAL_FIRST,
    USER_WAVETABLE_INTERNAL_LAST,
)
from .errors import DestinationError


class SoundBank(str, Enum):
    A = "A"
    B = "B"


class SoundNamePolicy(str, Enum):
    REJECT = "reject"
    SANITIZE = "sanitize"


@dataclass(frozen=True, slots=True)
class DeviceAddress:
    """A safe Microwave XT Device ID selection.

    Device IDs 0..126 address one device. ID 127 is broadcast and is accepted
    only when ``allow_broadcast`` is explicitly true.
    """

    value: int
    allow_broadcast: bool = False

    def __post_init__(self) -> None:
        if not DEVICE_ID_FIRST <= self.value <= DEVICE_ID_BROADCAST:
            raise DestinationError(f"Device ID out of range: {self.value}")
        if self.value == DEVICE_ID_BROADCAST and not self.allow_broadcast:
            raise DestinationError(
                "Device ID 127 is broadcast and requires allow_broadcast=True"
            )
        if self.value != DEVICE_ID_BROADCAST and self.allow_broadcast:
            raise DestinationError(
                "allow_broadcast=True is valid only with Device ID 127"
            )

    @property
    def is_broadcast(self) -> bool:
        return self.value == DEVICE_ID_BROADCAST

    @property
    def is_direct(self) -> bool:
        return DEVICE_ID_FIRST <= self.value <= DEVICE_ID_LAST


@dataclass(frozen=True, slots=True)
class UserWavetableDestination:
    """A user-facing Wavetable number with its confirmed internal address."""

    display_number: int

    def __post_init__(self) -> None:
        if not USER_WAVETABLE_DISPLAY_FIRST <= self.display_number <= USER_WAVETABLE_DISPLAY_LAST:
            raise DestinationError(
                f"User Wavetable display number out of range: {self.display_number}"
            )

    @property
    def internal_number(self) -> int:
        return self.display_number - 1

    @classmethod
    def from_internal_number(cls, internal_number: int) -> "UserWavetableDestination":
        if not USER_WAVETABLE_INTERNAL_FIRST <= internal_number <= USER_WAVETABLE_INTERNAL_LAST:
            raise DestinationError(
                f"User Wavetable internal number out of range: {internal_number}"
            )
        return cls(internal_number + 1)


@dataclass(frozen=True, slots=True)
class SoundDestination:
    """A Sound destination in bank A, bank B, or the edit buffer."""

    bank: SoundBank | None
    slot: int | None

    def __post_init__(self) -> None:
        if self.bank is None:
            if self.slot is not None:
                raise DestinationError("Edit Buffer destination cannot have a slot")
            return
        if not isinstance(self.bank, SoundBank):
            raise DestinationError(f"Invalid Sound bank: {self.bank!r}")
        if self.slot is None or not SOUND_SLOT_DISPLAY_FIRST <= self.slot <= SOUND_SLOT_DISPLAY_LAST:
            raise DestinationError(f"Sound slot out of range: {self.slot}")

    @classmethod
    def stored(cls, bank: SoundBank | str, slot: int) -> "SoundDestination":
        if isinstance(bank, SoundBank):
            normalized_bank = bank
        else:
            try:
                normalized_bank = SoundBank(str(bank).upper())
            except ValueError as exc:
                raise DestinationError(f"Invalid Sound bank: {bank!r}") from exc
        return cls(normalized_bank, slot)

    @classmethod
    def edit_buffer(cls) -> "SoundDestination":
        return cls(None, None)

    @classmethod
    def parse(cls, value: str) -> "SoundDestination":
        normalized = value.strip().upper().replace(" ", "_")
        if normalized in {"EDIT", "EDIT_BUFFER", "BUFFER"}:
            return cls.edit_buffer()
        if len(normalized) != 4 or normalized[0] not in {"A", "B"} or not normalized[1:].isdigit():
            raise DestinationError(f"Invalid Sound destination: {value!r}")
        return cls.stored(normalized[0], int(normalized[1:]))

    @property
    def is_edit_buffer(self) -> bool:
        return self.bank is None

    @property
    def display_location(self) -> str:
        if self.is_edit_buffer:
            return "EDIT_BUFFER"
        assert self.bank is not None and self.slot is not None
        return f"{self.bank.value}{self.slot:03d}"

    @property
    def wire_address(self) -> int | None:
        """Return the confirmed bank address, or ``None`` for the edit buffer.

        The edit-buffer wire address is intentionally not guessed in CODE V2-A.
        """
        if self.is_edit_buffer:
            return None
        assert self.bank is not None and self.slot is not None
        bank_index = 0 if self.bank is SoundBank.A else 1
        return (bank_index << 7) | (self.slot - 1)


def encode_sound_name(
    name: str,
    *,
    policy: SoundNamePolicy | str = SoundNamePolicy.REJECT,
) -> bytes:
    """Encode a fixed-width, printable-ASCII Microwave XT Sound name.

    ``REJECT`` refuses unsupported characters and names over 16 characters.
    ``SANITIZE`` replaces unsupported characters with ``?`` and truncates.
    Both policies pad the resulting field with spaces to exactly 16 bytes.
    """

    try:
        normalized_policy = SoundNamePolicy(policy)
    except ValueError as exc:
        raise DestinationError(f"Unknown Sound name policy: {policy!r}") from exc

    if not isinstance(name, str):
        raise DestinationError("Sound name must be a string")

    if normalized_policy is SoundNamePolicy.REJECT:
        if len(name) > PATCH_NAME_LENGTH:
            raise DestinationError(
                f"Sound name is too long: {len(name)} characters; maximum is {PATCH_NAME_LENGTH}"
            )
        if any(not 0x20 <= ord(character) <= 0x7E for character in name):
            raise DestinationError("Sound name must contain printable ASCII characters only")
        encoded = name.encode("ascii")
    else:
        sanitized = "".join(
            character if 0x20 <= ord(character) <= 0x7E else "?"
            for character in name
        )
        encoded = sanitized[:PATCH_NAME_LENGTH].encode("ascii")

    return encoded.ljust(PATCH_NAME_LENGTH, b" ")
