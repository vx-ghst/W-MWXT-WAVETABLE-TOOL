from __future__ import annotations

from pathlib import Path

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


def test_release_version_is_0_5_0() -> None:
    assert tool.__version__ == "0.5.0"


def test_public_package_exports_code_v5_contract() -> None:
    assert tool.CodeV5Analysis is analysis.CodeV5Analysis


def test_public_package_exports_code_v5_analyzer() -> None:
    assert tool.analyze_audio_source_code_v5 is analysis.analyze_audio_source_code_v5


def test_public_package_exports_code_v5_assembler() -> None:
    assert tool.assemble_code_v5_analysis is analysis.assemble_code_v5_analysis


def test_package_metadata_declares_0_5_0() -> None:
    root = Path(__file__).resolve().parents[1]
    assert 'version = "0.5.0"' in (root / "pyproject.toml").read_text(encoding="utf-8")


def test_readme_declares_code_v5_release() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "Current release:** `0.5.0` — CODE V5" in readme
    assert "analyze-audio" in readme
