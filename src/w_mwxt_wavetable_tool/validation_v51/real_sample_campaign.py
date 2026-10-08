from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
import struct
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import numpy.typing as npt
import soundfile as sf

from ..analysis.code_v6 import analyze_audio_source_code_v6
from ..audio.importers import import_audio
from ..constants import DumpType
from ..destinations import SoundDestination, UserWavetableDestination
from ..dump import DumpFile
from ..errors import AnalysisError
from ..models import SoundProgram, UserWave, UserWavetable
from ..xt.audio_gate import build_controlled_audio_sound
from ..xt.projection import project_code_v6_analysis_xt_native, reconstruct_xt_native
from ..xt.trajectory import build_xt_wavetable_trajectory_document
from ..xt.trajectory_qc import analyze_xt_trajectory_qc_documents

REAL_SAMPLE_CAMPAIGN_SCHEMA_VERSION = 1
DEFAULT_FIXED_POSITIONS = (0, 10, 20, 30, 40, 50, 60)
DEFAULT_FIXED_NOTES = (48, 60, 72)
DEFAULT_SAMPLE_RATE = 96_000
DEFAULT_MIDI_DIVISION = 480
DEFAULT_TEMPO_US_PER_QUARTER = 500_000


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _safe_stem(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "._-" else "_" for character in value)
    cleaned = cleaned.strip("._-")
    if not cleaned:
        raise ValueError("campaign stem must contain at least one safe character")
    return cleaned[:48]


def _varlen(value: int) -> bytes:
    if value < 0:
        raise ValueError("MIDI delta time cannot be negative")
    buffer = value & 0x7F
    output = bytearray((buffer,))
    value >>= 7
    while value:
        buffer = (value & 0x7F) | 0x80
        output.insert(0, buffer)
        value >>= 7
    return bytes(output)


def _seconds_to_ticks(seconds: float) -> int:
    ticks_per_second = DEFAULT_MIDI_DIVISION * 1_000_000 / DEFAULT_TEMPO_US_PER_QUARTER
    return int(round(seconds * ticks_per_second))


def _smf_type0(events: Sequence[tuple[float, int, bytes]]) -> bytes:
    """Build a deterministic SMF type 0.

    Events are `(seconds, stable_order, raw_midi_bytes)`. Only generated notes and
    CC71 are used by this campaign. No SysEx is embedded in the MIDI files.
    """

    ordered = sorted(events, key=lambda item: (item[0], item[1], item[2]))
    track = bytearray()
    # Tempo 120 BPM and 4/4 time signature.
    track += _varlen(0) + b"\xFF\x51\x03" + DEFAULT_TEMPO_US_PER_QUARTER.to_bytes(3, "big")
    track += _varlen(0) + b"\xFF\x58\x04\x04\x02\x18\x08"
    previous_tick = 0
    for seconds, _, message in ordered:
        tick = _seconds_to_ticks(seconds)
        if tick < previous_tick:
            raise ValueError("MIDI events are not time ordered")
        track += _varlen(tick - previous_tick)
        track += message
        previous_tick = tick
    track += _varlen(0) + b"\xFF\x2F\x00"
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, DEFAULT_MIDI_DIVISION)
    return header + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


def build_fixed_position_midi(
    *,
    positions: Sequence[int] = DEFAULT_FIXED_POSITIONS,
    notes: Sequence[int] = DEFAULT_FIXED_NOTES,
    velocity: int = 100,
    initial_silence: float = 2.0,
    note_duration: float = 1.5,
    gap_duration: float = 0.5,
    final_silence: float = 2.0,
) -> tuple[bytes, dict[str, object]]:
    if any(not 0 <= value <= 60 for value in positions):
        raise ValueError("fixed positions must remain in the editable XT range 0..60")
    if any(not 1 <= note <= 127 for note in notes):
        raise ValueError("MIDI notes must be in 1..127")
    if not 1 <= velocity <= 127:
        raise ValueError("velocity must be in 1..127")
    events: list[tuple[float, int, bytes]] = []
    blocks: list[dict[str, object]] = []
    cursor = initial_silence
    order = 0
    for position in positions:
        for note in notes:
            # Set Startwave before each note; this makes every block independently
            # identifiable even after manual DAW relocation.
            events.append((cursor, order, bytes((0xB0, 71, position))))
            order += 1
            note_start = cursor + 0.10
            note_end = note_start + note_duration
            events.append((note_start, order, bytes((0x90, note, velocity))))
            order += 1
            events.append((note_end, order, bytes((0x80, note, 0))))
            order += 1
            blocks.append(
                {
                    "index": len(blocks) + 1,
                    "position": position,
                    "midi_note": note,
                    "velocity": velocity,
                    "note_start_seconds": note_start,
                    "note_end_seconds": note_end,
                    "analysis_start_seconds": note_start + min(0.30, note_duration * 0.25),
                    "analysis_end_seconds": note_end - min(0.20, note_duration * 0.20),
                }
            )
            cursor = note_end + gap_duration
    duration = cursor + final_silence
    manifest = {
        "schema_version": 1,
        "kind": "fixed_positions",
        "controller": 71,
        "positions": list(positions),
        "notes": list(notes),
        "velocity": velocity,
        "duration_seconds": duration,
        "blocks": blocks,
        "midi_policy": {
            "allowed_cc": [71],
            "contains_sysex": False,
            "contains_program_change": False,
            "contains_all_notes_off": False,
        },
    }
    midi = _smf_type0(events)
    manifest["midi_sha256"] = sha256(midi).hexdigest()
    return midi, manifest


def build_sweep_midi(
    *,
    note: int = 60,
    velocity: int = 100,
    initial_silence: float = 2.0,
    step_seconds: float = 0.20,
    endpoint_hold: float = 0.60,
    final_silence: float = 2.0,
) -> tuple[bytes, dict[str, object]]:
    if not 1 <= note <= 127:
        raise ValueError("MIDI note must be in 1..127")
    if step_seconds < 0.05:
        raise ValueError("sweep step must be at least 50 ms")
    events: list[tuple[float, int, bytes]] = []
    schedule: list[dict[str, object]] = []
    order = 0
    cursor = initial_silence
    events.append((cursor, order, bytes((0xB0, 71, 0))))
    order += 1
    note_start = cursor + 0.10
    events.append((note_start, order, bytes((0x90, note, velocity))))
    order += 1
    cursor = note_start
    values = tuple(range(0, 61)) + tuple(range(59, -1, -1))
    for index, value in enumerate(values):
        if index == 61:
            cursor += endpoint_hold
        events.append((cursor, order, bytes((0xB0, 71, value))))
        order += 1
        schedule.append({"time_seconds": cursor, "position": value})
        cursor += step_seconds
    note_end = cursor + 0.20
    events.append((note_end, order, bytes((0x80, note, 0))))
    duration = note_end + final_silence
    manifest = {
        "schema_version": 1,
        "kind": "forward_reverse_sweep",
        "controller": 71,
        "note": note,
        "velocity": velocity,
        "step_seconds": step_seconds,
        "endpoint_hold_seconds": endpoint_hold,
        "note_start_seconds": note_start,
        "note_end_seconds": note_end,
        "duration_seconds": duration,
        "schedule": schedule,
        "midi_policy": {
            "allowed_cc": [71],
            "contains_sysex": False,
            "contains_program_change": False,
            "contains_all_notes_off": False,
        },
    }
    midi = _smf_type0(events)
    manifest["midi_sha256"] = sha256(midi).hexdigest()
    return midi, manifest


def _midi_frequency(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def _lookup(wave: npt.NDArray[np.float64], phase: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    position = np.mod(phase, 1.0) * wave.size
    left = np.floor(position).astype(np.int64) % wave.size
    fraction = position - np.floor(position)
    right = (left + 1) % wave.size
    return wave[left] * (1.0 - fraction) + wave[right] * fraction


def _fade(samples: npt.NDArray[np.float64], sample_rate: int, seconds: float = 0.01) -> None:
    count = min(int(round(sample_rate * seconds)), samples.size // 2)
    if count <= 0:
        return
    ramp = np.sin(np.linspace(0.0, math.pi / 2.0, count, endpoint=True)) ** 2
    samples[:count] *= ramp
    samples[-count:] *= ramp[::-1]


def _trajectory_waveforms(trajectory: object) -> tuple[npt.NDArray[np.float64], ...]:
    slots = tuple(getattr(trajectory, "slots"))
    if len(slots) != 61:
        raise AnalysisError("real-sample campaign requires exactly 61 trajectory slots")
    result = []
    for slot in slots:
        stored = tuple(int(value) for value in getattr(slot, "stored_samples"))
        reconstructed = np.asarray(reconstruct_xt_native(stored), dtype=np.float64) / 127.0
        result.append(reconstructed)
    return tuple(result)


def render_fixed_position_preview(
    trajectory: object,
    manifest: Mapping[str, object],
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    peak: float = 0.5,
) -> npt.NDArray[np.float64]:
    duration = float(manifest["duration_seconds"])
    output = np.zeros(int(math.ceil(duration * sample_rate)), dtype=np.float64)
    waveforms = _trajectory_waveforms(trajectory)
    blocks = manifest.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("fixed MIDI manifest has no blocks")
    for block in blocks:
        if not isinstance(block, Mapping):
            raise ValueError("invalid fixed MIDI block")
        position = int(block["position"])
        note = int(block["midi_note"])
        start = int(round(float(block["note_start_seconds"]) * sample_rate))
        end = int(round(float(block["note_end_seconds"]) * sample_rate))
        count = max(0, end - start)
        time = np.arange(count, dtype=np.float64) / sample_rate
        phase = _midi_frequency(note) * time
        segment = _lookup(waveforms[position], phase)
        _fade(segment, sample_rate)
        output[start:end] = segment
    maximum = float(np.max(np.abs(output)))
    if maximum > 0.0:
        output *= peak / maximum
    return output


def render_sweep_preview(
    trajectory: object,
    manifest: Mapping[str, object],
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    peak: float = 0.5,
) -> npt.NDArray[np.float64]:
    duration = float(manifest["duration_seconds"])
    output = np.zeros(int(math.ceil(duration * sample_rate)), dtype=np.float64)
    waveforms = _trajectory_waveforms(trajectory)
    note_start = float(manifest["note_start_seconds"])
    note_end = float(manifest["note_end_seconds"])
    schedule = manifest.get("schedule")
    if not isinstance(schedule, list) or not schedule:
        raise ValueError("sweep MIDI manifest has no schedule")
    start_sample = int(round(note_start * sample_rate))
    end_sample = min(output.size, int(round(note_end * sample_rate)))
    count = max(0, end_sample - start_sample)
    times = note_start + np.arange(count, dtype=np.float64) / sample_rate
    schedule_times = np.asarray([float(item["time_seconds"]) for item in schedule], dtype=np.float64)
    schedule_positions = np.asarray([int(item["position"]) for item in schedule], dtype=np.int64)
    indexes = np.searchsorted(schedule_times, times, side="right") - 1
    indexes = np.clip(indexes, 0, schedule_positions.size - 1)
    positions = schedule_positions[indexes]
    phase = _midi_frequency(int(manifest["note"])) * (times - note_start)
    segment = np.empty(count, dtype=np.float64)
    for position in np.unique(positions):
        mask = positions == position
        segment[mask] = _lookup(waveforms[int(position)], phase[mask])
    _fade(segment, sample_rate)
    output[start_sample:end_sample] = segment
    maximum = float(np.max(np.abs(output)))
    if maximum > 0.0:
        output *= peak / maximum
    return output


@dataclass(frozen=True, slots=True)
class _V51PackagePaths:
    package_sysex: Path
    user_waves_sysex: Path
    user_wavetable_sysex: Path
    sound_sysex: Path
    restore_sysex: Path
    analysis_json: Path
    analysis_markdown: Path
    sha256_index: Path


@dataclass(frozen=True, slots=True)
class SourceCampaignArtifacts:
    root: Path
    manifest_path: Path
    package_path: Path
    restore_path: Path
    fixed_midi_path: Path
    sweep_midi_path: Path
    fixed_preview_path: Path
    sweep_preview_path: Path


def build_source_campaign(
    source_wav: str | Path,
    baseline_everything: str | Path,
    output_directory: str | Path,
    *,
    campaign_stem: str,
    user_wave_start: int,
    wavetable_display_number: int,
    sound_destination: str,
    template_sound_destination: str | None = None,
    sound_name: str,
    top_n: int = 16,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> SourceCampaignArtifacts:
    """Run the real source through the stable V6/V7 chain and build hardware evidence.

    This is intentionally a V7 N+2 hardware carrier. The current V8-K source tree
    materializes N WAVD + WCTD and explicitly leaves SNDD integration to a later
    stage. The generated evidence links back to the same source, projection and
    trajectory hashes and is designed to drive V8 algorithm changes rather than
    to claim that V8-K already implements the missing Sound layer.
    """

    stem = _safe_stem(campaign_stem)
    source_path = Path(source_wav).expanduser().resolve(strict=True)
    baseline_path = Path(baseline_everything).expanduser().resolve(strict=True)
    root = Path(output_directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    inputs = root / "inputs"
    reports = root / "reports"
    packages = root / "packages"
    midi = root / "midi"
    previews = root / "previews"
    captures = root / "captures"
    for directory in (inputs, reports, packages, midi, previews, captures):
        directory.mkdir(parents=True, exist_ok=True)

    source_copy = inputs / f"{stem}.source{source_path.suffix.lower() or '.wav'}"
    baseline_copy = inputs / f"{stem}.baseline_everything.syx"
    shutil.copyfile(source_path, source_copy)
    shutil.copyfile(baseline_path, baseline_copy)
    if _file_hash(source_copy) != _file_hash(source_path):
        raise RuntimeError("campaign source copy is not byte-identical")
    if _file_hash(baseline_copy) != _file_hash(baseline_path):
        raise RuntimeError("campaign baseline copy is not byte-identical")

    audio = import_audio(source_copy)
    code_v6 = analyze_audio_source_code_v6(
        audio,
        top_n=top_n,
        reconstruction_kwargs={
            "target_sample_count": 128,
            "remove_dc": True,
            "normalization_peak": 0.95,
        },
    )
    projection = project_code_v6_analysis_xt_native(code_v6)
    trajectory = build_xt_wavetable_trajectory_document(projection.to_dict())
    trajectory_document = trajectory.to_dict()
    duplicate_pairs = list(trajectory_document.get("duplicate_adjacent_slot_pairs", ()))

    code_v6_path = reports / f"{stem}.code_v6.json"
    projection_path = reports / f"{stem}.xt_projection.json"
    trajectory_path = reports / f"{stem}.xt_trajectory.json"
    _write_json(
        code_v6_path,
        {
            "audio": audio.to_summary(),
            "code_v6_analysis": code_v6.to_dict(),
        },
    )
    _write_json(projection_path, projection.to_dict())
    _write_json(trajectory_path, trajectory_document)

    # V7-D deliberately rejects adjacent duplicate slots. Real low-complexity sources
    # (notably sub/bass material) can quantize to identical neighbouring waves. V5.1
    # does not perturb them by one LSB merely to satisfy that policy. It records the
    # duplicates, keeps the mathematically exact 61-slot carrier, and leaves 61→N
    # consolidation to the dedicated V8-I/V8-K matrix. This is a validation boundary,
    # not a silent QC PASS.
    qc_preview_paths: tuple[Path, ...] = ()
    if not duplicate_pairs:
        qc = analyze_xt_trajectory_qc_documents(
            trajectory_document,
            projection_document=projection.to_dict(),
        )
        qc_json_path, qc_md_path, qc_preview_paths = qc.write(reports, stem=f"{stem}.xt_qc")
        qc_hash = qc.analysis.analysis_sha256
        qc_status = qc.analysis.status.value if hasattr(qc.analysis.status, "value") else str(qc.analysis.status)
    else:
        qc_payload = {
            "schema_version": 1,
            "status": "duplicate_aware_carrier",
            "source_trajectory_sha256": trajectory.analysis_sha256,
            "source_projection_set_sha256": projection.analysis_sha256,
            "duplicate_adjacent_slot_pairs": duplicate_pairs,
            "decision": "preserve exact quantized slots; do not inject artificial one-LSB differences",
            "v8_follow_up": "V8-I consolidation and V8-K N-matrix hardware cases must measure the reduced physical representation",
            "hardware_claim": False,
        }
        qc_hash = _canonical_hash(qc_payload)
        qc_payload["analysis_sha256"] = qc_hash
        qc_json_path = reports / f"{stem}.xt_qc_duplicate_aware.json"
        qc_md_path = reports / f"{stem}.xt_qc_duplicate_aware.md"
        _write_json(qc_json_path, qc_payload)
        qc_md_path.write_text(
            "# Duplicate-aware source carrier\n\n"
            f"Adjacent duplicate pairs: `{duplicate_pairs}`\n\n"
            "The exact quantized slots are preserved. No artificial sample perturbation is applied. "
            "This carrier is used only for source-to-XT evidence; V8-I/V8-K consolidation is validated separately.\n",
            encoding="utf-8",
        )
        qc_status = "duplicate_aware_carrier"

    baseline_bytes = baseline_copy.read_bytes()
    baseline = DumpFile.from_bytes(baseline_bytes)
    device_ids = tuple(baseline.device_ids)
    device_id = int(device_ids[0]) if len(device_ids) == 1 else 0
    numbers = tuple(range(user_wave_start, user_wave_start + 61))
    if numbers[0] < 1000 or numbers[-1] > 1249:
        raise AnalysisError("source campaign requires a contiguous 61-wave block inside 1000..1249")
    wavetable_destination = UserWavetableDestination(wavetable_display_number)
    target_sound = SoundDestination.parse(sound_destination)
    template_sound = SoundDestination.parse(template_sound_destination or sound_destination)
    if target_sound.is_edit_buffer or template_sound.is_edit_buffer:
        raise AnalysisError("source campaign requires stored Sound destinations")
    target_sound_address = target_sound.wire_address
    template_sound_address = template_sound.wire_address
    assert target_sound_address is not None and template_sound_address is not None
    index = {(int(message.dump_type), message.address): message for message in baseline.messages}
    target_wave_messages = tuple(index.get((int(DumpType.USER_WAVE), number)) for number in numbers)
    if any(message is None for message in target_wave_messages):
        missing = [number for number, message in zip(numbers, target_wave_messages) if message is None]
        raise AnalysisError(f"baseline is missing reserved User Waves: {missing}")
    target_wctd_message = index.get((int(DumpType.USER_WAVETABLE), wavetable_destination.internal_number))
    target_sound_message = index.get((int(DumpType.SOUND), target_sound_address))
    template_sound_message = index.get((int(DumpType.SOUND), template_sound_address))
    if target_wctd_message is None or target_sound_message is None or template_sound_message is None:
        raise AnalysisError("baseline is missing target WCTD or Sound destination")
    original_wavetable = UserWavetable.from_message(target_wctd_message)
    fixed_tail = tuple(original_wavetable.references[61:64])
    if len(fixed_tail) != 3:
        raise AnalysisError("baseline WCTD does not expose the three fixed tail references")
    slots = tuple(tuple(int(value) for value in slot.stored_samples) for slot in trajectory.slots)
    if len(slots) != 61:
        raise AnalysisError("source carrier requires exactly 61 trajectory slots")
    wave_messages = tuple(
        UserWave(device_id=device_id, number=number, stored_samples=stored).to_message()
        for number, stored in zip(numbers, slots, strict=True)
    )
    wavetable_message = UserWavetable(
        device_id=device_id,
        internal_number=wavetable_destination.internal_number,
        references=numbers + fixed_tail,
    ).to_message()
    source_sound = SoundProgram.from_message(template_sound_message)
    controlled_sound, sound_changes = build_controlled_audio_sound(
        source_sound,
        device_id=device_id,
        target_bank=target_sound_address >> 7,
        target_slot=target_sound_address & 0x7F,
        target_wavetable_internal=wavetable_destination.internal_number,
        name=sound_name,
    )
    sound_message = controlled_sound.to_message()
    package_dump = DumpFile(wave_messages + (wavetable_message, sound_message))
    restore_dump = DumpFile(tuple(target_wave_messages) + (target_wctd_message, target_sound_message))
    if len(package_dump.messages) != 63 or len(restore_dump.messages) != 63:
        raise AnalysisError("source carrier package/restore must each contain exactly 63 messages")
    package_bytes = package_dump.to_bytes()
    restore_bytes = restore_dump.to_bytes()
    if DumpFile.from_bytes(package_bytes).to_bytes() != package_bytes:
        raise AnalysisError("source carrier package round-trip failed")
    if DumpFile.from_bytes(restore_bytes).to_bytes() != restore_bytes:
        raise AnalysisError("source carrier restore round-trip failed")

    package_sysex = packages / f"{stem}.package.syx"
    waves_sysex = packages / f"{stem}.01-user-waves.syx"
    wavetable_sysex = packages / f"{stem}.02-wavetable.syx"
    sound_sysex = packages / f"{stem}.03-sound.syx"
    restore_sysex = packages / f"{stem}.restore.syx"
    package_sysex.write_bytes(package_bytes)
    waves_sysex.write_bytes(DumpFile(wave_messages).to_bytes())
    wavetable_sysex.write_bytes(DumpFile((wavetable_message,)).to_bytes())
    sound_sysex.write_bytes(DumpFile((sound_message,)).to_bytes())
    restore_sysex.write_bytes(restore_bytes)
    package_analysis = {
        "schema_version": 1,
        "carrier": "V5.1 duplicate-aware stable V7 source carrier",
        "message_count": len(package_dump.messages),
        "package_sha256": sha256(package_bytes).hexdigest(),
        "restore_bundle_sha256": sha256(restore_bytes).hexdigest(),
        "source_trajectory_sha256": trajectory.analysis_sha256,
        "source_projection_sha256": projection.analysis_sha256,
        "duplicate_adjacent_slot_pairs": duplicate_pairs,
        "unique_stored_wave_count": len(set(slots)),
        "sound_parameter_changes": [change.to_dict() if hasattr(change, "to_dict") else str(change) for change in sound_changes],
        "boundaries": {
            "source_evidence_carrier": True,
            "v8k_nplus1_product_claim": False,
            "v9_complete_product_claim": False,
            "automatic_midi": False,
        },
    }
    package_analysis["analysis_sha256"] = _canonical_hash(package_analysis)
    analysis_json = packages / f"{stem}.package.analysis.json"
    analysis_markdown = packages / f"{stem}.package.analysis.md"
    sha256_index = packages / f"{stem}.SHA256SUMS.txt"
    _write_json(analysis_json, package_analysis)
    analysis_markdown.write_text(
        "# Source hardware carrier\n\n"
        f"Messages: `{len(package_dump.messages)}`\n\n"
        f"Unique stored waves: `{package_analysis['unique_stored_wave_count']}` / 61\n\n"
        f"Adjacent duplicates preserved: `{duplicate_pairs}`\n\n"
        "This is a controlled source-evidence carrier, not a V9 complete-product claim.\n",
        encoding="utf-8",
    )
    checksum_paths = (package_sysex, waves_sysex, wavetable_sysex, sound_sysex, restore_sysex, analysis_json, analysis_markdown)
    sha256_index.write_text("".join(f"{_file_hash(path)}  {path.name}\n" for path in checksum_paths), encoding="utf-8")
    package_paths = _V51PackagePaths(package_sysex, waves_sysex, wavetable_sysex, sound_sysex, restore_sysex, analysis_json, analysis_markdown, sha256_index)

    fixed_midi, fixed_manifest = build_fixed_position_midi()
    sweep_midi, sweep_manifest = build_sweep_midi()
    fixed_midi_path = midi / f"{stem}.fixed_positions_CC71.mid"
    sweep_midi_path = midi / f"{stem}.sweep_0_60_0_CC71.mid"
    fixed_midi_path.write_bytes(fixed_midi)
    sweep_midi_path.write_bytes(sweep_midi)
    fixed_manifest_path = midi / f"{stem}.fixed_positions_CC71.json"
    sweep_manifest_path = midi / f"{stem}.sweep_0_60_0_CC71.json"
    _write_json(fixed_manifest_path, fixed_manifest)
    _write_json(sweep_manifest_path, sweep_manifest)

    fixed_preview = render_fixed_position_preview(trajectory, fixed_manifest, sample_rate=sample_rate)
    sweep_preview = render_sweep_preview(trajectory, sweep_manifest, sample_rate=sample_rate)
    fixed_preview_path = previews / f"{stem}.fixed_positions_expected.wav"
    sweep_preview_path = previews / f"{stem}.sweep_expected.wav"
    sf.write(str(fixed_preview_path), fixed_preview, sample_rate, format="WAV", subtype="PCM_24")
    sf.write(str(sweep_preview_path), sweep_preview, sample_rate, format="WAV", subtype="PCM_24")

    artifact_paths: list[Path] = [
        source_copy,
        baseline_copy,
        code_v6_path,
        projection_path,
        trajectory_path,
        qc_json_path,
        qc_md_path,
        *qc_preview_paths,
        package_paths.package_sysex,
        package_paths.user_waves_sysex,
        package_paths.user_wavetable_sysex,
        package_paths.sound_sysex,
        package_paths.restore_sysex,
        package_paths.analysis_json,
        package_paths.analysis_markdown,
        package_paths.sha256_index,
        fixed_midi_path,
        fixed_manifest_path,
        sweep_midi_path,
        sweep_manifest_path,
        fixed_preview_path,
        sweep_preview_path,
    ]
    artifacts = {
        str(path.relative_to(root)).replace("\\", "/"): {
            "sha256": _file_hash(path),
            "bytes": path.stat().st_size,
        }
        for path in artifact_paths
    }
    manifest: dict[str, object] = {
        "schema_version": REAL_SAMPLE_CAMPAIGN_SCHEMA_VERSION,
        "campaign_stem": stem,
        "source": {
            "original_path": str(source_path),
            "campaign_path": str(source_copy.relative_to(root)).replace("\\", "/"),
            "sha256": _file_hash(source_copy),
            "audio_state_sha256": audio.state_sha256,
            "sample_rate": audio.metadata.sample_rate,
            "sample_count": int(audio.mono_samples.size),
            "duration_seconds": audio.metadata.duration_seconds,
        },
        "baseline": {
            "original_path": str(baseline_path),
            "campaign_path": str(baseline_copy.relative_to(root)).replace("\\", "/"),
            "sha256": _file_hash(baseline_copy),
            "message_count": len(baseline.messages),
            "device_ids": list(baseline.device_ids),
        },
        "execution_chain": [
            "audio import (V3)",
            "CODE V5/V6 analysis and reconstructed waves",
            "CODE V7 XT-native projection",
            "CODE V7 61-position trajectory",
            "duplicate-aware trajectory review and mathematical previews",
            "V5.1 controlled 61-WAVD source carrier and exact restore",
            "real XT fixed-position and sweep capture comparison",
            "machine-readable repository change recommendations",
        ],
        "hash_links": {
            "code_v6_analysis_sha256": code_v6.analysis_sha256,
            "reconstructed_wave_set_sha256": code_v6.reconstructed_wave_set.analysis_sha256,
            "projection_sha256": projection.analysis_sha256,
            "trajectory_sha256": trajectory.analysis_sha256,
            "qc_sha256": qc_hash,
            "hardware_package_analysis_sha256": package_analysis["analysis_sha256"],
            "hardware_package_sha256": package_analysis["package_sha256"],
            "trajectory_review_status": qc_status,
            "restore_sha256": package_analysis["restore_bundle_sha256"],
        },
        "hardware_targets": {
            "user_wave_start": user_wave_start,
            "user_wave_end": user_wave_start + 60,
            "wavetable_display_number": wavetable_display_number,
            "sound_destination": sound_destination,
            "template_sound_destination": template_sound_destination or sound_destination,
            "sound_name": sound_name,
        },
        "required_captures": {
            "readback": {
                "destination": f"captures/{stem}.package_readback.syx",
                "expected_package": str(package_paths.package_sysex.relative_to(root)).replace("\\", "/"),
                "required_before_audio": True,
            },
            "fixed_positions": {
                "destination": f"captures/{stem}.fixed_positions_XT.wav",
                "midi": str(fixed_midi_path.relative_to(root)).replace("\\", "/"),
                "expected_preview": str(fixed_preview_path.relative_to(root)).replace("\\", "/"),
            },
            "sweep": {
                "destination": f"captures/{stem}.sweep_XT.wav",
                "midi": str(sweep_midi_path.relative_to(root)).replace("\\", "/"),
                "expected_preview": str(sweep_preview_path.relative_to(root)).replace("\\", "/"),
            },
        },
        "evidence_count": {
            "readback_sysex": 1,
            "audio_wav": 2,
        },
        "capture_contract": {
            "mono": True,
            "pcm_bits": 24,
            "allowed_sample_rates": [48_000, 96_000],
            "normalization": False,
            "plugins": False,
            "warp_or_time_stretch": False,
            "gain_must_remain_unchanged": True,
            "raw_track_not_processed_master": True,
        },
        "current_repository_boundary": {
            "v8k_complete_sound_package": False,
            "hardware_carrier_used": "V5.1 duplicate-aware controlled 61-WAVD source carrier",
            "reason": (
                "The supplied V8-K code explicitly defines but does not implement N WAVD + WCTD + SNDD. "
                "V5.1 therefore uses a controlled 61-WAVD source-evidence carrier, preserving legitimate adjacent duplicates, "
                "while the separate V8-I/V8-K matrix validates 61-to-N consolidation and N+1 packages."
            ),
        },
        "artifacts": artifacts,
        "automatic_midi_transmission": False,
        "automatic_hardware_write": False,
    }
    manifest["campaign_sha256"] = _canonical_hash(manifest)
    manifest_path = root / "CAMPAIGN.json"
    _write_json(manifest_path, manifest)

    operator = root / "OPERATOR_STEPS.md"
    operator_text = (
        f"# {stem} — prise matérielle réelle\n\n"
        "1. Vérifier le nouveau bloc d’alimentation et une stabilité d’au moins 30 minutes.\n"
        f"2. Envoyer **une seule fois** `packages/{package_paths.package_sysex.name}`.\n"
        "3. Faire un redump frais des 61 User Waves, de la Wavetable et du Sound; comparer avant toute prise.\n"
        f"4. Charger le Sound `{sound_name}` à `{sound_destination}`. Sélectionner brièvement un autre Sound, puis revenir à celui-ci.\n"
        f"5. Lire `midi/{fixed_midi_path.name}` sans modification et enregistrer `captures/{stem}.fixed_positions_XT.wav`.\n"
        f"6. Lire `midi/{sweep_midi_path.name}` sans modification et enregistrer `captures/{stem}.sweep_XT.wav`.\n"
        "7. Les deux prises doivent être mono PCM 24 bits, 48 ou 96 kHz, sans plugin, Warp, normalisation, dither, limiteur ou traitement Master.\n"
        "8. Lancer ensuite l’analyse de captures.\n"
        f"9. À la fin, envoyer `packages/{package_paths.restore_sysex.name}` puis vérifier le read-back de restauration.\n\n"
        "Aucun fichier MIDI ne contient de SysEx. Seul CC71 est utilisé, avec Note On/Off explicites.\n"
    )
    operator.write_text(operator_text, encoding="utf-8", newline="\n")
    return SourceCampaignArtifacts(
        root=root,
        manifest_path=manifest_path,
        package_path=package_paths.package_sysex,
        restore_path=package_paths.restore_sysex,
        fixed_midi_path=fixed_midi_path,
        sweep_midi_path=sweep_midi_path,
        fixed_preview_path=fixed_preview_path,
        sweep_preview_path=sweep_preview_path,
    )


__all__ = [
    "REAL_SAMPLE_CAMPAIGN_SCHEMA_VERSION",
    "DEFAULT_FIXED_POSITIONS",
    "DEFAULT_FIXED_NOTES",
    "SourceCampaignArtifacts",
    "build_fixed_position_midi",
    "build_sweep_midi",
    "render_fixed_position_preview",
    "render_sweep_preview",
    "build_source_campaign",
]
