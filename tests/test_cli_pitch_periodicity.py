from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import main


def _write_sine(path, *, frequency_hz: float = 440.0, sample_rate: int = 44100) -> None:
    times = np.arange(sample_rate // 4, dtype=np.float64) / sample_rate
    signal = 0.8 * np.sin(2.0 * np.pi * frequency_hz * times)
    sf.write(path, signal, sample_rate, subtype="FLOAT")


def test_signal_analyze_includes_pitch_periodicity(capsys, tmp_path) -> None:
    source = tmp_path / "a4.wav"
    _write_sine(source)
    result = main(["signal-analyze", str(source)])
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    analysis = payload["pitch_periodicity_analysis"]
    assert analysis["note_name"] == "A4"
    assert abs(analysis["frequency_hz"] - 440.0) < 0.2
    assert analysis["periodicity_class"] == "stable_periodic"


def test_signal_analyze_writes_deterministic_report(capsys, tmp_path) -> None:
    source = tmp_path / "source.wav"
    report = tmp_path / "nested" / "analysis.json"
    _write_sine(source, frequency_hz=220.0)
    arguments = [
        "signal-analyze",
        str(source),
        "--pitch-frame-size",
        "2048",
        "--pitch-hop-size",
        "512",
        "--minimum-frequency",
        "80",
        "--maximum-frequency",
        "1000",
        "--pitch-confidence",
        "0.55",
        "--reference-a4",
        "440",
        "--report",
        str(report),
    ]
    assert main(arguments) == 0
    first_stdout = capsys.readouterr().out
    assert report.read_text(encoding="utf-8") == first_stdout
    assert main(arguments) == 0
    second_stdout = capsys.readouterr().out
    assert first_stdout == second_stdout
