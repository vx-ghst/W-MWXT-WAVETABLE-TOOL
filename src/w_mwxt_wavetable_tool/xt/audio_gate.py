from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import numpy as np
import soundfile as sf

from ..constants import (
    INTERPOLATED_WAVE_REFERENCE,
    PATCH_NAME_LENGTH,
    PATCH_NAME_OFFSET,
    PATCH_WAVETABLE_OFFSET,
    USER_WAVE_FIRST,
    USER_WAVE_LAST,
    USER_WAVETABLE_DISPLAY_FIRST,
    USER_WAVETABLE_DISPLAY_LAST,
    DumpType,
)
from ..dump import DumpFile
from ..errors import HardwareValidationError
from ..message import SysExMessage
from ..models import SoundProgram, UserWave, UserWavetable
from ..version import __version__
from .reconstruction_gate import (
    DOCUMENTED_RECONSTRUCTION_LAW,
    SAFE_OPTIMIZER_MAX,
    SAFE_OPTIMIZER_MIN,
    XtGatePattern,
    XtGateProbe,
    build_xt_reconstruction_gate,
)

AUDIO_GATE_SCHEMA_VERSION = 1
DEFAULT_STEM = "CODE_V7_A2_XT_AUDIO_GATE"
MIN_CAPTURE_SAMPLE_RATE = 48_000
RECOMMENDED_CAPTURE_SAMPLE_RATE = 96_000
PHASE_BINS = 128
_CAPTURE_STEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SOUND_LOCATION = re.compile(r"^(?P<bank>[AB])(?P<slot>\d{3})$", re.IGNORECASE)


class XtAudioGateStatus(str, Enum):
    PASS = "pass"
    INCOMPLETE = "incomplete"
    INCONCLUSIVE = "inconclusive"
    FAIL = "fail"


class XtAudioGateVerdict(str, Enum):
    SETUP_CONFIRMED = "setup_confirmed"
    SETUP_FAILED = "setup_failed"
    SAFE_RECONSTRUCTION_SUPPORTED_EDGE_POSITIVE = (
        "safe_reconstruction_supported_edge_positive"
    )
    SAFE_RECONSTRUCTION_SUPPORTED_EDGE_WRAP = (
        "safe_reconstruction_supported_edge_wrap"
    )
    SAFE_RECONSTRUCTION_SUPPORTED_EDGE_ZERO = (
        "safe_reconstruction_supported_edge_zero"
    )
    SAFE_RECONSTRUCTION_SUPPORTED_EDGE_INCONCLUSIVE = (
        "safe_reconstruction_supported_edge_inconclusive"
    )
    SAFE_RECONSTRUCTION_INCONCLUSIVE = "safe_reconstruction_inconclusive"
    SAFE_RECONSTRUCTION_CONFLICT = "safe_reconstruction_conflict"
    CAPTURES_INCOMPLETE = "captures_incomplete"
    RESTORE_CONFIRMED = "restore_confirmed"
    RESTORE_FAILED = "restore_failed"


class XtAudioWaveRole(str, Enum):
    SAFE = "safe_asymmetric"
    OFFSET_BINARY_EDGE = "offset_binary_edge"
    NEGATIVE_FULL_SCALE_EDGE = "negative_full_scale_edge"


class XtAudioHypothesis(str, Enum):
    DOCUMENTED_REVERSE_NEGATE = "documented_reverse_negate"
    REPEAT_FIRST_HALF = "repeat_first_half"
    MIRROR_FIRST_HALF = "mirror_first_half"
    NEGATE_FIRST_HALF = "negate_first_half"
    ZERO_FILL_SECOND_HALF = "zero_fill_second_half"
    POSITIVE_NEGATIVE_FULL_SCALE = "positive_negative_full_scale"
    WRAP_NEGATIVE_FULL_SCALE = "wrap_negative_full_scale"
    ZERO_NEGATIVE_FULL_SCALE = "zero_negative_full_scale"


_ROLE_BY_PATTERN = {
    XtGatePattern.INDEXED_ASYMMETRIC: XtAudioWaveRole.SAFE,
    XtGatePattern.OFFSET_BINARY_GOLDEN: XtAudioWaveRole.OFFSET_BINARY_EDGE,
    XtGatePattern.NEGATIVE_FULL_SCALE_EDGE: XtAudioWaveRole.NEGATIVE_FULL_SCALE_EDGE,
}

_NOTE_TOKENS = {
    36: "MIDI36",
    48: "MIDI48",
    60: "MIDI60",
}

_NOTE_LABELS = {
    36: "MIDI 36 (scientific C2; Ableton C1)",
    48: "MIDI 48 (scientific C3; Ableton C2)",
    60: "MIDI 60 (scientific C4; Ableton C3)",
}

# Microwave II/XT SNDD byte indexes from the published SysEx appendix.
# Reserved/unknown bytes are preserved from the target Sound in the backup.
# Values are raw 7-bit parameter bytes.
_CONTROLLED_SOUND_FIXED_OVERRIDES: dict[int, int] = {
    0: 1,    # Published Sound data format version
    1: 64,   # Osc 1 octave: 0
    2: 64,   # Osc 1 semitone: 0
    3: 64,   # Osc 1 detune: 0
    5: 0,    # Osc 1 pitch-bend range: minimum; no pitch bend is sent
    6: 48,   # Osc 1 keytrack: documented 100% tracking
    7: 0,    # Osc 1 FM amount
    12: 64,  # Osc 2 octave: 0
    13: 64,  # Osc 2 semitone: 0
    14: 64,  # Osc 2 detune: 0
    16: 0,   # Osc 2 sync off
    17: 0,   # Osc 2 pitch-bend range
    18: 48,  # Osc 2 keytrack: documented 100% tracking
    19: 0,   # Osc 2 link off
    26: 0,   # Wave 1 start wave
    27: 1,   # Wave 1 fixed phase: first non-free phase value
    28: 64,  # Wave 1 envelope amount: zero
    29: 64,  # Wave 1 envelope velocity amount: zero
    30: 64,  # Wave 1 keytrack: zero
    31: 0,   # Wave 1 limit off
    36: 0,   # Wave 2 start wave
    37: 1,   # Wave 2 fixed phase
    38: 64,  # Wave 2 envelope amount: zero
    39: 64,  # Wave 2 envelope velocity amount: zero
    40: 64,  # Wave 2 keytrack: zero
    41: 0,   # Wave 2 limit off
    42: 0,   # Wave 2 link off
    47: 96,  # Wave 1 level: controlled headroom
    48: 0,   # Wave 2 level
    49: 0,   # Ring-mod level
    50: 0,   # Noise level
    51: 0,   # External input level
    53: 0,   # Aliasing: off/base setting
    54: 0,   # Time Quantization: off
    55: 0,   # Clipping: Saturate
    57: 1,   # Accuracy: on
    62: 127, # Filter 1 cutoff fully open
    63: 0,   # Filter 1 resonance
    64: 0,   # Filter 1 type: first documented low-pass mode
    65: 64,  # Filter 1 keytrack: zero
    66: 64,  # Filter 1 envelope amount: zero
    67: 64,  # Filter 1 envelope velocity amount: zero
    70: 0,   # Filter 1 extra/context parameter
    73: 127, # Filter 2 cutoff fully open
    74: 0,   # Filter 2 type: first documented mode
    75: 64,  # Filter 2 keytrack: zero
    76: 0,   # Effect type/off baseline
    77: 100, # Amplifier volume with headroom
    79: 64,  # Amplifier envelope velocity amount: zero
    80: 64,  # Amplifier keytrack: zero
    81: 0,   # Effect parameter 1
    82: 0,   # Chorus off
    83: 0,   # Effect parameter 2
    84: 64,  # Pan center
    85: 64,  # Pan keytrack: zero
    86: 0,   # Effect parameter 3 / documented context byte
    87: 0,   # Glide active off
    88: 0,   # Glide type
    89: 0,   # Glide mode
    90: 0,   # Glide time
    92: 0,   # Arpeggiator off
    108: 0,  # Allocation mode: Poly
    109: 0,  # Assignment: Normal (no Dual/Unison voice stacking)
    110: 64, # Assignment detune: neutral center
    113: 0,  # Filter envelope attack
    114: 0,  # Filter envelope decay
    115: 127,# Filter envelope sustain
    116: 0,  # Filter envelope release
    117: 0,  # Filter envelope trigger: normal
    119: 0,  # Amplifier envelope attack
    120: 0,  # Amplifier envelope decay
    121: 127,# Amplifier envelope sustain
    122: 0,  # Amplifier envelope release
    123: 0,  # Amplifier envelope trigger: normal
}


_CONTROLLED_SOUND_PARAMETER_LABELS: dict[int, str] = {
    0: "Sound format version",
    1: "Osc 1 octave",
    2: "Osc 1 semitone",
    3: "Osc 1 detune",
    5: "Osc 1 pitch-bend range",
    6: "Osc 1 keytrack (100%)",
    7: "Osc 1 FM amount",
    12: "Osc 2 octave",
    13: "Osc 2 semitone",
    14: "Osc 2 detune",
    16: "Osc 2 sync",
    17: "Osc 2 pitch-bend range",
    18: "Osc 2 keytrack (100%)",
    19: "Osc 2 link",
    25: "Wavetable",
    26: "Wave 1 startwave",
    27: "Wave 1 fixed phase",
    28: "Wave 1 envelope amount",
    29: "Wave 1 envelope velocity amount",
    30: "Wave 1 keytrack",
    31: "Wave 1 limit",
    36: "Wave 2 startwave",
    37: "Wave 2 fixed phase",
    38: "Wave 2 envelope amount",
    39: "Wave 2 envelope velocity amount",
    40: "Wave 2 keytrack",
    41: "Wave 2 limit",
    42: "Wave 2 link",
    47: "Mix Wave 1",
    48: "Mix Wave 2",
    49: "Mix Ringmod",
    50: "Mix Noise",
    51: "Mix External",
    53: "Aliasing",
    54: "Time Quantization",
    55: "Clipping",
    57: "Accuracy",
    62: "Filter 1 cutoff",
    63: "Filter 1 resonance",
    64: "Filter 1 type",
    65: "Filter 1 keytrack",
    66: "Filter 1 envelope amount",
    67: "Filter 1 envelope velocity amount",
    70: "Filter 1 extra",
    73: "Filter 2 cutoff",
    74: "Filter 2 type",
    75: "Filter 2 keytrack",
    76: "Effect type",
    77: "Amplifier volume",
    79: "Amplifier envelope velocity amount",
    80: "Amplifier keytrack",
    81: "Effect parameter 1",
    82: "Chorus",
    83: "Effect parameter 2",
    84: "Panning",
    85: "Panning keytrack",
    86: "Effect parameter 3",
    87: "Glide active",
    88: "Glide type",
    89: "Glide mode",
    90: "Glide time",
    92: "Arpeggiator active",
    108: "Allocation mode (Poly)",
    109: "Assignment (Normal)",
    110: "Assignment detune",
    113: "Filter envelope attack",
    114: "Filter envelope decay",
    115: "Filter envelope sustain",
    116: "Filter envelope release",
    117: "Filter envelope trigger",
    119: "Amplifier envelope attack",
    120: "Amplifier envelope decay",
    121: "Amplifier envelope sustain",
    122: "Amplifier envelope release",
    123: "Amplifier envelope trigger",
}


def _json_hash(data: Mapping[str, Any]) -> str:
    raw = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _bytes_hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _require_hash(value: str, label: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise HardwareValidationError(f"invalid {label}")


def _parse_sound_location(location: str) -> tuple[int, int, int]:
    match = _SOUND_LOCATION.fullmatch(location.strip())
    if match is None:
        raise HardwareValidationError(
            "Sound location must be A001..A128 or B001..B128"
        )
    bank = 0 if match.group("bank").upper() == "A" else 1
    slot_display = int(match.group("slot"))
    if not 1 <= slot_display <= 128:
        raise HardwareValidationError("Sound slot must be in 001..128")
    slot = slot_display - 1
    return bank, slot, (bank << 7) | slot


def _message_key(message: SysExMessage) -> tuple[int, int]:
    return int(message.dump_type), message.address


def _find_unique(
    dump: DumpFile,
    dump_type: DumpType,
    address: int,
    *,
    label: str,
) -> SysExMessage:
    matches = tuple(
        message
        for message in dump.messages
        if int(message.dump_type) == int(dump_type) and message.address == address
    )
    if len(matches) != 1:
        raise HardwareValidationError(
            f"{label} requires exactly one {dump_type.name} at address {address}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _validate_v7a1_reports(
    storage_report: Mapping[str, Any],
    restore_report: Mapping[str, Any],
) -> None:
    if storage_report.get("status") != "pass":
        raise HardwareValidationError("V7-A.1 storage report is not PASS")
    if storage_report.get("storage_passed") is not True:
        raise HardwareValidationError("V7-A.1 storage report lacks storage_passed=true")
    if storage_report.get("v7_b_allowed_under_safe_range") is not True:
        raise HardwareValidationError(
            "V7-A.1 storage report does not allow V7-B under the safe range"
        )
    if restore_report.get("status") != "pass":
        raise HardwareValidationError("V7-A.1 restore report is not PASS")
    if restore_report.get("verdict") != "restore_confirmed":
        raise HardwareValidationError("V7-A.1 restore report is not restore_confirmed")


def _sound_overrides(target_wavetable_internal: int) -> dict[int, int]:
    overrides = dict(_CONTROLLED_SOUND_FIXED_OVERRIDES)
    overrides[PATCH_WAVETABLE_OFFSET] = target_wavetable_internal
    # Disable all sixteen modulation rows: source=off, amount=0 (raw 64),
    # destination=0. The documented table occupies indexes 192..239.
    for base in range(192, 240, 3):
        overrides[base] = 0
        overrides[base + 1] = 64
        overrides[base + 2] = 0
    return overrides


def build_controlled_audio_sound(
    source: SoundProgram,
    *,
    device_id: int,
    target_bank: int,
    target_slot: int,
    target_wavetable_internal: int,
    name: str = "V7A2 AUDIO GATE",
) -> tuple[SoundProgram, tuple[dict[str, int], ...]]:
    if len(source.data) != 256:
        raise HardwareValidationError("Sound template must contain 256 data bytes")
    data = bytearray(source.data)
    changes: list[dict[str, int]] = []
    for index, value in sorted(_sound_overrides(target_wavetable_internal).items()):
        before = data[index]
        if not 0 <= value <= 127:
            raise HardwareValidationError(f"invalid 7-bit Sound value at {index}")
        data[index] = value
        if before != value:
            changes.append({"index": index, "before": before, "after": value})
    encoded_name = name.encode("ascii", errors="replace")[:PATCH_NAME_LENGTH]
    encoded_name = encoded_name.ljust(PATCH_NAME_LENGTH, b" ")
    for offset, value in enumerate(encoded_name, start=PATCH_NAME_OFFSET):
        before = data[offset]
        data[offset] = value
        if before != value:
            changes.append({"index": offset, "before": before, "after": value})
    return (
        SoundProgram(device_id, target_bank, target_slot, bytes(data)),
        tuple(changes),
    )


def _wavetable_for_probe(device_id: int, display_number: int, wave_number: int) -> UserWavetable:
    references = (wave_number,) * 61 + (0, 1, 2)
    return UserWavetable.from_display_number(device_id, display_number, references)


def _midi_vlq(value: int) -> bytes:
    if value < 0:
        raise HardwareValidationError("MIDI delta time must be non-negative")
    buffer = value & 0x7F
    output = bytearray((buffer,))
    value >>= 7
    while value:
        buffer = (value & 0x7F) | 0x80
        output.insert(0, buffer)
        value >>= 7
    return bytes(output)


def build_note_midi(
    midi_note: int,
    *,
    velocity: int = 100,
    duration_seconds: float = 4.0,
    bpm: int = 120,
    division: int = 480,
) -> bytes:
    if not 0 <= midi_note <= 127:
        raise HardwareValidationError("MIDI note must be in 0..127")
    if not 1 <= velocity <= 127:
        raise HardwareValidationError("MIDI velocity must be in 1..127")
    if duration_seconds <= 0 or bpm <= 0 or division <= 0:
        raise HardwareValidationError("invalid MIDI timing")
    microseconds_per_quarter = round(60_000_000 / bpm)
    duration_ticks = round(duration_seconds * bpm * division / 60.0)
    track = bytearray()
    track.extend(b"\x00\xFF\x51\x03")
    track.extend(microseconds_per_quarter.to_bytes(3, "big"))
    track.extend(b"\x00\x90")
    track.extend((midi_note, velocity))
    track.extend(_midi_vlq(duration_ticks))
    track.extend(b"\x80")
    track.extend((midi_note, 0))
    track.extend(b"\x00\xFF\x2F\x00")
    return (
        b"MThd"
        + (6).to_bytes(4, "big")
        + (0).to_bytes(2, "big")
        + (1).to_bytes(2, "big")
        + division.to_bytes(2, "big")
        + b"MTrk"
        + len(track).to_bytes(4, "big")
        + bytes(track)
    )


@dataclass(frozen=True, slots=True)
class XtAudioCaptureSpec:
    capture_id: str
    role: XtAudioWaveRole | None
    selector_filename: str | None
    midi_note: int | None
    note_name: str | None
    take: int
    filename: str
    required: bool
    instruction: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "role": None if self.role is None else self.role.value,
            "selector_filename": self.selector_filename,
            "midi_note": self.midi_note,
            "note_name": self.note_name,
            "take": self.take,
            "filename": self.filename,
            "required": self.required,
            "instruction": self.instruction,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "XtAudioCaptureSpec":
        role_value = data.get("role")
        return cls(
            capture_id=str(data["capture_id"]),
            role=None if role_value is None else XtAudioWaveRole(str(role_value)),
            selector_filename=(
                None
                if data.get("selector_filename") is None
                else str(data["selector_filename"])
            ),
            midi_note=(
                None if data.get("midi_note") is None else int(data["midi_note"])
            ),
            note_name=(
                None if data.get("note_name") is None else str(data["note_name"])
            ),
            take=int(data["take"]),
            filename=str(data["filename"]),
            required=bool(data["required"]),
            instruction=str(data["instruction"]),
        )


def default_capture_plan(stem: str = DEFAULT_STEM) -> tuple[XtAudioCaptureSpec, ...]:
    specs: list[XtAudioCaptureSpec] = [
        XtAudioCaptureSpec(
            capture_id="silence",
            role=None,
            selector_filename=f"{stem}.select-safe.syx",
            midi_note=None,
            note_name=None,
            take=1,
            filename="silence_5s.wav",
            required=True,
            instruction=(
                "Send select-safe, do not play a note, record five seconds with the "
                "same input gain used for every other capture."
            ),
        )
    ]
    for midi_note in (36, 48, 60):
        note_token = _NOTE_TOKENS[midi_note]
        note_name = _NOTE_LABELS[midi_note]
        specs.append(
            XtAudioCaptureSpec(
                capture_id=f"safe_{note_token}_take01",
                role=XtAudioWaveRole.SAFE,
                selector_filename=f"{stem}.select-safe.syx",
                midi_note=midi_note,
                note_name=note_name,
                take=1,
                filename=f"safe_{note_token}_take01.wav",
                required=True,
                instruction=(
                    f"Send select-safe, play MIDI note {midi_note} ({note_name}) "
                    "with the supplied four-second MIDI clip, and record mono."
                ),
            )
        )
    for role, role_stem, selector, repeats in (
        (
            XtAudioWaveRole.OFFSET_BINARY_EDGE,
            "offset",
            f"{stem}.select-offset-binary.syx",
            1,
        ),
        (
            XtAudioWaveRole.NEGATIVE_FULL_SCALE_EDGE,
            "negfs",
            f"{stem}.select-negative-full-scale.syx",
            3,
        ),
    ):
        for midi_note in (36, 48):
            note_token = _NOTE_TOKENS[midi_note]
            note_name = _NOTE_LABELS[midi_note]
            for take in range(1, repeats + 1):
                specs.append(
                    XtAudioCaptureSpec(
                        capture_id=f"{role_stem}_{note_token}_take{take:02d}",
                        role=role,
                        selector_filename=selector,
                        midi_note=midi_note,
                        note_name=note_name,
                        take=take,
                        filename=f"{role_stem}_{note_token}_take{take:02d}.wav",
                        required=True,
                        instruction=(
                            f"Send {Path(selector).name}, play MIDI note {midi_note} "
                            f"({note_name}) with the supplied four-second MIDI clip, "
                            "and record mono without changing gain."
                        ),
                    )
                )
    return tuple(specs)


@dataclass(frozen=True, slots=True)
class XtAudioGatePlan:
    schema_version: int
    tool_version: str
    device_id: int
    seed: int
    baseline_sha256: str
    v7a1_storage_report_sha256: str
    v7a1_restore_report_sha256: str
    target_wave_start: int
    target_wavetable_display: int
    target_sound_location: str
    setup_sha256: str
    select_safe_sha256: str
    select_offset_binary_sha256: str
    select_negative_full_scale_sha256: str
    restore_sha256: str
    probes: tuple[XtGateProbe, ...]
    sound_changes: tuple[dict[str, int], ...]
    captures: tuple[XtAudioCaptureSpec, ...]
    recommended_sample_rate: int = RECOMMENDED_CAPTURE_SAMPLE_RATE
    minimum_sample_rate: int = MIN_CAPTURE_SAMPLE_RATE

    def __post_init__(self) -> None:
        if self.schema_version != AUDIO_GATE_SCHEMA_VERSION:
            raise HardwareValidationError("unsupported V7-A.2 audio-gate schema")
        if not 0 <= self.device_id <= 126:
            raise HardwareValidationError("audio gate requires a direct Device ID")
        if len(self.probes) != 3:
            raise HardwareValidationError("audio gate requires the three V7-A.1 probes")
        for label in (
            "baseline_sha256",
            "v7a1_storage_report_sha256",
            "v7a1_restore_report_sha256",
            "setup_sha256",
            "select_safe_sha256",
            "select_offset_binary_sha256",
            "select_negative_full_scale_sha256",
            "restore_sha256",
        ):
            _require_hash(getattr(self, label), label)
        if not USER_WAVE_FIRST <= self.target_wave_start <= USER_WAVE_LAST - 2:
            raise HardwareValidationError("invalid target wave range")
        if not (
            USER_WAVETABLE_DISPLAY_FIRST
            <= self.target_wavetable_display
            <= USER_WAVETABLE_DISPLAY_LAST
        ):
            raise HardwareValidationError("invalid User Wavetable destination")
        _parse_sound_location(self.target_sound_location)
        required_ids = [capture.capture_id for capture in self.captures if capture.required]
        if len(required_ids) != len(set(required_ids)):
            raise HardwareValidationError("capture IDs must be unique")

    @property
    def target_wave_numbers(self) -> tuple[int, int, int]:
        return tuple(probe.target_wave_number for probe in self.probes)  # type: ignore[return-value]

    def _dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "device_id": self.device_id,
            "seed": self.seed,
            "baseline_sha256": self.baseline_sha256,
            "v7a1_storage_report_sha256": self.v7a1_storage_report_sha256,
            "v7a1_restore_report_sha256": self.v7a1_restore_report_sha256,
            "documented_reconstruction_law": DOCUMENTED_RECONSTRUCTION_LAW,
            "safe_optimizer_sample_range": [
                SAFE_OPTIMIZER_MIN,
                SAFE_OPTIMIZER_MAX,
            ],
            "target_wave_start": self.target_wave_start,
            "target_wave_numbers": list(self.target_wave_numbers),
            "target_wavetable_display": self.target_wavetable_display,
            "target_wavetable_internal": self.target_wavetable_display - 1,
            "target_sound_location": self.target_sound_location,
            "setup_sha256": self.setup_sha256,
            "select_safe_sha256": self.select_safe_sha256,
            "select_offset_binary_sha256": self.select_offset_binary_sha256,
            "select_negative_full_scale_sha256": (
                self.select_negative_full_scale_sha256
            ),
            "restore_sha256": self.restore_sha256,
            "probes": [probe.to_dict() for probe in self.probes],
            "sound_control": {
                "method": (
                    "clone target Sound from fresh Everything backup; overwrite only "
                    "documented measurement parameters; preserve reserved bytes"
                ),
                "fixed_phase_raw": 1,
                "wave_1_level_raw": 96,
                "wave_2_level_raw": 0,
                "ring_mod_level_raw": 0,
                "noise_level_raw": 0,
                "filter_1_cutoff_raw": 127,
                "filter_1_resonance_raw": 0,
                "aliasing_raw": 0,
                "time_quantization_raw": 0,
                "clipping_raw": 0,
                "accuracy_raw": 1,
                "modulation_rows_disabled": 16,
                "raw_overrides": [
                    {
                        "index": index,
                        "value": value,
                        "parameter": _CONTROLLED_SOUND_PARAMETER_LABELS.get(
                            index,
                            (
                                "Modulation row byte"
                                if 192 <= index <= 239
                                else "Documented Sound parameter"
                            ),
                        ),
                    }
                    for index, value in sorted(
                        _sound_overrides(self.target_wavetable_display - 1).items()
                    )
                ],
                "changes": list(self.sound_changes),
                "boundary": (
                    "This is a controlled documented-parameter Sound, not a claim of "
                    "bit-exact knowledge of every reserved or firmware-private byte."
                ),
            },
            "capture_format": {
                "channels": 1,
                "recommended_sample_rate": self.recommended_sample_rate,
                "minimum_sample_rate": self.minimum_sample_rate,
                "recommended_subtype": "PCM_24",
                "processing": "none",
                "gain_policy": "unchanged across all captures",
            },
            "captures": [capture.to_dict() for capture in self.captures],
            "evidence_boundary": {
                "can_support": [
                    "compatibility of the analog output with the documented reverse-negate law",
                    "ranking of positive, wrap, and zero treatments of the -128 edge",
                    "detection of a material oscillator-output conflict before V7-B",
                ],
                "cannot_prove": [
                    "bit-exact internal DSP samples",
                    "the exact DAC transfer function",
                    "complete V10 interpolation, aliasing, and time-quantization calibration",
                ],
            },
        }

    @property
    def plan_sha256(self) -> str:
        return _json_hash(self._dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self._dict(), "plan_sha256": self.plan_sha256}

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        ) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# CODE V7-A.2 — XT audio gate",
            "",
            f"- Plan SHA-256: `{self.plan_sha256}`",
            f"- Device ID: `{self.device_id}`",
            f"- User Waves: `{self.target_wave_numbers[0]}–{self.target_wave_numbers[-1]}`",
            f"- User Wavetable: `{self.target_wavetable_display:03d}`",
            f"- Sound: `{self.target_sound_location}`",
            f"- Recommended capture: mono PCM 24-bit / {self.recommended_sample_rate} Hz",
            f"- Minimum accepted sample rate: {self.minimum_sample_rate} Hz",
            "",
            "## Order",
            "",
            "1. Send the setup package.",
            "2. Dump Everything and run `verify-setup`.",
            "3. Record every required capture without changing input gain.",
            "4. Run `analyze`.",
            "5. Send the restore bundle, dump Everything, and run `verify-restore`.",
            "",
            "## Captures",
            "",
        ]
        for capture in self.captures:
            marker = "required" if capture.required else "optional"
            lines.append(f"- `{capture.filename}` ({marker}): {capture.instruction}")
        lines.extend(
            [
                "",
                "## Boundary",
                "",
                "The report compares phase-folded analog captures against structural "
                "hypotheses. It does not claim a bit-exact DSP emulation.",
                "",
            ]
        )
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "XtAudioGatePlan":
        plan = cls(
            schema_version=int(data["schema_version"]),
            tool_version=str(data["tool_version"]),
            device_id=int(data["device_id"]),
            seed=int(data["seed"]),
            baseline_sha256=str(data["baseline_sha256"]),
            v7a1_storage_report_sha256=str(data["v7a1_storage_report_sha256"]),
            v7a1_restore_report_sha256=str(data["v7a1_restore_report_sha256"]),
            target_wave_start=int(data["target_wave_start"]),
            target_wavetable_display=int(data["target_wavetable_display"]),
            target_sound_location=str(data["target_sound_location"]),
            setup_sha256=str(data["setup_sha256"]),
            select_safe_sha256=str(data["select_safe_sha256"]),
            select_offset_binary_sha256=str(data["select_offset_binary_sha256"]),
            select_negative_full_scale_sha256=str(
                data["select_negative_full_scale_sha256"]
            ),
            restore_sha256=str(data["restore_sha256"]),
            probes=tuple(XtGateProbe.from_dict(item) for item in data["probes"]),
            sound_changes=tuple(
                {
                    "index": int(item["index"]),
                    "before": int(item["before"]),
                    "after": int(item["after"]),
                }
                for item in data["sound_control"]["changes"]
            ),
            captures=tuple(
                XtAudioCaptureSpec.from_dict(item) for item in data["captures"]
            ),
            recommended_sample_rate=int(
                data["capture_format"]["recommended_sample_rate"]
            ),
            minimum_sample_rate=int(data["capture_format"]["minimum_sample_rate"]),
        )
        if data.get("plan_sha256", plan.plan_sha256) != plan.plan_sha256:
            raise HardwareValidationError("audio-gate plan SHA-256 mismatch")
        return plan

    @classmethod
    def from_json(cls, text: str) -> "XtAudioGatePlan":
        data = json.loads(text)
        if not isinstance(data, Mapping):
            raise HardwareValidationError("audio-gate manifest must be a JSON object")
        return cls.from_dict(data)


@dataclass(frozen=True, slots=True)
class XtAudioGateOutputPaths:
    setup: Path
    select_safe: Path
    select_offset_binary: Path
    select_negative_full_scale: Path
    restore: Path
    manifest_json: Path
    manifest_markdown: Path
    capture_plan_json: Path
    midi_c2: Path
    midi_c3: Path
    midi_c4: Path


@dataclass(frozen=True, slots=True)
class XtAudioGateBuild:
    setup: DumpFile
    select_safe: DumpFile
    select_offset_binary: DumpFile
    select_negative_full_scale: DumpFile
    restore: DumpFile
    plan: XtAudioGatePlan

    @property
    def ready_for_transmission(self) -> bool:
        return (
            _bytes_hash(self.setup.to_bytes()) == self.plan.setup_sha256
            and _bytes_hash(self.restore.to_bytes()) == self.plan.restore_sha256
            and self.setup.to_bytes() != self.restore.to_bytes()
        )

    def write(self, directory: str | Path, *, stem: str = DEFAULT_STEM) -> XtAudioGateOutputPaths:
        if _CAPTURE_STEM.fullmatch(stem) is None:
            raise HardwareValidationError("invalid output stem")
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        midi_dir = output / "midi"
        midi_dir.mkdir(parents=True, exist_ok=True)
        paths = XtAudioGateOutputPaths(
            setup=output / f"{stem}.setup.syx",
            select_safe=output / f"{stem}.select-safe.syx",
            select_offset_binary=output / f"{stem}.select-offset-binary.syx",
            select_negative_full_scale=(
                output / f"{stem}.select-negative-full-scale.syx"
            ),
            restore=output / f"{stem}.restore.syx",
            manifest_json=output / f"{stem}.manifest.json",
            manifest_markdown=output / f"{stem}.manifest.md",
            capture_plan_json=output / f"{stem}.capture-plan.json",
            midi_c2=midi_dir / "MIDI36_4s.mid",
            midi_c3=midi_dir / "MIDI48_4s.mid",
            midi_c4=midi_dir / "MIDI60_4s.mid",
        )
        paths.setup.write_bytes(self.setup.to_bytes())
        paths.select_safe.write_bytes(self.select_safe.to_bytes())
        paths.select_offset_binary.write_bytes(self.select_offset_binary.to_bytes())
        paths.select_negative_full_scale.write_bytes(
            self.select_negative_full_scale.to_bytes()
        )
        paths.restore.write_bytes(self.restore.to_bytes())
        paths.manifest_json.write_text(
            self.plan.to_json(), encoding="utf-8", newline="\n"
        )
        paths.manifest_markdown.write_text(
            self.plan.to_markdown(), encoding="utf-8", newline="\n"
        )
        capture_plan = {
            "schema_version": AUDIO_GATE_SCHEMA_VERSION,
            "audio_gate_plan_sha256": self.plan.plan_sha256,
            "captures": [capture.to_dict() for capture in self.plan.captures],
        }
        paths.capture_plan_json.write_text(
            json.dumps(capture_plan, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        paths.midi_c2.write_bytes(build_note_midi(36))
        paths.midi_c3.write_bytes(build_note_midi(48))
        paths.midi_c4.write_bytes(build_note_midi(60))
        return paths


def build_xt_audio_gate(
    baseline: DumpFile,
    *,
    v7a1_storage_report: Mapping[str, Any],
    v7a1_restore_report: Mapping[str, Any],
    v7a1_storage_report_sha256: str,
    v7a1_restore_report_sha256: str,
    target_wave_start: int = 1247,
    target_wavetable_display: int = 128,
    target_sound_location: str = "B128",
    seed: int = 0x57A,
    tool_version: str = __version__,
    stem: str = DEFAULT_STEM,
) -> XtAudioGateBuild:
    _validate_v7a1_reports(v7a1_storage_report, v7a1_restore_report)
    _require_hash(v7a1_storage_report_sha256, "V7-A.1 storage report SHA-256")
    _require_hash(v7a1_restore_report_sha256, "V7-A.1 restore report SHA-256")
    if baseline.validate():
        raise HardwareValidationError("baseline contains invalid SysEx messages")
    if len(baseline.device_ids) != 1 or not 0 <= baseline.device_ids[0] <= 126:
        raise HardwareValidationError(
            "baseline must contain exactly one direct Device ID"
        )
    if not USER_WAVETABLE_DISPLAY_FIRST <= target_wavetable_display <= USER_WAVETABLE_DISPLAY_LAST:
        raise HardwareValidationError("invalid target User Wavetable display number")
    bank, slot, sound_address = _parse_sound_location(target_sound_location)
    device_id = baseline.device_ids[0]

    wave_gate = build_xt_reconstruction_gate(
        baseline,
        target_wave_start=target_wave_start,
        seed=seed,
        tool_version=tool_version,
    )
    probes = wave_gate.plan.probes
    probe_by_role = {_ROLE_BY_PATTERN[probe.pattern]: probe for probe in probes}

    wavetable_internal = target_wavetable_display - 1
    original_wavetable = _find_unique(
        baseline,
        DumpType.USER_WAVETABLE,
        wavetable_internal,
        label="audio gate baseline",
    )
    original_sound_message = _find_unique(
        baseline,
        DumpType.SOUND,
        sound_address,
        label="audio gate baseline",
    )
    original_sound = SoundProgram.from_message(original_sound_message)
    controlled_sound, sound_changes = build_controlled_audio_sound(
        original_sound,
        device_id=device_id,
        target_bank=bank,
        target_slot=slot,
        target_wavetable_internal=wavetable_internal,
    )
    sound_message = controlled_sound.to_message()

    tables = {
        role: _wavetable_for_probe(
            device_id,
            target_wavetable_display,
            probe.target_wave_number,
        ).to_message()
        for role, probe in probe_by_role.items()
    }
    setup = DumpFile(
        wave_gate.probe_package.messages
        + (tables[XtAudioWaveRole.SAFE], sound_message)
    )
    select_safe = DumpFile((tables[XtAudioWaveRole.SAFE], sound_message))
    select_offset = DumpFile(
        (tables[XtAudioWaveRole.OFFSET_BINARY_EDGE], sound_message)
    )
    select_negfs = DumpFile(
        (tables[XtAudioWaveRole.NEGATIVE_FULL_SCALE_EDGE], sound_message)
    )
    restore = DumpFile(
        wave_gate.restore_bundle.messages
        + (original_wavetable, original_sound_message)
    )

    for label, package in (
        ("setup", setup),
        ("select-safe", select_safe),
        ("select-offset-binary", select_offset),
        ("select-negative-full-scale", select_negfs),
        ("restore", restore),
    ):
        raw = package.to_bytes()
        if DumpFile.from_bytes(raw).to_bytes() != raw:
            raise HardwareValidationError(f"{label} package failed strict round-trip")

    captures = default_capture_plan(stem)
    plan = XtAudioGatePlan(
        schema_version=AUDIO_GATE_SCHEMA_VERSION,
        tool_version=tool_version,
        device_id=device_id,
        seed=seed,
        baseline_sha256=_bytes_hash(baseline.to_bytes()),
        v7a1_storage_report_sha256=v7a1_storage_report_sha256,
        v7a1_restore_report_sha256=v7a1_restore_report_sha256,
        target_wave_start=target_wave_start,
        target_wavetable_display=target_wavetable_display,
        target_sound_location=target_sound_location.upper(),
        setup_sha256=_bytes_hash(setup.to_bytes()),
        select_safe_sha256=_bytes_hash(select_safe.to_bytes()),
        select_offset_binary_sha256=_bytes_hash(select_offset.to_bytes()),
        select_negative_full_scale_sha256=_bytes_hash(select_negfs.to_bytes()),
        restore_sha256=_bytes_hash(restore.to_bytes()),
        probes=probes,
        sound_changes=sound_changes,
        captures=captures,
    )
    result = XtAudioGateBuild(
        setup,
        select_safe,
        select_offset,
        select_negfs,
        restore,
        plan,
    )
    if not result.ready_for_transmission:
        raise HardwareValidationError("audio gate is not ready for transmission")
    return result


@dataclass(frozen=True, slots=True)
class XtAudioSysexEvidence:
    dump_type: str
    address: int
    expected_sha256: str
    observed_sha256: str | None
    exact: bool
    issue: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dump_type": self.dump_type,
            "address": self.address,
            "expected_sha256": self.expected_sha256,
            "observed_sha256": self.observed_sha256,
            "exact": self.exact,
            "issue": self.issue,
        }


@dataclass(frozen=True, slots=True)
class XtAudioSysexAnalysis:
    status: XtAudioGateStatus
    verdict: XtAudioGateVerdict
    evidence: tuple[XtAudioSysexEvidence, ...]
    plan_sha256: str

    @property
    def exact(self) -> bool:
        return bool(self.evidence) and all(item.exact for item in self.evidence)

    def _dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "verdict": self.verdict.value,
            "exact": self.exact,
            "audio_gate_plan_sha256": self.plan_sha256,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @property
    def analysis_sha256(self) -> str:
        return _json_hash(self._dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self._dict(), "analysis_sha256": self.analysis_sha256}

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        ) + "\n"

    def to_markdown(self) -> str:
        lines = [
            f"# {self.verdict.value}",
            "",
            f"- Status: `{self.status.value}`",
            f"- Exact: `{str(self.exact).lower()}`",
            f"- Analysis SHA-256: `{self.analysis_sha256}`",
            "",
            "| Type | Address | Exact | Issue |",
            "|---|---:|:---:|---|",
        ]
        for item in self.evidence:
            lines.append(
                f"| {item.dump_type} | {item.address} | "
                f"{'yes' if item.exact else 'no'} | {item.issue or ''} |"
            )
        lines.append("")
        return "\n".join(lines)


def _verify_messages(
    expected: DumpFile,
    readback: DumpFile,
    plan: XtAudioGatePlan,
    *,
    success_verdict: XtAudioGateVerdict,
    failure_verdict: XtAudioGateVerdict,
) -> XtAudioSysexAnalysis:
    readback_index: dict[tuple[int, int], list[SysExMessage]] = {}
    for message in readback.messages:
        readback_index.setdefault(_message_key(message), []).append(message)
    evidence: list[XtAudioSysexEvidence] = []
    for message in expected.messages:
        key = _message_key(message)
        matches = readback_index.get(key, [])
        expected_raw = message.to_bytes()
        if len(matches) != 1:
            evidence.append(
                XtAudioSysexEvidence(
                    dump_type=DumpType(int(message.dump_type)).name,
                    address=message.address,
                    expected_sha256=_bytes_hash(expected_raw),
                    observed_sha256=None,
                    exact=False,
                    issue=(
                        "missing" if len(matches) == 0 else f"duplicate:{len(matches)}"
                    ),
                )
            )
            continue
        observed_raw = matches[0].to_bytes()
        exact = observed_raw == expected_raw
        evidence.append(
            XtAudioSysexEvidence(
                dump_type=DumpType(int(message.dump_type)).name,
                address=message.address,
                expected_sha256=_bytes_hash(expected_raw),
                observed_sha256=_bytes_hash(observed_raw),
                exact=exact,
                issue=None if exact else "payload_changed",
            )
        )
    passed = bool(evidence) and all(item.exact for item in evidence)
    return XtAudioSysexAnalysis(
        status=XtAudioGateStatus.PASS if passed else XtAudioGateStatus.FAIL,
        verdict=success_verdict if passed else failure_verdict,
        evidence=tuple(evidence),
        plan_sha256=plan.plan_sha256,
    )


def verify_xt_audio_gate_setup(
    expected_setup: DumpFile,
    readback: DumpFile,
    plan: XtAudioGatePlan,
) -> XtAudioSysexAnalysis:
    if _bytes_hash(expected_setup.to_bytes()) != plan.setup_sha256:
        raise HardwareValidationError("setup package hash does not match manifest")
    return _verify_messages(
        expected_setup,
        readback,
        plan,
        success_verdict=XtAudioGateVerdict.SETUP_CONFIRMED,
        failure_verdict=XtAudioGateVerdict.SETUP_FAILED,
    )


def verify_xt_audio_gate_restore(
    expected_restore: DumpFile,
    readback: DumpFile,
    plan: XtAudioGatePlan,
) -> XtAudioSysexAnalysis:
    if _bytes_hash(expected_restore.to_bytes()) != plan.restore_sha256:
        raise HardwareValidationError("restore package hash does not match manifest")
    return _verify_messages(
        expected_restore,
        readback,
        plan,
        success_verdict=XtAudioGateVerdict.RESTORE_CONFIRMED,
        failure_verdict=XtAudioGateVerdict.RESTORE_FAILED,
    )


@dataclass(frozen=True, slots=True)
class XtAudioHypothesisScore:
    hypothesis: XtAudioHypothesis
    combined_score: float
    correlation: float
    magnitude_similarity: float
    phase_shift_bins: int
    polarity: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis.value,
            "combined_score": self.combined_score,
            "correlation": self.correlation,
            "magnitude_similarity": self.magnitude_similarity,
            "phase_shift_bins": self.phase_shift_bins,
            "polarity": self.polarity,
        }


@dataclass(frozen=True, slots=True)
class XtAudioTakeAnalysis:
    capture_id: str
    filename: str
    role: XtAudioWaveRole
    midi_note: int
    note_name: str
    sample_rate: int
    frames: int
    duration_seconds: float
    peak: float
    rms: float
    dc_offset: float
    estimated_frequency_hz: float
    expected_frequency_hz: float
    tuning_ratio: float
    max_harmonic: int
    winner: XtAudioHypothesis
    scores: tuple[XtAudioHypothesisScore, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "filename": self.filename,
            "role": self.role.value,
            "midi_note": self.midi_note,
            "note_name": self.note_name,
            "sample_rate": self.sample_rate,
            "frames": self.frames,
            "duration_seconds": self.duration_seconds,
            "peak": self.peak,
            "rms": self.rms,
            "dc_offset": self.dc_offset,
            "estimated_frequency_hz": self.estimated_frequency_hz,
            "expected_frequency_hz": self.expected_frequency_hz,
            "tuning_ratio": self.tuning_ratio,
            "max_harmonic": self.max_harmonic,
            "winner": self.winner.value,
            "scores": [score.to_dict() for score in self.scores],
        }


@dataclass(frozen=True, slots=True)
class XtAudioGateAnalysis:
    status: XtAudioGateStatus
    verdict: XtAudioGateVerdict
    plan_sha256: str
    required_capture_count: int
    present_capture_count: int
    missing_captures: tuple[str, ...]
    silence_sample_rate: int | None
    silence_peak: float | None
    silence_rms: float | None
    safe_reconstruction_status: str
    negative_full_scale_status: str
    v7_b_allowed_under_safe_range: bool
    tuning_ratio: float | None
    takes: tuple[XtAudioTakeAnalysis, ...]
    warnings: tuple[str, ...]

    def _dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "verdict": self.verdict.value,
            "audio_gate_plan_sha256": self.plan_sha256,
            "required_capture_count": self.required_capture_count,
            "present_capture_count": self.present_capture_count,
            "missing_captures": list(self.missing_captures),
            "silence": {
                "sample_rate": self.silence_sample_rate,
                "peak": self.silence_peak,
                "rms": self.silence_rms,
            },
            "safe_reconstruction_status": self.safe_reconstruction_status,
            "negative_full_scale_status": self.negative_full_scale_status,
            "v7_b_allowed_under_safe_range": self.v7_b_allowed_under_safe_range,
            "safe_optimizer_sample_range": [SAFE_OPTIMIZER_MIN, SAFE_OPTIMIZER_MAX],
            "tuning_ratio": self.tuning_ratio,
            "takes": [take.to_dict() for take in self.takes],
            "warnings": list(self.warnings),
            "evidence_boundary": (
                "Analog phase-folded captures can support or conflict with the "
                "documented structure, but cannot prove bit-exact internal DSP samples."
            ),
        }

    @property
    def analysis_sha256(self) -> str:
        return _json_hash(self._dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self._dict(), "analysis_sha256": self.analysis_sha256}

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        ) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# CODE V7-A.2 — audio analysis",
            "",
            f"- Status: `{self.status.value}`",
            f"- Verdict: `{self.verdict.value}`",
            f"- Safe reconstruction: `{self.safe_reconstruction_status}`",
            f"- Negative-full-scale edge: `{self.negative_full_scale_status}`",
            f"- V7-B allowed under -127..127: `{str(self.v7_b_allowed_under_safe_range).lower()}`",
            f"- Analysis SHA-256: `{self.analysis_sha256}`",
            "",
        ]
        if self.missing_captures:
            lines.append("## Missing captures")
            lines.append("")
            lines.extend(f"- `{name}`" for name in self.missing_captures)
            lines.append("")
        lines.extend(
            [
                "## Take results",
                "",
                "| Capture | Role | Note | f0 Hz | Winner | Score | Correlation |",
                "|---|---|---|---:|---|---:|---:|",
            ]
        )
        for take in self.takes:
            winner = take.scores[0]
            lines.append(
                f"| {take.capture_id} | {take.role.value} | {take.note_name} | "
                f"{take.estimated_frequency_hz:.5f} | {take.winner.value} | "
                f"{winner.combined_score:.6f} | {winner.correlation:.6f} |"
            )
        if self.warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {warning}" for warning in self.warnings)
        lines.extend(
            [
                "",
                "## Boundary",
                "",
                "This report ranks structural hypotheses after phase folding and "
                "band-limiting. It is not a bit-exact DSP or DAC identification.",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class XtAudioAnalysisOutputPaths:
    json_report: Path
    markdown_report: Path


@dataclass(frozen=True, slots=True)
class XtAudioGateAnalysisResult:
    analysis: XtAudioGateAnalysis

    def write(
        self,
        directory: str | Path,
        *,
        stem: str = f"{DEFAULT_STEM}.analysis",
    ) -> XtAudioAnalysisOutputPaths:
        if _CAPTURE_STEM.fullmatch(stem) is None:
            raise HardwareValidationError("invalid analysis stem")
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        paths = XtAudioAnalysisOutputPaths(
            json_report=output / f"{stem}.json",
            markdown_report=output / f"{stem}.md",
        )
        paths.json_report.write_text(
            self.analysis.to_json(), encoding="utf-8", newline="\n"
        )
        paths.markdown_report.write_text(
            self.analysis.to_markdown(), encoding="utf-8", newline="\n"
        )
        return paths


def midi_note_frequency(midi_note: int) -> float:
    return 440.0 * 2.0 ** ((midi_note - 69) / 12.0)


def _stable_segment(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    if samples.ndim != 1:
        raise HardwareValidationError("audio samples must be mono")
    if samples.size < int(sample_rate * 1.5):
        raise HardwareValidationError("capture must contain at least 1.5 seconds")
    start = int(sample_rate * 0.50)
    end = samples.size - int(sample_rate * 0.25)
    if end <= start:
        raise HardwareValidationError("capture is too short after trimming")
    segment = samples[start:end]
    max_frames = int(sample_rate * 2.5)
    if segment.size > max_frames:
        offset = (segment.size - max_frames) // 2
        segment = segment[offset : offset + max_frames]
    return segment


def _load_mono(path: Path, minimum_sample_rate: int) -> tuple[np.ndarray, int]:
    data, sample_rate = sf.read(path, dtype="float64", always_2d=True)
    if data.shape[1] != 1:
        raise HardwareValidationError(
            f"{path.name} must be mono; found {data.shape[1]} channels"
        )
    if sample_rate < minimum_sample_rate:
        raise HardwareValidationError(
            f"{path.name} sample rate {sample_rate} is below {minimum_sample_rate} Hz"
        )
    samples = np.asarray(data[:, 0], dtype=np.float64)
    if samples.size == 0 or not np.isfinite(samples).all():
        raise HardwareValidationError(f"{path.name} contains invalid audio")
    return samples, int(sample_rate)


def _estimate_frequency_autocorrelation(
    samples: np.ndarray,
    sample_rate: int,
    expected_frequency: float,
    *,
    ratio_span: float = 0.06,
) -> float:
    centered = samples - float(np.mean(samples))
    if float(np.sqrt(np.mean(centered * centered))) <= 1e-9:
        raise HardwareValidationError("capture is silent")
    n = centered.size
    nfft = 1 << (2 * n - 1).bit_length()
    spectrum = np.fft.rfft(centered, n=nfft)
    autocorrelation = np.fft.irfft(spectrum * np.conj(spectrum), n=nfft)[:n]
    overlap = np.arange(n, 0, -1, dtype=np.float64)
    autocorrelation = autocorrelation / overlap
    min_frequency = expected_frequency * (1.0 - ratio_span)
    max_frequency = expected_frequency * (1.0 + ratio_span)
    min_lag = max(2, int(math.floor(sample_rate / max_frequency)))
    max_lag = min(n - 2, int(math.ceil(sample_rate / min_frequency)))
    if max_lag <= min_lag:
        raise HardwareValidationError("invalid autocorrelation lag range")
    local = autocorrelation[min_lag : max_lag + 1]
    lag = min_lag + int(np.argmax(local))
    delta = 0.0
    if 1 <= lag < n - 1:
        y0, y1, y2 = autocorrelation[lag - 1 : lag + 2]
        denominator = y0 - 2.0 * y1 + y2
        if abs(denominator) > 1e-18:
            delta = 0.5 * (y0 - y2) / denominator
            delta = float(np.clip(delta, -0.5, 0.5))
    return float(sample_rate / (lag + delta))


def _phase_fold(
    samples: np.ndarray,
    sample_rate: int,
    frequency: float,
    bins: int = PHASE_BINS,
) -> np.ndarray:
    centered = samples - float(np.mean(samples))
    phase_positions = (np.arange(centered.size, dtype=np.float64) * frequency / sample_rate) % 1.0
    positions = phase_positions * bins
    lower = np.floor(positions).astype(np.int64) % bins
    fraction = positions - np.floor(positions)
    upper = (lower + 1) % bins
    weighted = np.zeros(bins, dtype=np.float64)
    weights = np.zeros(bins, dtype=np.float64)
    np.add.at(weighted, lower, centered * (1.0 - fraction))
    np.add.at(weights, lower, 1.0 - fraction)
    np.add.at(weighted, upper, centered * fraction)
    np.add.at(weights, upper, fraction)
    if np.any(weights <= 0):
        raise HardwareValidationError("phase folding left empty bins")
    folded = weighted / weights
    folded -= float(np.mean(folded))
    rms = float(np.sqrt(np.mean(folded * folded)))
    if rms <= 1e-12:
        raise HardwareValidationError("phase-folded cycle is silent")
    return folded / rms


def _reconstruct_edge(stored: Sequence[int], mode: str) -> np.ndarray:
    second: list[float] = []
    for sample in reversed(tuple(int(x) for x in stored)):
        if sample != -128:
            second.append(float(-sample))
        elif mode == "positive":
            second.append(127.0)
        elif mode == "wrap":
            second.append(-128.0)
        elif mode == "zero":
            second.append(0.0)
        else:
            raise HardwareValidationError(f"unknown edge mode: {mode}")
    return np.asarray(tuple(stored) + tuple(second), dtype=np.float64)


def _hypothesis_cycles(probe: XtGateProbe, role: XtAudioWaveRole) -> dict[XtAudioHypothesis, np.ndarray]:
    first = np.asarray(probe.stored_samples, dtype=np.float64)
    if role is XtAudioWaveRole.SAFE:
        return {
            XtAudioHypothesis.DOCUMENTED_REVERSE_NEGATE: np.concatenate(
                [first, -first[::-1]]
            ),
            XtAudioHypothesis.REPEAT_FIRST_HALF: np.concatenate([first, first]),
            XtAudioHypothesis.MIRROR_FIRST_HALF: np.concatenate(
                [first, first[::-1]]
            ),
            XtAudioHypothesis.NEGATE_FIRST_HALF: np.concatenate([first, -first]),
            XtAudioHypothesis.ZERO_FILL_SECOND_HALF: np.concatenate(
                [first, np.zeros_like(first)]
            ),
        }
    return {
        XtAudioHypothesis.POSITIVE_NEGATIVE_FULL_SCALE: _reconstruct_edge(
            probe.stored_samples, "positive"
        ),
        XtAudioHypothesis.WRAP_NEGATIVE_FULL_SCALE: _reconstruct_edge(
            probe.stored_samples, "wrap"
        ),
        XtAudioHypothesis.ZERO_NEGATIVE_FULL_SCALE: _reconstruct_edge(
            probe.stored_samples, "zero"
        ),
        XtAudioHypothesis.REPEAT_FIRST_HALF: np.concatenate([first, first]),
    }


def _bandlimit_cycle(cycle: np.ndarray, max_harmonic: int) -> np.ndarray:
    centered = np.asarray(cycle, dtype=np.float64) - float(np.mean(cycle))
    spectrum = np.fft.rfft(centered)
    if max_harmonic + 1 < spectrum.size:
        spectrum[max_harmonic + 1 :] = 0
    filtered = np.fft.irfft(spectrum, n=centered.size)
    filtered -= float(np.mean(filtered))
    rms = float(np.sqrt(np.mean(filtered * filtered)))
    if rms <= 1e-12:
        raise HardwareValidationError("hypothesis has no measurable energy")
    return filtered / rms


def _score_cycle(
    observed: np.ndarray,
    expected: np.ndarray,
    hypothesis: XtAudioHypothesis,
    max_harmonic: int,
) -> XtAudioHypothesisScore:
    expected_filtered = _bandlimit_cycle(expected, max_harmonic)
    observed_norm = observed / float(np.sqrt(np.mean(observed * observed)))
    cross = np.fft.ifft(
        np.fft.fft(observed_norm) * np.conj(np.fft.fft(expected_filtered))
    ).real / observed_norm.size
    shift = int(np.argmax(np.abs(cross)))
    signed_correlation = float(cross[shift])
    polarity = 1 if signed_correlation >= 0 else -1
    correlation = abs(signed_correlation)

    observed_magnitude = np.abs(np.fft.rfft(observed_norm))[1 : max_harmonic + 1]
    expected_magnitude = np.abs(np.fft.rfft(expected_filtered))[1 : max_harmonic + 1]
    denominator = float(
        np.linalg.norm(observed_magnitude) * np.linalg.norm(expected_magnitude)
    )
    magnitude_similarity = (
        0.0
        if denominator <= 1e-18
        else float(np.dot(observed_magnitude, expected_magnitude) / denominator)
    )
    combined = float((correlation + magnitude_similarity) / 2.0)
    return XtAudioHypothesisScore(
        hypothesis=hypothesis,
        combined_score=combined,
        correlation=correlation,
        magnitude_similarity=magnitude_similarity,
        phase_shift_bins=shift,
        polarity=polarity,
    )


def _analyze_take(
    path: Path,
    spec: XtAudioCaptureSpec,
    probe: XtGateProbe,
    *,
    minimum_sample_rate: int,
    tuning_ratio: float | None,
) -> XtAudioTakeAnalysis:
    if spec.role is None or spec.midi_note is None or spec.note_name is None:
        raise HardwareValidationError("audio take specification is incomplete")
    samples, sample_rate = _load_mono(path, minimum_sample_rate)
    segment = _stable_segment(samples, sample_rate)
    dc_offset = float(np.mean(segment))
    centered = segment - dc_offset
    peak = float(np.max(np.abs(centered)))
    rms = float(np.sqrt(np.mean(centered * centered)))
    expected_frequency = midi_note_frequency(spec.midi_note)
    if tuning_ratio is None:
        estimated_frequency = _estimate_frequency_autocorrelation(
            centered, sample_rate, expected_frequency
        )
    else:
        center_frequency = expected_frequency * tuning_ratio
        estimated_frequency = _estimate_frequency_autocorrelation(
            centered,
            sample_rate,
            center_frequency,
            ratio_span=0.012,
        )
    folded = _phase_fold(centered, sample_rate, estimated_frequency)
    max_harmonic = max(
        3,
        min(48, 63, int((sample_rate * 0.45) // estimated_frequency)),
    )
    scores = tuple(
        sorted(
            (
                _score_cycle(folded, cycle, hypothesis, max_harmonic)
                for hypothesis, cycle in _hypothesis_cycles(probe, spec.role).items()
            ),
            key=lambda item: (
                item.combined_score,
                item.correlation,
                item.magnitude_similarity,
                item.hypothesis.value,
            ),
            reverse=True,
        )
    )
    return XtAudioTakeAnalysis(
        capture_id=spec.capture_id,
        filename=spec.filename,
        role=spec.role,
        midi_note=spec.midi_note,
        note_name=spec.note_name,
        sample_rate=sample_rate,
        frames=int(samples.size),
        duration_seconds=float(samples.size / sample_rate),
        peak=peak,
        rms=rms,
        dc_offset=dc_offset,
        estimated_frequency_hz=estimated_frequency,
        expected_frequency_hz=expected_frequency,
        tuning_ratio=float(estimated_frequency / expected_frequency),
        max_harmonic=max_harmonic,
        winner=scores[0].hypothesis,
        scores=scores,
    )


def analyze_xt_audio_gate(
    captures_directory: str | Path,
    plan: XtAudioGatePlan,
) -> XtAudioGateAnalysisResult:
    directory = Path(captures_directory)
    required = tuple(capture for capture in plan.captures if capture.required)
    missing = tuple(
        capture.filename
        for capture in required
        if not (directory / capture.filename).is_file()
    )
    present_count = len(required) - len(missing)
    if missing:
        return XtAudioGateAnalysisResult(
            XtAudioGateAnalysis(
                status=XtAudioGateStatus.INCOMPLETE,
                verdict=XtAudioGateVerdict.CAPTURES_INCOMPLETE,
                plan_sha256=plan.plan_sha256,
                required_capture_count=len(required),
                present_capture_count=present_count,
                missing_captures=missing,
                silence_sample_rate=None,
                silence_peak=None,
                silence_rms=None,
                safe_reconstruction_status="not_analyzed",
                negative_full_scale_status="not_analyzed",
                v7_b_allowed_under_safe_range=False,
                tuning_ratio=None,
                takes=(),
                warnings=("Record every required file before analysis.",),
            )
        )

    probe_by_role = {
        _ROLE_BY_PATTERN[probe.pattern]: probe for probe in plan.probes
    }
    silence_spec = next(capture for capture in required if capture.role is None)
    silence, silence_rate = _load_mono(
        directory / silence_spec.filename, plan.minimum_sample_rate
    )
    silence_segment = _stable_segment(silence, silence_rate)
    silence_dc = float(np.mean(silence_segment))
    silence_centered = silence_segment - silence_dc
    silence_peak = float(np.max(np.abs(silence_centered)))
    silence_rms = float(np.sqrt(np.mean(silence_centered * silence_centered)))

    safe_specs = tuple(
        capture for capture in required if capture.role is XtAudioWaveRole.SAFE
    )
    safe_takes = tuple(
        _analyze_take(
            directory / spec.filename,
            spec,
            probe_by_role[XtAudioWaveRole.SAFE],
            minimum_sample_rate=plan.minimum_sample_rate,
            tuning_ratio=None,
        )
        for spec in safe_specs
    )
    tuning_ratio = float(np.median([take.tuning_ratio for take in safe_takes]))

    edge_specs = tuple(
        capture
        for capture in required
        if capture.role in {
            XtAudioWaveRole.OFFSET_BINARY_EDGE,
            XtAudioWaveRole.NEGATIVE_FULL_SCALE_EDGE,
        }
    )
    edge_takes = tuple(
        _analyze_take(
            directory / spec.filename,
            spec,
            probe_by_role[spec.role],  # type: ignore[index]
            minimum_sample_rate=plan.minimum_sample_rate,
            tuning_ratio=tuning_ratio,
        )
        for spec in edge_specs
    )
    takes = safe_takes + edge_takes

    safe_winners = tuple(take.winner for take in safe_takes)
    documented_count = sum(
        winner is XtAudioHypothesis.DOCUMENTED_REVERSE_NEGATE
        for winner in safe_winners
    )
    if documented_count == len(safe_winners):
        safe_status = "documented_reverse_negate_consistent_unique_best"
        safe_passed = True
        safe_conflict = False
    elif documented_count == 0 and len(set(safe_winners)) == 1:
        safe_status = f"consistent_conflict:{safe_winners[0].value}"
        safe_passed = False
        safe_conflict = True
    else:
        safe_status = "inconclusive_mixed_winners"
        safe_passed = False
        safe_conflict = False

    # The -128 edge is a very small perturbation relative to a 128-point
    # analog cycle. Individual notes can therefore exchange first and second
    # place after oscillator band-limiting or capture noise. Aggregate the
    # normalized take scores across every edge capture instead of requiring
    # every individual take to have the same winner. A minimum mean-score
    # margin keeps close analog ties explicitly inconclusive.
    edge_hypotheses = (
        XtAudioHypothesis.POSITIVE_NEGATIVE_FULL_SCALE,
        XtAudioHypothesis.WRAP_NEGATIVE_FULL_SCALE,
        XtAudioHypothesis.ZERO_NEGATIVE_FULL_SCALE,
        XtAudioHypothesis.REPEAT_FIRST_HALF,
    )
    aggregate_edge_scores = {
        hypothesis: float(
            np.mean(
                [
                    next(
                        score.combined_score
                        for score in take.scores
                        if score.hypothesis is hypothesis
                    )
                    for take in edge_takes
                ]
            )
        )
        for hypothesis in edge_hypotheses
    }
    ranked_edge = tuple(
        sorted(
            aggregate_edge_scores.items(),
            key=lambda item: (item[1], item[0].value),
            reverse=True,
        )
    )
    edge_margin = ranked_edge[0][1] - ranked_edge[1][1]
    if edge_margin >= 0.003:
        edge_winner = ranked_edge[0][0]
        edge_status = edge_winner.value
    else:
        edge_winner = None
        edge_status = (
            "inconclusive_aggregate_margin:"
            f"{ranked_edge[0][0].value}={ranked_edge[0][1]:.6f},"
            f"{ranked_edge[1][0].value}={ranked_edge[1][1]:.6f}"
        )

    warnings: list[str] = []
    if silence_rms > 0:
        for take in takes:
            if take.rms <= silence_rms * 10.0:
                warnings.append(
                    f"{take.filename}: signal RMS is less than 20 dB above measured silence"
                )
            if take.peak >= 0.999:
                warnings.append(f"{take.filename}: digital clipping is possible")
    sample_rates = {take.sample_rate for take in takes}
    if len(sample_rates) > 1 or (sample_rates and silence_rate not in sample_rates):
        warnings.append("Capture sample rates are not identical across the corpus")
    if any(take.sample_rate < plan.recommended_sample_rate for take in takes):
        warnings.append(
            "One or more captures use less than the recommended 96 kHz sample rate"
        )

    if safe_passed:
        if edge_winner is XtAudioHypothesis.POSITIVE_NEGATIVE_FULL_SCALE:
            verdict = XtAudioGateVerdict.SAFE_RECONSTRUCTION_SUPPORTED_EDGE_POSITIVE
            edge_label = "positive_edge_compatible_(+127_or_internal_+128_not_distinguished)"
        elif edge_winner is XtAudioHypothesis.WRAP_NEGATIVE_FULL_SCALE:
            verdict = XtAudioGateVerdict.SAFE_RECONSTRUCTION_SUPPORTED_EDGE_WRAP
            edge_label = "wrap_to_negative_full_scale_compatible"
        elif edge_winner is XtAudioHypothesis.ZERO_NEGATIVE_FULL_SCALE:
            verdict = XtAudioGateVerdict.SAFE_RECONSTRUCTION_SUPPORTED_EDGE_ZERO
            edge_label = "zero_edge_compatible"
        else:
            verdict = XtAudioGateVerdict.SAFE_RECONSTRUCTION_SUPPORTED_EDGE_INCONCLUSIVE
            edge_label = edge_status
        status = XtAudioGateStatus.PASS
    elif safe_conflict:
        verdict = XtAudioGateVerdict.SAFE_RECONSTRUCTION_CONFLICT
        status = XtAudioGateStatus.FAIL
        edge_label = edge_status
    else:
        verdict = XtAudioGateVerdict.SAFE_RECONSTRUCTION_INCONCLUSIVE
        status = XtAudioGateStatus.INCONCLUSIVE
        edge_label = edge_status

    return XtAudioGateAnalysisResult(
        XtAudioGateAnalysis(
            status=status,
            verdict=verdict,
            plan_sha256=plan.plan_sha256,
            required_capture_count=len(required),
            present_capture_count=present_count,
            missing_captures=(),
            silence_sample_rate=silence_rate,
            silence_peak=silence_peak,
            silence_rms=silence_rms,
            safe_reconstruction_status=safe_status,
            negative_full_scale_status=edge_label,
            v7_b_allowed_under_safe_range=safe_passed,
            tuning_ratio=tuning_ratio,
            takes=takes,
            warnings=tuple(warnings),
        )
    )
