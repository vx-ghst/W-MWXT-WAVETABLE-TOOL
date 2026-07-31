from __future__ import annotations

from importlib.metadata import version as distribution_version
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool.cli import main
from w_mwxt_wavetable_tool.project import open_project


EXPECTED_VERSION = "0.3.0"


def test_public_api_reports_code_v3_version() -> None:
    assert tool.__version__ == EXPECTED_VERSION


def test_distribution_metadata_reports_code_v3_version() -> None:
    assert distribution_version("W-MWXT-WAVETABLE-TOOL") == EXPECTED_VERSION


def test_cli_reports_code_v3_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == (
        f"W-MWXT-WAVETABLE-TOOL {EXPECTED_VERSION}"
    )


def test_project_created_by_cli_records_code_v3_version(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "release.wav"
    project_path = tmp_path / "release.mwxtproj"
    sf.write(source, np.linspace(-0.25, 0.25, 128), 44100, subtype="FLOAT")

    assert main(["project-create", str(source), str(project_path)]) == 0
    capsys.readouterr()

    project = open_project(project_path)
    assert project.manifest.tool_version == EXPECTED_VERSION
    assert project.to_summary()["project"]["tool_version"] == EXPECTED_VERSION
