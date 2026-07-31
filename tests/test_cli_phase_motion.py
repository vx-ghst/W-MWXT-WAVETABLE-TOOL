
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import main


def _write_sine(path: Path) -> None:
    sample_rate = 48000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    sf.write(path, 0.5 * np.sin(2.0 * np.pi * 440.0 * time), sample_rate, subtype="FLOAT")


def test_signal_analyze_includes_phase_motion(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_sine(source)
    assert main(["signal-analyze", str(source)]) == 0
    output = json.loads(capsys.readouterr().out)
    phase = output["phase_motion_analysis"]
    assert phase["pitch_motion_class"] == "stable"
    assert phase["phase_continuity_class"] in {"stable", "variable"}
    assert len(phase["analysis_sha256"]) == 64


def test_signal_analyze_report_is_deterministic(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_sine(source)
    assert main(["signal-analyze", str(source), "--report", str(first)]) == 0
    capsys.readouterr()
    assert main(["signal-analyze", str(source), "--report", str(second)]) == 0
    capsys.readouterr()
    assert first.read_bytes() == second.read_bytes()


def test_signal_analyze_phase_options_are_recorded(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_sine(source)
    assert main([
        "signal-analyze",
        str(source),
        "--phase-discontinuity-degrees", "50",
        "--stable-pitch-cents", "10",
        "--glide-slope-cents-per-second", "35",
        "--stepped-pitch-cents", "80",
    ]) == 0
    output = json.loads(capsys.readouterr().out)["phase_motion_analysis"]
    assert output["phase_discontinuity_threshold_degrees"] == 50.0
    assert output["stable_pitch_threshold_cents"] == 10.0
    assert output["glide_slope_threshold_cents_per_second"] == 35.0
    assert output["stepped_pitch_threshold_cents"] == 80.0


def test_invalid_phase_option_returns_error(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_sine(source)
    assert main([
        "signal-analyze",
        str(source),
        "--phase-discontinuity-degrees", "200",
    ]) == 1
    assert "must not exceed 180" in capsys.readouterr().err
