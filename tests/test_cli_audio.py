from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import main


def test_audio_inspect_cli_prints_json(tmp_path: Path, capsys) -> None:
    path = tmp_path / "source.wav"
    sf.write(path, np.linspace(-0.5, 0.5, 64), 44100, subtype="FLOAT")
    assert main(["audio-inspect", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metadata"]["container"] == "wav"
    assert payload["metadata"]["frames"] == 64
    assert payload["sample_dtype"] == "float64"


def test_audio_inspect_cli_writes_report(tmp_path: Path, capsys) -> None:
    path = tmp_path / "source.flac"
    report = tmp_path / "reports" / "source.json"
    sf.write(path, np.linspace(-0.5, 0.5, 64), 44100, format="FLAC", subtype="PCM_16")
    assert main(["audio-inspect", str(path), "--report", str(report)]) == 0
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved == printed


def test_audio_inspect_cli_reports_failure(tmp_path: Path, capsys) -> None:
    assert main(["audio-inspect", str(tmp_path / "missing.wav")]) == 1
    assert "ERROR:" in capsys.readouterr().err
