from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v6_changelog_history_is_preserved():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "## 0.6.0 — CODE V6" in changelog
    assert "CodeV6Analysis" in changelog
    assert "analyze-code-v6" in changelog


def test_v6_release_notes_are_preserved():
    notes = (
        ROOT
        / "docs"
        / "releases"
        / "CODE_V6_RELEASE.md"
    ).read_text(encoding="utf-8")

    assert "CODE V6 Release — 0.6.0" in notes
    assert "CodeV6Analysis" in notes
    assert "analyze-code-v6" in notes


def test_v6_validation_record_is_preserved():
    validation = (
        ROOT
        / "docs"
        / "validation"
        / "CODE_V6_F_VALIDATION.md"
    ).read_text(encoding="utf-8")

    assert "CODE V6-F Validation" in validation
    assert "Release : 0.6.0" in validation
    assert "CODE V6-F" in validation


def test_readme_preserves_v6_capabilities():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "### CODE V6 — working pitch" in readme
    assert "CodeV6Analysis" in readme
    assert "analyze-code-v6" in readme


def test_roadmap_preserves_v6_completion_history():
    roadmap = (
        ROOT
        / "docs"
        / "roadmap"
        / "W-MWXT-WAVETABLE-TOOL_ROADMAP_AND_TRACEABILITY_MATRIX.md"
    ).read_text(encoding="utf-8")

    assert "CODE V6" in roadmap
    assert "V6-E public baseline: 900 passed, 4 skipped" in roadmap
    assert "V6-E private baseline: 904 passed" in roadmap
