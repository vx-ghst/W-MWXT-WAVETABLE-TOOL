from __future__ import annotations

import json
from pathlib import Path

from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable
from w_mwxt_wavetable_tool.xt_audio_gate_cli import main


def _baseline(path: Path) -> None:
    waves = tuple(
        UserWave(0, 1247 + index, tuple(((index + n) % 127) - 63 for n in range(64))).to_message()
        for index in range(3)
    )
    table = UserWavetable.from_display_number(
        0, 128, tuple(range(1000, 1061)) + (0, 1, 2)
    ).to_message()
    sound = SoundProgram(0, 1, 127, bytes(256)).to_message()
    path.write_bytes(DumpFile(waves + (table, sound)).to_bytes())


def test_audio_gate_cli_build_and_verify(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.syx"
    storage = tmp_path / "storage.json"
    restore = tmp_path / "restore.json"
    output = tmp_path / "out"
    _baseline(baseline)
    storage.write_text(
        json.dumps(
            {
                "status": "pass",
                "storage_passed": True,
                "v7_b_allowed_under_safe_range": True,
            }
        )
    )
    restore.write_text(json.dumps({"status": "pass", "verdict": "restore_confirmed"}))
    assert (
        main(
            [
                "build",
                str(baseline),
                str(storage),
                str(restore),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    setup = output / "CODE_V7_A2_XT_AUDIO_GATE.setup.syx"
    manifest = output / "CODE_V7_A2_XT_AUDIO_GATE.manifest.json"
    assert setup.is_file()
    assert manifest.is_file()
    assert (
        main(
            [
                "verify-setup",
                str(setup),
                str(setup),
                str(manifest),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )


def test_audio_gate_cli_analyze_missing_returns_two(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.syx"
    storage = tmp_path / "storage.json"
    restore = tmp_path / "restore.json"
    output = tmp_path / "out"
    _baseline(baseline)
    storage.write_text(
        json.dumps(
            {
                "status": "pass",
                "storage_passed": True,
                "v7_b_allowed_under_safe_range": True,
            }
        )
    )
    restore.write_text(json.dumps({"status": "pass", "verdict": "restore_confirmed"}))
    assert main(["build", str(baseline), str(storage), str(restore), "--output-dir", str(output)]) == 0
    assert (
        main(
            [
                "analyze",
                str(tmp_path / "captures"),
                str(output / "CODE_V7_A2_XT_AUDIO_GATE.manifest.json"),
                "--output-dir",
                str(output),
            ]
        )
        == 2
    )
