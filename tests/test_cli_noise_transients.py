
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import main


def _write_tone(path: Path) -> None:
    sample_rate = 48000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    samples = 0.5 * np.sin(2.0 * np.pi * 440.0 * time)
    samples[sample_rate // 2] += 0.8
    sf.write(path, samples, sample_rate, subtype="FLOAT")


def test_signal_analyze_includes_noise_and_transients(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main(["signal-analyze", str(source)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert "noise_analysis" in output
    assert "transient_change_analysis" in output
    assert len(output["noise_analysis"]["analysis_sha256"]) == 64
    assert len(output["transient_change_analysis"]["analysis_sha256"]) == 64


def test_signal_analyze_v4d_report_is_deterministic(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_tone(source)
    assert main(["signal-analyze", str(source), "--report", str(first)]) == 0
    capsys.readouterr()
    assert main(["signal-analyze", str(source), "--report", str(second)]) == 0
    capsys.readouterr()
    assert first.read_bytes() == second.read_bytes()


def test_signal_analyze_v4d_options_are_recorded(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main([
        "signal-analyze", str(source),
        "--noise-lower-quantile", "0.3",
        "--transient-frame-size", "512",
        "--transient-hop-size", "128",
        "--transient-sensitivity", "4",
        "--minimum-onset-strength", "0.7",
        "--change-energy-db", "5",
        "--change-spectral-flux", "0.2",
        "--minimum-event-separation-ms", "25",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["noise_analysis"]["lower_quantile"] == 0.3
    transient = output["transient_change_analysis"]
    assert transient["frame_size"] == 512
    assert transient["hop_size"] == 128
    assert transient["sensitivity"] == 4.0
    assert transient["minimum_onset_strength"] == 0.7
    assert transient["change_energy_threshold_db"] == 5.0
    assert transient["change_spectral_flux_threshold"] == 0.2
    assert transient["minimum_event_separation_ms"] == 25.0


def test_invalid_noise_option_returns_error(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main(["signal-analyze", str(source), "--noise-lower-quantile", "2"]) == 1
    assert "lower_quantile" in capsys.readouterr().err
