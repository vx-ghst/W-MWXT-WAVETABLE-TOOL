from __future__ import annotations

import json
from pathlib import Path

from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.models import UserWave
from w_mwxt_wavetable_tool.xt import (
    XtReconstructionGatePlan,
    XtReconstructionHypothesis,
    reconstruct_probe,
)
from w_mwxt_wavetable_tool.xt_gate_cli import main


def _write_baseline(path: Path, start: int = 1247) -> None:
    dump = DumpFile(
        tuple(
            UserWave(
                0,
                start + index,
                tuple(((sample * 11 + index * 23) % 255) - 127 for sample in range(64)),
            ).to_message()
            for index in range(3)
        )
    )
    path.write_bytes(dump.to_bytes())


def test_cli_build_and_storage_analysis_passes_without_observation(
    tmp_path: Path, capsys
) -> None:
    baseline = tmp_path / "baseline.syx"
    _write_baseline(baseline)
    output = tmp_path / "gate"
    assert main(["build", str(baseline), "--output-dir", str(output)]) == 0
    build_output = json.loads(capsys.readouterr().out)
    assert build_output["status"] == "READY"
    assert build_output["schema_version"] == 2

    assert main(
        [
            "analyze",
            build_output["probe_package"],
            build_output["probe_package"],
            build_output["manifest_json"],
            "--output-dir",
            str(output),
        ]
    ) == 0
    analysis_output = json.loads(capsys.readouterr().out)
    assert analysis_output["status"] == "pass"
    assert analysis_output["storage_passed"] is True
    assert analysis_output["v7_b_allowed_under_safe_range"] is True
    assert analysis_output["negative_full_scale_status"] == (
        "pending_hardware_characterization"
    )


def test_cli_analyze_with_unique_edge_observation_passes(
    tmp_path: Path, capsys
) -> None:
    baseline = tmp_path / "baseline.syx"
    _write_baseline(baseline)
    output = tmp_path / "gate"
    assert main(["build", str(baseline), "--output-dir", str(output)]) == 0
    build_output = json.loads(capsys.readouterr().out)
    plan = XtReconstructionGatePlan.from_json(
        Path(build_output["manifest_json"]).read_text(encoding="utf-8")
    )
    observation = {
        "schema_version": 2,
        "gate_plan_sha256": plan.plan_sha256,
        "measurement_method": "independent digital phase-aligned capture",
        "cycles": [
            {
                "target_wave_number": probe.target_wave_number,
                "samples": list(
                    reconstruct_probe(
                        probe,
                        XtReconstructionHypothesis.REVERSE_NEGATE_SATURATE_I8,
                    )
                ),
            }
            for probe in plan.probes
        ],
    }
    observation_path = output / "observed.json"
    observation_path.write_text(json.dumps(observation), encoding="utf-8")

    assert main(
        [
            "analyze",
            build_output["probe_package"],
            build_output["probe_package"],
            build_output["manifest_json"],
            "--observations",
            str(observation_path),
            "--output-dir",
            str(output),
        ]
    ) == 0
    analysis_output = json.loads(capsys.readouterr().out)
    assert analysis_output["status"] == "pass"
    assert analysis_output["verdict"] == (
        "documented_reconstruction_and_edge_saturate_i8_confirmed"
    )


def test_cli_verify_restore(tmp_path: Path, capsys) -> None:
    baseline = tmp_path / "baseline.syx"
    _write_baseline(baseline)
    output = tmp_path / "gate"
    assert main(["build", str(baseline), "--output-dir", str(output)]) == 0
    build_output = json.loads(capsys.readouterr().out)
    assert main(
        [
            "verify-restore",
            build_output["restore_bundle"],
            build_output["restore_bundle"],
            build_output["manifest_json"],
            "--output-dir",
            str(output),
        ]
    ) == 0
    restore_output = json.loads(capsys.readouterr().out)
    assert restore_output["verdict"] == "restore_confirmed"
