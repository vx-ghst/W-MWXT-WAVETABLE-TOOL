from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable
from w_mwxt_wavetable_tool.xt_package_cli import main


def _hash_document(document: dict[str, object]) -> dict[str, object]:
    rendered = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    document["analysis_sha256"] = sha256(rendered).hexdigest()
    return document


def test_cli_builds_without_transmission(tmp_path: Path, capsys) -> None:
    slots = []
    for index in range(61):
        stored = tuple(((sample + index * 2) % 127) - 63 for sample in range(64))
        slots.append(
            {
                "slot_number": index + 1,
                "kind": "anchor" if index in {0, 60} else "interpolated",
                "stored_samples": list(stored),
                "reconstructed_samples": list(stored + tuple(-v for v in reversed(stored))),
            }
        )
    trajectory = _hash_document(
        {
            "schema_version": 1,
            "slot_count": 61,
            "anchor_count": 2,
            "duplicate_adjacent_slot_pairs": [],
            "source_projection_set_sha256": "a" * 64,
            "boundaries": {"generates_sysex": False},
            "slots": slots,
        }
    )
    qc = _hash_document(
        {
            "schema_version": 1,
            "status": "pass",
            "source_trajectory_sha256": trajectory["analysis_sha256"],
            "source_projection_set_sha256": "a" * 64,
            "flagged_jump_count": 0,
            "flagged_curvature_count": 0,
            "boundaries": {
                "modifies_trajectory_slots": False,
                "generates_sysex": False,
            },
        }
    )
    trajectory_path = tmp_path / "trajectory.json"
    qc_path = tmp_path / "qc.json"
    trajectory_path.write_text(json.dumps(trajectory), encoding="utf-8")
    qc_path.write_text(json.dumps(qc), encoding="utf-8")

    messages = [UserWave(0, number, (-1,) * 64).to_message() for number in range(1189, 1250)]
    messages.append(
        UserWavetable(0, 127, tuple(range(1000, 1061)) + (1, 2, 3)).to_message()
    )
    sound_data = bytearray(256)
    sound_data[240:256] = b"BASELINE        "
    messages.append(SoundProgram(0, 1, 127, bytes(sound_data)).to_message())
    baseline_path = tmp_path / "baseline.syx"
    baseline_path.write_bytes(DumpFile(tuple(messages)).to_bytes())

    output_dir = tmp_path / "out"
    code = main(
        [
            "build",
            str(trajectory_path),
            str(qc_path),
            str(baseline_path),
            "--output-dir",
            str(output_dir),
            "--wave-start",
            "1189",
            "--wavetable",
            "128",
            "--sound",
            "B128",
            "--sound-name",
            "ODIUM KEY V7E",
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "pass"
    assert summary["message_count"] == 63
    assert summary["generates_sysex"] is True
    assert summary["transmits_midi"] is False
    assert summary["writes_hardware"] is False
    assert Path(summary["package_sysex"]).exists()
    assert Path(summary["restore_sysex"]).exists()
