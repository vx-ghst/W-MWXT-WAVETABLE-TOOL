from __future__ import annotations

import math

import pytest

from w_mwxt_wavetable_tool.analysis import (
    describe_frequency,
    frequency_to_midi,
    midi_note_name,
    midi_to_frequency,
    nearest_midi_note,
)


def test_a4_frequency_maps_to_midi_69() -> None:
    assert frequency_to_midi(440.0) == pytest.approx(69.0)


def test_midi_69_maps_to_a4_frequency() -> None:
    assert midi_to_frequency(69.0) == pytest.approx(440.0)


def test_frequency_and_midi_conversion_are_inverse() -> None:
    for midi in (0.0, 24.5, 60.0, 69.0, 84.25, 127.0):
        assert frequency_to_midi(midi_to_frequency(midi)) == pytest.approx(midi)


def test_note_names_use_scientific_pitch_notation() -> None:
    assert midi_note_name(0) == "C-1"
    assert midi_note_name(60) == "C4"
    assert midi_note_name(69) == "A4"
    assert midi_note_name(127) == "G9"


def test_nearest_note_rounds_half_up_deterministically() -> None:
    assert nearest_midi_note(69.49) == 69
    assert nearest_midi_note(69.50) == 70


def test_describe_frequency_reports_note_and_cents() -> None:
    frequency = 440.0 * 2.0 ** (25.0 / 1200.0)
    midi, nearest, name, cents = describe_frequency(frequency)
    assert midi == pytest.approx(69.25)
    assert nearest == 69
    assert name == "A4"
    assert cents == pytest.approx(25.0)


def test_custom_reference_frequency_is_supported() -> None:
    midi, nearest, name, cents = describe_frequency(432.0, reference_a4_hz=432.0)
    assert midi == pytest.approx(69.0)
    assert nearest == 69
    assert name == "A4"
    assert cents == pytest.approx(0.0)


@pytest.mark.parametrize("value", [0.0, -1.0, math.nan, math.inf])
def test_invalid_frequency_is_rejected(value: float) -> None:
    with pytest.raises(ValueError):
        frequency_to_midi(value)


@pytest.mark.parametrize("reference", [0.0, -440.0, math.nan, math.inf])
def test_invalid_reference_is_rejected(reference: float) -> None:
    with pytest.raises(ValueError):
        midi_to_frequency(69.0, reference_a4_hz=reference)
