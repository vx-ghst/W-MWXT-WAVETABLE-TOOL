from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import main


def test_signal_analyze_cli_prints_time_domain_json(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "signal.wav"
    sf.write(source, np.linspace(-0.5, 0.5, 1024), 44100, subtype="FLOAT")
    assert main(["signal-analyze", str(source), "--frame-size", "128", "--hop-size", "64"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["audio"]["metadata"]["sample_rate"] == 44100
    assert payload["time_domain_analysis"]["schema_version"] == 1
    assert payload["time_domain_analysis"]["envelope"]["frame_size"] == 128
    assert len(payload["time_domain_analysis"]["analysis_sha256"]) == 64


def test_signal_analyze_cli_writes_identical_report(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "signal.wav"
    report = tmp_path / "reports" / "signal.json"
    sf.write(source, np.ones(256) * 0.1, 48000, subtype="FLOAT")
    assert main(["signal-analyze", str(source), "--report", str(report)]) == 0
    stdout = capsys.readouterr().out
    assert report.read_text(encoding="utf-8") == stdout


def test_signal_analyze_cli_reports_invalid_frame_configuration(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "signal.wav"
    sf.write(source, np.ones(64), 44100, subtype="FLOAT")
    assert main(["signal-analyze", str(source), "--frame-size", "0"]) == 1
    assert "frame_size" in capsys.readouterr().err
