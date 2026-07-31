from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import main


def write_harmonic_tone(path: Path, fundamental: float = 250.0) -> None:
    sample_rate = 48000
    t = np.arange(sample_rate, dtype=np.float64) / sample_rate
    samples = (
        0.75 * np.sin(2.0 * np.pi * fundamental * t)
        + 0.35 * np.sin(2.0 * np.pi * 2.0 * fundamental * t)
        + 0.20 * np.sin(2.0 * np.pi * 3.0 * fundamental * t)
    )
    sf.write(path, samples, sample_rate, subtype="FLOAT")


def test_cli_prints_harmonic_perceptual_json(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    write_harmonic_tone(source)
    assert main(["perceptual-analyze", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["harmonic_perceptual_analysis"]["detected_harmonic_count"] >= 3


def test_cli_preserves_component_sample_identity(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    write_harmonic_tone(source)
    main(["perceptual-analyze", str(source)])
    payload = json.loads(capsys.readouterr().out)
    hashes = {
        payload["audio"]["sample_sha256"],
        payload["pitch_periodicity_analysis"]["sample_sha256"],
        payload["spectral_analysis"]["sample_sha256"],
        payload["harmonic_perceptual_analysis"]["sample_sha256"],
    }
    assert len(hashes) == 1


def test_cli_writes_report(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    report = tmp_path / "report.json"
    write_harmonic_tone(source)
    assert main(["perceptual-analyze", str(source), "--report", str(report)]) == 0
    assert report.read_text(encoding="utf-8") == capsys.readouterr().out


def test_cli_reports_are_deterministic(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_harmonic_tone(source)
    main(["perceptual-analyze", str(source), "--report", str(first)])
    capsys.readouterr()
    main(["perceptual-analyze", str(source), "--report", str(second)])
    capsys.readouterr()
    assert first.read_bytes() == second.read_bytes()


def test_cli_accepts_harmonic_and_bark_configuration(tmp_path, capsys) -> None:
    source = tmp_path / "tone.wav"
    write_harmonic_tone(source)
    main(
        [
            "perceptual-analyze",
            str(source),
            "--maximum-harmonics",
            "2",
            "--bark-band-count",
            "12",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    analysis = payload["harmonic_perceptual_analysis"]
    assert analysis["detected_harmonic_count"] <= 2
    assert len(analysis["bark_band_energy_ratio"]) == 12
