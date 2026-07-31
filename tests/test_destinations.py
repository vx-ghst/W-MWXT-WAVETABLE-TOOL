from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.destinations import (
    DeviceAddress,
    SoundBank,
    SoundDestination,
    SoundNamePolicy,
    UserWavetableDestination,
    encode_sound_name,
)
from w_mwxt_wavetable_tool.errors import DestinationError


def test_direct_device_id_boundaries() -> None:
    assert DeviceAddress(0).is_direct
    assert DeviceAddress(126).is_direct
    with pytest.raises(DestinationError):
        DeviceAddress(-1)
    with pytest.raises(DestinationError):
        DeviceAddress(128)


def test_broadcast_requires_explicit_opt_in() -> None:
    with pytest.raises(DestinationError, match="broadcast"):
        DeviceAddress(127)
    address = DeviceAddress(127, allow_broadcast=True)
    assert address.is_broadcast
    with pytest.raises(DestinationError):
        DeviceAddress(0, allow_broadcast=True)


def test_wavetable_display_and_internal_boundaries() -> None:
    first = UserWavetableDestination(97)
    last = UserWavetableDestination(128)
    assert first.internal_number == 96
    assert last.internal_number == 127
    assert UserWavetableDestination.from_internal_number(96) == first
    assert UserWavetableDestination.from_internal_number(127) == last


@pytest.mark.parametrize("number", [96, 129])
def test_wavetable_display_out_of_range_is_rejected(number: int) -> None:
    with pytest.raises(DestinationError):
        UserWavetableDestination(number)


@pytest.mark.parametrize(
    ("text", "display", "wire_address"),
    [
        ("A001", "A001", 0),
        ("A128", "A128", 127),
        ("B001", "B001", 128),
        ("B128", "B128", 255),
    ],
)
def test_stored_sound_destinations(text: str, display: str, wire_address: int) -> None:
    destination = SoundDestination.parse(text)
    assert destination.display_location == display
    assert destination.wire_address == wire_address
    assert not destination.is_edit_buffer


def test_stored_destination_accepts_the_typed_bank_enum() -> None:
    assert SoundDestination.stored(SoundBank.B, 1).display_location == "B001"


def test_edit_buffer_is_semantic_until_wire_address_is_confirmed() -> None:
    destination = SoundDestination.parse("edit buffer")
    assert destination.is_edit_buffer
    assert destination.display_location == "EDIT_BUFFER"
    assert destination.wire_address is None


@pytest.mark.parametrize("text", ["A000", "A129", "C001", "A01", "garbage"])
def test_invalid_sound_destinations_are_rejected(text: str) -> None:
    with pytest.raises(DestinationError):
        SoundDestination.parse(text)


def test_sound_name_strict_policy_accepts_exactly_16_ascii_characters() -> None:
    encoded = encode_sound_name("1234567890ABCDEF")
    assert encoded == b"1234567890ABCDEF"


def test_sound_name_strict_policy_rejects_long_or_non_ascii_names() -> None:
    with pytest.raises(DestinationError, match="too long"):
        encode_sound_name("1234567890ABCDEFG")
    with pytest.raises(DestinationError, match="ASCII"):
        encode_sound_name("BASSÉ")


def test_sound_name_sanitize_policy_is_explicit_and_fixed_width() -> None:
    encoded = encode_sound_name(
        "BASSÉ-123456789012345",
        policy=SoundNamePolicy.SANITIZE,
    )
    assert encoded == b"BASS?-1234567890"
    assert len(encoded) == 16
