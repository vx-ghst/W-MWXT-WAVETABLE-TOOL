from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from w_mwxt_wavetable_tool.xt.projection import (
    PROJECTION_SCHEMA_VERSION,
    XtProjectionSet,
    XtProjectionWeights,
    project_wave_xt_native,
    reconstruct_xt_native,
)
from w_mwxt_wavetable_tool.xt.trajectory import (
    XtPhasePathPolicy,
    XtTrajectoryConfig,
    build_xt_wavetable_trajectory_document,
)
from w_mwxt_wavetable_tool.xt_trajectory_qc_cli import main


def _projection_document() -> dict:
    waves = []
    for index, seed in enumerate((3, 31, 83, 127)):
        stored = tuple(
            int(np.clip(((seed + item * 37 + item * item) % 255) - 127, -127, 127))
            for item in range(64)
        )
        source = tuple(value / 127.0 for value in reconstruct_xt_native(stored))
        waves.append(
            project_wave_xt_native(
                source,
                index=index,
                candidate_index=index + 10,
                source_wave_sha256=f"{index + 1:064x}",
            )
        )
    return XtProjectionSet(
        schema_version=PROJECTION_SCHEMA_VERSION,
        tool_version="0.6.0",
        source_reconstructed_wave_set_sha256="a" * 64,
        source_code_v6_analysis_sha256=None,
        weights=XtProjectionWeights(),
        waves=tuple(waves),
        decision_reason="CLI fixture",
    ).to_dict()


def test_cli_writes_reports_and_three_previews(tmp_path: Path, capsys) -> None:
    projection = _projection_document()
    trajectory = build_xt_wavetable_trajectory_document(
        projection,
        config=XtTrajectoryConfig(
            target_slot_count=61,
            phase_path_policy=XtPhasePathPolicy.GLOBAL,
        ),
    ).to_dict()
    trajectory_path = tmp_path / "trajectory.json"
    projection_path = tmp_path / "projection.json"
    output = tmp_path / "out"
    trajectory_path.write_text(json.dumps(trajectory), encoding="utf-8")
    projection_path.write_text(json.dumps(projection), encoding="utf-8")
    exit_code = main(
        [
            "audit",
            str(trajectory_path),
            "--projection-report",
            str(projection_path),
            "--output-dir",
            str(output),
            "--sample-rate",
            "8000",
            "--preview-frequency",
            "100",
            "--sweep-duration",
            "0.12",
            "--slot-duration",
            "0.005",
            "--fade-duration",
            "0.001",
            "--jump-absolute-minimum",
            "1",
            "--curvature-absolute-minimum",
            "1",
        ]
    )
    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "pass"
    assert summary["adjacent_pair_count"] == 60
    assert summary["curvature_point_count"] == 59
    assert summary["baseline_comparison_included"] is True
    assert summary["generates_sysex"] is False
    assert summary["modifies_trajectory_slots"] is False
    assert Path(summary["json_report"]).exists()
    assert Path(summary["markdown_report"]).exists()
    assert len(summary["preview_files"]) == 3
    assert all(Path(path).exists() for path in summary["preview_files"])


def test_cli_strict_returns_three_for_review(tmp_path: Path, capsys) -> None:
    projection = _projection_document()
    trajectory = build_xt_wavetable_trajectory_document(
        projection,
        config=XtTrajectoryConfig(target_slot_count=61),
    ).to_dict()
    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(json.dumps(trajectory), encoding="utf-8")
    exit_code = main(
        [
            "audit",
            str(trajectory_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--sample-rate",
            "8000",
            "--preview-frequency",
            "100",
            "--sweep-duration",
            "0.10",
            "--slot-duration",
            "0.004",
            "--fade-duration",
            "0.001",
            "--jump-absolute-minimum",
            "0",
            "--jump-median-multiplier",
            "0",
            "--jump-mad-multiplier",
            "0",
            "--curvature-absolute-minimum",
            "0",
            "--curvature-median-multiplier",
            "0",
            "--curvature-mad-multiplier",
            "0",
            "--strict",
        ]
    )
    assert exit_code == 3
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "review"
