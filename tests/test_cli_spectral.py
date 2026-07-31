from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import main


def write_tone(path: Path, frequency: float = 1000.0) -> None:
    sample_rate = 48000
    t = np.arange(sample_rate, dtype=np.float64) / sample_rate
    samples = 0.8 * np.sin(2.0 * np.pi * frequency * t)
    sf.write(path, samples, sample_rate, subtype="FLOAT")


def test_cli_prints_spectral_json(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    write_tone(source)
    assert main(["spectral-analyze", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["spectral_analysis"]["dominant_frequency_hz"] > 900.0


def test_cli_writes_report(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    report = tmp_path / "report.json"
    write_tone(source)
    assert main(["spectral-analyze", str(source), "--report", str(report)]) == 0
    printed = capsys.readouterr().out
    assert report.read_text(encoding="utf-8") == printed


def test_cli_reports_are_deterministic(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_tone(source, 750.0)
    main(["spectral-analyze", str(source), "--report", str(first)])
    capsys.readouterr()
    main(["spectral-analyze", str(source), "--report", str(second)])
    capsys.readouterr()
    assert first.read_bytes() == second.read_bytes()


def test_cli_accepts_custom_fft_size(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    write_tone(source)
    main(["spectral-analyze", str(source), "--frame-size", "2048", "--fft-size", "8192"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["spectral_analysis"]["fft_size"] == 8192


def test_cli_embeds_audio_and_analysis_hashes(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    write_tone(source)
    main(["spectral-analyze", str(source)])
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["audio"]["sample_sha256"]) == 64
    assert len(payload["spectral_analysis"]["analysis_sha256"]) == 64
