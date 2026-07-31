from __future__ import annotations

from importlib.metadata import version as distribution_version
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool.cli import main
from w_mwxt_wavetable_tool.project import open_project


EXPECTED_VERSION = "0.4.0"
ROOT = Path(__file__).resolve().parents[1]


def test_public_api_reports_code_v4_version() -> None:
    assert tool.__version__ == EXPECTED_VERSION


def test_distribution_metadata_reports_code_v4_version() -> None:
    assert distribution_version("W-MWXT-WAVETABLE-TOOL") == EXPECTED_VERSION


def test_cli_reports_code_v4_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"W-MWXT-WAVETABLE-TOOL {EXPECTED_VERSION}"


def test_project_created_by_cli_records_code_v4_version(tmp_path: Path, capsys) -> None:
    source = tmp_path / "release.wav"
    project_path = tmp_path / "release.mwxtproj"
    sf.write(source, np.linspace(-0.25, 0.25, 128), 44100, subtype="FLOAT")
    assert main(["project-create", str(source), str(project_path)]) == 0
    capsys.readouterr()
    project = open_project(project_path)
    assert project.manifest.tool_version == EXPECTED_VERSION


def test_pyproject_release_version_matches_public_api() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{EXPECTED_VERSION}"' in text


def test_readme_and_changelog_declare_code_v4_release() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Current release:** `0.4.0` — CODE V4" in readme
    assert "## 0.4.0 — CODE V4" in changelog
    assert "SignalAnalysis" in readme
