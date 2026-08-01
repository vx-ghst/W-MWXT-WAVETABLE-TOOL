from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import _build_parser, main


def _write_tone(path: Path, frequency: float = 440.0, sample_rate: int = 16000) -> None:
    time = np.arange(sample_rate // 2, dtype=np.float64) / sample_rate
    sf.write(
        path,
        0.4 * np.sin(2.0 * np.pi * frequency * time),
        sample_rate,
        subtype="FLOAT",
    )


def test_parser_exposes_pitch_plan_defaults(tmp_path: Path) -> None:
    source = tmp_path / "tone.wav"
    args = _build_parser().parse_args(["pitch-plan", str(source)])
    assert args.command == "pitch-plan"
    assert args.policy == "auto"
    assert args.preferred_period_samples == 128.0
    assert args.minimum_period_samples == 64.0
    assert args.maximum_period_samples == 256.0
    assert args.maximum_octave_shift == 4


def test_pitch_plan_cli_emits_linked_json(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main(["pitch-plan", str(source), "--maximum-frequency", "2000"]) == 0
    payload = json.loads(capsys.readouterr().out)
    plan = payload["working_pitch_plan"]
    assert payload["audio"]["sample_sha256"] == plan["sample_sha256"]
    assert (
        payload["pitch_periodicity_analysis"]["analysis_sha256"]
        == plan["pitch_periodicity_analysis_sha256"]
    )
    assert plan["policy"] == "auto"
    assert plan["decision"] in {"repitch", "no_repitch"}


def test_pitch_plan_cli_writes_deterministic_report(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_tone(source, frequency=220.0)
    assert main(["pitch-plan", str(source), "--report", str(first)]) == 0
    capsys.readouterr()
    assert main(["pitch-plan", str(source), "--report", str(second)]) == 0
    capsys.readouterr()
    assert first.read_bytes() == second.read_bytes()


def test_pitch_plan_cli_accepts_explicit_lock(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main(
        [
            "pitch-plan",
            str(source),
            "--policy",
            "lock",
            "--locked-frequency",
            "330",
        ]
    ) == 0
    plan = json.loads(capsys.readouterr().out)["working_pitch_plan"]
    assert plan["policy"] == "lock"
    assert plan["locked"] is True
    assert plan["target_frequency_hz"] == 330.0


def test_pitch_plan_cli_rejects_lock_without_frequency(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main(["pitch-plan", str(source), "--policy", "lock"]) == 1
    assert "locked_frequency_hz" in capsys.readouterr().err
