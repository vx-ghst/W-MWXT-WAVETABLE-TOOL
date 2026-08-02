from __future__ import annotations

from importlib.metadata import version as distribution_version
from pathlib import Path

import pytest

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool.cli import main

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.7.0"


def test_public_api_version():
    assert tool.__version__ == VERSION


def test_distribution_version():
    assert distribution_version("W-MWXT-WAVETABLE-TOOL") == VERSION


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"W-MWXT-WAVETABLE-TOOL {VERSION}"


def test_version_files():
    assert 'version = "0.7.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "0.7.0"' in (
        ROOT / "src" / "w_mwxt_wavetable_tool" / "version.py"
    ).read_text(encoding="utf-8")


def test_readme_release():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Current release:** `0.7.0` — CODE V7" in readme
    assert "W-MWXT-XT-PACKAGE --help" in readme
    assert "63/63" in readme


def test_changelog_release():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 0.7.0 — CODE V7" in changelog
    assert "1035 passed" in changelog
    assert "1039 passed" in changelog


def test_release_notes():
    notes = (ROOT / "docs" / "releases" / "CODE_V7_RELEASE.md").read_text(encoding="utf-8")
    assert "CODE V7 Release — 0.7.0" in notes
    assert "61 User Wave WAVD messages" in notes
    assert "Final installation : 63/63 exact" in notes
    assert "Final public suite          : 1035 passed, 4 skipped" in notes
    assert "Final private suite         : 1039 passed" in notes


def test_validation_document():
    validation = (
        ROOT / "docs" / "validation" / "CODE_V7_F_VALIDATION.md"
    ).read_text(encoding="utf-8")
    assert "Release : 0.7.0" in validation
    assert "Final public suite       : 1035 passed, 4 skipped" in validation
    assert "Final private suite      : 1039 passed" in validation
    assert "PASS_EXACT" in validation


def test_roadmap_marks_v7_complete():
    roadmap = (
        ROOT / "docs" / "roadmap" / "W-MWXT-WAVETABLE-TOOL_ROADMAP_AND_TRACEABILITY_MATRIX.md"
    ).read_text(encoding="utf-8")
    assert "**Baseline:** CODE V7 / `v0.7.0`" in roadmap
    assert "STATUS: COMPLETE" in roadmap
    assert "RELEASE: v0.7.0" in roadmap


def test_v7_console_scripts_are_declared():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for script in (
        "W-MWXT-XT-GATE",
        "W-MWXT-XT-AUDIO-GATE",
        "W-MWXT-XT-PROJECT",
        "W-MWXT-XT-TRAJECTORY",
        "W-MWXT-XT-QC",
        "W-MWXT-XT-PACKAGE",
    ):
        assert script in pyproject


def test_public_release_files_exclude_private_evidence():
    paths = (
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "docs" / "releases" / "CODE_V7_RELEASE.md",
        ROOT / "docs" / "validation" / "CODE_V7_F_VALIDATION.md",
        ROOT / "docs" / "roadmap" / "W-MWXT-WAVETABLE-TOOL_ROADMAP_AND_TRACEABILITY_MATRIX.md",
    )
    forbidden = (
        "W-MWXT-" + "V7F",
        "W-MWXT-" + "PRIVATE-DUMPS",
        "CODE_V7_F_" + "CLOSURE_EVIDENCE",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for value in forbidden:
            assert value not in text
