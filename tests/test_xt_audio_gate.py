from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.constants import DumpType
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable
from w_mwxt_wavetable_tool.xt.audio_gate import (
    XtAudioGateStatus,
    XtAudioGateVerdict,
    XtAudioHypothesis,
    XtAudioWaveRole,
    analyze_xt_audio_gate,
    build_note_midi,
    build_xt_audio_gate,
    midi_note_frequency,
    verify_xt_audio_gate_restore,
    verify_xt_audio_gate_setup,
)


def _baseline() -> DumpFile:
    waves = tuple(
        UserWave(
            0,
            1247 + index,
            tuple(((index * 41 + sample * 5) % 255) - 127 for sample in range(64)),
        ).to_message()
        for index in range(3)
    )
    wavetable = UserWavetable.from_display_number(
        0,
        128,
        tuple(range(1000, 1061)) + (0, 1, 2),
    ).to_message()
    data = bytearray(256)
    data[0] = 1
    data[25] = 96
    data[240:256] = b"ORIGINAL B128   "
    sound = SoundProgram(0, 1, 127, bytes(data)).to_message()
    return DumpFile(waves + (wavetable, sound))


def _storage_report() -> dict:
    return {
        "status": "pass",
        "storage_passed": True,
        "v7_b_allowed_under_safe_range": True,
        "verdict": "documented_reconstruction_storage_confirmed_edge_unresolved",
    }


def _restore_report() -> dict:
    return {
        "status": "pass",
        "storage_passed": True,
        "verdict": "restore_confirmed",
    }


def _build():
    return build_xt_audio_gate(
        _baseline(),
        v7a1_storage_report=_storage_report(),
        v7a1_restore_report=_restore_report(),
        v7a1_storage_report_sha256="1" * 64,
        v7a1_restore_report_sha256="2" * 64,
    )


def test_audio_gate_build_is_deterministic_and_complete(tmp_path: Path) -> None:
    first = _build()
    second = _build()
    assert first.setup.to_bytes() == second.setup.to_bytes()
    assert first.plan.to_json() == second.plan.to_json()
    assert first.ready_for_transmission
    assert len(first.setup.messages) == 5
    assert len(first.select_safe.messages) == 2
    assert len(first.select_offset_binary.messages) == 2
    assert len(first.select_negative_full_scale.messages) == 2
    assert len(first.restore.messages) == 5
    paths = first.write(tmp_path)
    assert paths.setup.stat().st_size == 941
    assert paths.restore.stat().st_size == 941
    assert paths.midi_c2.read_bytes().startswith(b"MThd")
    manifest = json.loads(paths.manifest_json.read_text())
    assert manifest["schema_version"] == 1
    raw_contract = {
        item["index"]: item["value"]
        for item in manifest["sound_control"]["raw_overrides"]
    }
    assert raw_contract[6] == 48
    assert raw_contract[108] == 0
    assert raw_contract[109] == 0
    assert raw_contract[110] == 64


def test_controlled_sound_targets_b128_and_neutralizes_documented_paths() -> None:
    build = _build()
    sound = SoundProgram.from_message(build.setup.messages[-1])
    assert sound.display_location == "B128"
    assert sound.name == "V7A2 AUDIO GATE"
    assert sound.wavetable_parameter_raw == 127
    assert sound.data[0] == 1
    assert sound.data[1:4] == bytes((64, 64, 64))
    assert sound.data[6] == 48
    assert sound.data[12:15] == bytes((64, 64, 64))
    assert sound.data[18] == 48
    assert sound.data[27] == 1
    assert sound.data[47:52] == bytes((96, 0, 0, 0, 0))
    assert sound.data[53:56] == bytes((0, 0, 0))
    assert sound.data[57] == 1
    assert sound.data[62:64] == bytes((127, 0))
    assert sound.data[82] == 0
    assert sound.data[92] == 0
    assert sound.data[108:111] == bytes((0, 0, 64))
    assert sound.data[119:124] == bytes((0, 0, 127, 0, 0))
    for base in range(192, 240, 3):
        assert sound.data[base : base + 3] == bytes((0, 64, 0))


def test_each_selector_repeats_one_probe_across_all_user_positions() -> None:
    build = _build()
    expected = {
        XtAudioWaveRole.SAFE: build.plan.target_wave_numbers[0],
        XtAudioWaveRole.OFFSET_BINARY_EDGE: build.plan.target_wave_numbers[1],
        XtAudioWaveRole.NEGATIVE_FULL_SCALE_EDGE: build.plan.target_wave_numbers[2],
    }
    packages = {
        XtAudioWaveRole.SAFE: build.select_safe,
        XtAudioWaveRole.OFFSET_BINARY_EDGE: build.select_offset_binary,
        XtAudioWaveRole.NEGATIVE_FULL_SCALE_EDGE: build.select_negative_full_scale,
    }
    for role, package in packages.items():
        table = UserWavetable.from_message(package.messages[0])
        assert table.references[:61] == (expected[role],) * 61
        assert table.references[61:] == (0, 1, 2)


def test_setup_and_restore_verification_are_exact() -> None:
    build = _build()
    setup = verify_xt_audio_gate_setup(build.setup, build.setup, build.plan)
    restore = verify_xt_audio_gate_restore(build.restore, build.restore, build.plan)
    assert setup.status is XtAudioGateStatus.PASS
    assert setup.verdict is XtAudioGateVerdict.SETUP_CONFIRMED
    assert setup.exact
    assert restore.status is XtAudioGateStatus.PASS
    assert restore.verdict is XtAudioGateVerdict.RESTORE_CONFIRMED
    assert restore.exact


def test_setup_verification_detects_changed_payload() -> None:
    build = _build()
    changed = list(build.setup.messages)
    payload = bytearray(changed[0].payload)
    payload[0] = (payload[0] + 1) & 0x0F
    changed[0] = type(changed[0])(
        changed[0].device_id,
        changed[0].dump_type,
        changed[0].address,
        bytes(payload),
    )
    result = verify_xt_audio_gate_setup(build.setup, DumpFile(tuple(changed)), build.plan)
    assert result.status is XtAudioGateStatus.FAIL
    assert not result.exact


def test_note_midi_is_deterministic() -> None:
    first = build_note_midi(48)
    second = build_note_midi(48)
    assert first == second
    assert first[:4] == b"MThd"
    assert b"MTrk" in first
    assert bytes((0x90, 48, 100)) in first
    assert bytes((0x80, 48, 0)) in first


def _synthesize(cycle: np.ndarray, midi_note: int, sample_rate: int = 96_000) -> np.ndarray:
    frequency = midi_note_frequency(midi_note) * 1.0015
    duration = 4.0
    frame_count = int(sample_rate * duration)
    phase = (np.arange(frame_count) * frequency / sample_rate) % 1.0
    positions = phase * cycle.size
    lower = np.floor(positions).astype(int) % cycle.size
    upper = (lower + 1) % cycle.size
    frac = positions - np.floor(positions)
    output = cycle[lower] * (1.0 - frac) + cycle[upper] * frac
    output = output - np.mean(output)
    output = output / max(np.max(np.abs(output)), 1e-12) * 0.35
    rng = np.random.default_rng(7 + midi_note)
    output += rng.normal(0.0, 2e-5, output.size)
    return output.astype(np.float64)


def _edge_cycle(stored: tuple[int, ...], positive: bool) -> np.ndarray:
    second = []
    for sample in reversed(stored):
        if sample == -128:
            second.append(127 if positive else -128)
        else:
            second.append(-sample)
    return np.asarray(stored + tuple(second), dtype=np.float64)


def _write_capture_corpus(directory: Path, positive_edge: bool = True) -> object:
    build = _build()
    directory.mkdir(parents=True, exist_ok=True)
    sf.write(directory / "silence_5s.wav", np.zeros(96_000 * 5), 96_000, subtype="PCM_24")
    probes = {
        XtAudioWaveRole.SAFE: build.plan.probes[0],
        XtAudioWaveRole.OFFSET_BINARY_EDGE: build.plan.probes[1],
        XtAudioWaveRole.NEGATIVE_FULL_SCALE_EDGE: build.plan.probes[2],
    }
    for spec in build.plan.captures:
        if spec.role is None:
            continue
        probe = probes[spec.role]
        if spec.role is XtAudioWaveRole.SAFE:
            cycle = np.asarray(probe.documented_full_samples, dtype=np.float64)
        else:
            cycle = _edge_cycle(probe.stored_samples, positive_edge)
        samples = _synthesize(cycle, spec.midi_note)
        sf.write(directory / spec.filename, samples, 96_000, subtype="PCM_24")
    return build


def test_audio_analysis_supports_documented_law_and_positive_edge(tmp_path: Path) -> None:
    build = _write_capture_corpus(tmp_path, positive_edge=True)
    result = analyze_xt_audio_gate(tmp_path, build.plan)
    analysis = result.analysis
    assert analysis.status is XtAudioGateStatus.PASS
    assert analysis.v7_b_allowed_under_safe_range
    assert analysis.safe_reconstruction_status == (
        "documented_reverse_negate_consistent_unique_best"
    )
    assert analysis.verdict is XtAudioGateVerdict.SAFE_RECONSTRUCTION_SUPPORTED_EDGE_POSITIVE
    assert analysis.negative_full_scale_status.startswith("positive_edge_compatible")
    safe = [take for take in analysis.takes if take.role is XtAudioWaveRole.SAFE]
    assert all(take.winner is XtAudioHypothesis.DOCUMENTED_REVERSE_NEGATE for take in safe)


def test_audio_analysis_can_rank_wrap_edge(tmp_path: Path) -> None:
    build = _write_capture_corpus(tmp_path, positive_edge=False)
    analysis = analyze_xt_audio_gate(tmp_path, build.plan).analysis
    assert analysis.status is XtAudioGateStatus.PASS
    assert analysis.verdict is XtAudioGateVerdict.SAFE_RECONSTRUCTION_SUPPORTED_EDGE_WRAP
    assert analysis.negative_full_scale_status == "wrap_to_negative_full_scale_compatible"


def test_audio_analysis_reports_missing_captures(tmp_path: Path) -> None:
    build = _build()
    result = analyze_xt_audio_gate(tmp_path, build.plan)
    assert result.analysis.status is XtAudioGateStatus.INCOMPLETE
    assert result.analysis.verdict is XtAudioGateVerdict.CAPTURES_INCOMPLETE
    assert "silence_5s.wav" in result.analysis.missing_captures
