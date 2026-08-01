from __future__ import annotations

import json
from pathlib import Path

from w_mwxt_wavetable_tool.xt.projection import (
    PROJECTION_SCHEMA_VERSION,
    XtProjectionSet,
    XtProjectionWeights,
    project_wave_xt_native,
    reconstruct_xt_native,
)
from w_mwxt_wavetable_tool.xt_trajectory_cli import main


def _write_projection(path: Path) -> None:
    waves = []
    for wave_index, seed in enumerate((7, 43, 89)):
        stored = tuple(((seed + index * 17) % 255) - 127 for index in range(64))
        source = tuple(value / 127.0 for value in reconstruct_xt_native(stored))
        waves.append(
            project_wave_xt_native(
                source,
                index=wave_index,
                candidate_index=wave_index + 10,
                source_wave_sha256=f"{wave_index + 1:064x}",
            )
        )
    result = XtProjectionSet(
        schema_version=PROJECTION_SCHEMA_VERSION,
        tool_version="0.6.0",
        source_reconstructed_wave_set_sha256="b" * 64,
        source_code_v6_analysis_sha256=None,
        weights=XtProjectionWeights(),
        waves=tuple(waves),
        decision_reason="CLI fixture",
    )
    path.write_text(result.to_json(), encoding="utf-8")


def test_cli_builds_61_position_report(tmp_path: Path, capsys) -> None:
    source = tmp_path / "projection.json"
    _write_projection(source)
    status = main(["build", str(source), "--output-dir", str(tmp_path)])
    assert status == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "pass"
    assert summary["anchor_count"] == 3
    assert summary["interpolated_slot_count"] == 58
    assert summary["slot_count"] == 61
    assert summary["generates_sysex"] is False
    assert Path(summary["json_report"]).exists()
    assert Path(summary["markdown_report"]).exists()


def test_cli_rejects_invalid_weight_sum(tmp_path: Path, capsys) -> None:
    source = tmp_path / "projection.json"
    _write_projection(source)
    status = main([
        "build",
        str(source),
        "--output-dir",
        str(tmp_path),
        "--local-fidelity-weight",
        "0.5",
    ])
    assert status == 2
    assert "sum exactly" in capsys.readouterr().err
