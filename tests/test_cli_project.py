from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import soundfile as sf

from w_mwxt_wavetable_tool.cli import main


def _write_audio(path: Path) -> None:
    sf.write(path, np.linspace(-0.5, 0.5, 96), 44100, subtype="FLOAT")


def test_project_create_and_open_cli(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.wav"
    project = tmp_path / "source.mwxtproj"
    _write_audio(source)
    assert main(["project-create", str(source), str(project), "--name", "CLI project"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["project_name"] == "CLI project"
    assert project.exists()

    assert main(["project-open", str(project)]) == 0
    opened = json.loads(capsys.readouterr().out)
    assert opened["project"]["name"] == "CLI project"
    assert opened["source_check"]["status"] == "unchanged"
    assert opened["audio"]["metadata"]["frames"] == 96


def test_project_open_cli_writes_report(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.wav"
    project = tmp_path / "source.mwxtproj"
    report = tmp_path / "reports" / "project.json"
    _write_audio(source)
    assert main(["project-create", str(source), str(project)]) == 0
    capsys.readouterr()
    assert main(["project-open", str(project), "--report", str(report)]) == 0
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved == printed


def test_project_create_cli_requires_overwrite_flag(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.wav"
    project = tmp_path / "source.mwxtproj"
    _write_audio(source)
    assert main(["project-create", str(source), str(project)]) == 0
    capsys.readouterr()
    assert main(["project-create", str(source), str(project)]) == 1
    assert "ERROR:" in capsys.readouterr().err
    assert main(["project-create", str(source), str(project), "--overwrite"]) == 0


def test_project_open_cli_changed_source_policy(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.wav"
    project = tmp_path / "source.mwxtproj"
    _write_audio(source)
    assert main(["project-create", str(source), str(project)]) == 0
    capsys.readouterr()
    source.write_bytes(source.read_bytes() + b"changed")
    assert main(["project-open", str(project)]) == 1
    assert "changed" in capsys.readouterr().err
    assert main(["project-open", str(project), "--source-policy", "allow_embedded"]) == 0
    opened = json.loads(capsys.readouterr().out)
    assert opened["source_check"]["status"] == "changed"


def test_project_cli_reports_invalid_extension(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.wav"
    _write_audio(source)
    assert main(["project-create", str(source), str(tmp_path / "bad.zip")]) == 1
    assert "ERROR:" in capsys.readouterr().err
