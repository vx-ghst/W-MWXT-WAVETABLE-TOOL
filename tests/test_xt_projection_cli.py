from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from w_mwxt_wavetable_tool.xt_projection_cli import main
from w_mwxt_wavetable_tool.xt.projection import reconstruct_xt_native


def _canonical(payload: dict) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return sha256(rendered).hexdigest()


def _write_source(path: Path) -> None:
    stored = tuple(((index * 23) % 255) - 127 for index in range(64))
    samples = [value / 127.0 for value in reconstruct_xt_native(stored)]
    wave_content = {"index": 0, "candidate_index": 4, "samples": samples}
    wave = dict(wave_content)
    wave["wave_sha256"] = _canonical(wave_content)
    set_content = {
        "schema_version": 1,
        "tool_version": "0.6.0",
        "target_sample_count": 128,
        "waves": [wave],
    }
    document = dict(set_content)
    document["analysis_sha256"] = _canonical(set_content)
    path.write_text(json.dumps(document), encoding="utf-8")


def test_cli_projects_json_and_writes_reports(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.json"
    _write_source(source)
    status = main(["project", str(source), "--output-dir", str(tmp_path)])
    assert status == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "pass"
    assert summary["wave_count"] == 1
    assert summary["generates_sysex"] is False
    assert Path(summary["json_report"]).exists()
    assert Path(summary["markdown_report"]).exists()


def test_cli_rejects_weight_sum_mismatch(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.json"
    _write_source(source)
    status = main([
        "project",
        str(source),
        "--output-dir",
        str(tmp_path),
        "--time-weight",
        "0.5",
    ])
    assert status == 2
    assert "sum exactly" in capsys.readouterr().err
