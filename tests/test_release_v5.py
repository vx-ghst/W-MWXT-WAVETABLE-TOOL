from __future__ import annotations

from importlib.metadata import version as distribution_version
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool.cli import main
from w_mwxt_wavetable_tool.project import open_project

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = "0.6.0"


def test_public_api_reports_current_release() -> None:
    assert tool.__version__ == CURRENT_VERSION


def test_distribution_metadata_matches_public_api() -> None:
    assert distribution_version("W-MWXT-WAVETABLE-TOOL") == CURRENT_VERSION


def test_cli_reports_current_release(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"W-MWXT-WAVETABLE-TOOL {CURRENT_VERSION}"


def test_project_created_by_cli_records_current_release(tmp_path: Path, capsys) -> None:
    source = tmp_path / "release.wav"
    project_path = tmp_path / "release.mwxtproj"
    sf.write(source, np.linspace(-0.25, 0.25, 128), 44100, subtype="FLOAT")
    assert main(["project-create", str(source), str(project_path)]) == 0
    capsys.readouterr()
    project = open_project(project_path)
    assert project.manifest.tool_version == CURRENT_VERSION


def test_v5_release_remains_historically_documented() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs" / "releases" / "CODE_V5_RELEASE.md").read_text(encoding="utf-8")
    assert "## 0.5.0 — CODE V5" in changelog
    assert "CODE V5 Release — 0.5.0" in release_notes
