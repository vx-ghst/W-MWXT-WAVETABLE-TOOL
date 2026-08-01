from __future__ import annotations

from importlib.metadata import version as distribution_version
from pathlib import Path

import pytest

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool.cli import main

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.0"


def test_public_api_version():
    assert tool.__version__ == VERSION


def test_distribution_version():
    assert distribution_version("W-MWXT-WAVETABLE-TOOL") == VERSION


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"W-MWXT-WAVETABLE-TOOL {VERSION}"


def test_pyproject_version():
    assert 'version = "0.6.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_readme_current_release():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Current release:** `0.6.0` — CODE V6" in readme
    assert "CodeV6Analysis" in readme
    assert "analyze-code-v6" in readme


def test_changelog_release():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 0.6.0 — CODE V6" in changelog


def test_release_notes():
    notes = (ROOT / "docs/releases/CODE_V6_RELEASE.md").read_text(encoding="utf-8")
    assert "CODE V6 Release — 0.6.0" in notes
    assert "CodeV6Analysis" in notes


def test_roadmap_marks_v6_complete():
    roadmap = (ROOT / "docs/roadmap/W-MWXT-WAVETABLE-TOOL_ROADMAP_AND_TRACEABILITY_MATRIX.md").read_text(encoding="utf-8")
    assert "**Baseline:** CODE V6 / `v0.6.0`" in roadmap
    assert "STATUS: COMPLETE" in roadmap
