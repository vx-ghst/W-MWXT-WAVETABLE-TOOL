from __future__ import annotations

import math


_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def frequency_to_midi(frequency_hz: float, *, reference_a4_hz: float = 440.0) -> float:
    frequency = float(frequency_hz)
    reference = float(reference_a4_hz)
    if not math.isfinite(frequency) or frequency <= 0.0:
        raise ValueError("frequency_hz must be finite and positive")
    if not math.isfinite(reference) or reference <= 0.0:
        raise ValueError("reference_a4_hz must be finite and positive")
    return float(69.0 + 12.0 * math.log2(frequency / reference))


def midi_to_frequency(midi_note: float, *, reference_a4_hz: float = 440.0) -> float:
    midi = float(midi_note)
    reference = float(reference_a4_hz)
    if not math.isfinite(midi):
        raise ValueError("midi_note must be finite")
    if not math.isfinite(reference) or reference <= 0.0:
        raise ValueError("reference_a4_hz must be finite and positive")
    return float(reference * (2.0 ** ((midi - 69.0) / 12.0)))


def nearest_midi_note(midi_note: float) -> int:
    midi = float(midi_note)
    if not math.isfinite(midi):
        raise ValueError("midi_note must be finite")
    return int(math.floor(midi + 0.5))


def midi_note_name(midi_note: int) -> str:
    midi = int(midi_note)
    octave = midi // 12 - 1
    return f"{_NOTE_NAMES[midi % 12]}{octave}"


def describe_frequency(
    frequency_hz: float,
    *,
    reference_a4_hz: float = 440.0,
) -> tuple[float, int, str, float]:
    midi = frequency_to_midi(frequency_hz, reference_a4_hz=reference_a4_hz)
    nearest = nearest_midi_note(midi)
    cents = float(100.0 * (midi - nearest))
    return midi, nearest, midi_note_name(nearest), cents
