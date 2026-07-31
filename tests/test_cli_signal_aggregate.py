from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import main


def _write_tone(path: Path, sample_rate: int = 16000) -> None:
    time = np.arange(sample_rate // 4, dtype=np.float64) / sample_rate
    sf.write(path, 0.4 * np.sin(2.0 * np.pi * 440.0 * time), sample_rate, subtype="FLOAT")


def _args(source: Path) -> list[str]:
    return [
        "signal-analyze", str(source),
        "--frame-size", "512", "--hop-size", "128",
        "--pitch-frame-size", "1024", "--pitch-hop-size", "256",
        "--maximum-frequency", "2000",
        "--transient-frame-size", "256", "--transient-hop-size", "64",
    ]


def test_cli_root_is_the_signal_analysis_contract(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main(_args(source)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["tool_version"] == "0.4.0"
    assert len(payload["analysis_sha256"]) == 64
    assert payload["sample_sha256"] == payload["audio"]["sample_sha256"]


def test_cli_preserves_all_accepted_component_keys(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main(_args(source)) == 0
    payload = json.loads(capsys.readouterr().out)
    for key in (
        "time_domain_analysis", "pitch_periodicity_analysis",
        "phase_motion_analysis", "noise_analysis",
        "transient_change_analysis",
    ):
        assert key in payload
        assert len(payload[key]["analysis_sha256"]) == 64


def test_cli_component_hash_map_matches_nested_components(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main(_args(source)) == 0
    payload = json.loads(capsys.readouterr().out)
    for key, digest in payload["component_analysis_sha256"].items():
        assert digest == payload[key]["analysis_sha256"]


def test_cli_writes_stdout_exactly_to_report(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    report = tmp_path / "reports" / "tone.json"
    _write_tone(source)
    assert main([*_args(source), "--report", str(report)]) == 0
    assert report.read_text(encoding="utf-8") == capsys.readouterr().out


def test_cli_report_is_byte_deterministic(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_tone(source)
    assert main([*_args(source), "--report", str(first)]) == 0
    capsys.readouterr()
    assert main([*_args(source), "--report", str(second)]) == 0
    capsys.readouterr()
    assert first.read_bytes() == second.read_bytes()


def test_cli_custom_configuration_is_recorded(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    args = [*_args(source), "--reference-a4", "442", "--noise-lower-quantile", "0.3"]
    assert main(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["pitch_periodicity_analysis"]["reference_a4_hz"] == 442.0
    assert payload["noise_analysis"]["lower_quantile"] == 0.3


def test_cli_invalid_configuration_returns_one(tmp_path: Path, capsys) -> None:
    source = tmp_path / "tone.wav"
    _write_tone(source)
    assert main(["signal-analyze", str(source), "--pitch-frame-size", "0"]) == 1
    assert "frame_size" in capsys.readouterr().err
