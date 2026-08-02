from __future__ import annotations

from pathlib import Path

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


def test_current_release_is_code_v7() -> None:
    assert tool.__version__ == "0.7.0"


def test_public_package_still_exports_code_v5_contract() -> None:
    assert tool.CodeV5Analysis is analysis.CodeV5Analysis
    assert tool.analyze_audio_source_code_v5 is analysis.analyze_audio_source_code_v5
    assert tool.assemble_code_v5_analysis is analysis.assemble_code_v5_analysis


def test_package_metadata_declares_current_release() -> None:
    root = Path(__file__).resolve().parents[1]
    assert 'version = "0.7.0"' in (root / "pyproject.toml").read_text(encoding="utf-8")


def test_readme_preserves_code_v5_and_adds_code_v6() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "### CODE V5" in readme
    assert "### CODE V6" in readme
    assert "analyze-audio" in readme
    assert "analyze-code-v6" in readme
