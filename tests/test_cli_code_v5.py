from __future__ import annotations

import json
from pathlib import Path

import pytest

from w_mwxt_wavetable_tool import cli


class FakeSource:
    def to_summary(self) -> dict[str, object]:
        return {"sample_sha256": "a" * 64, "sample_rate": 48000}


class FakeAnalysis:
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": 1, "analysis_sha256": "b" * 64}


def test_parser_exposes_analyze_audio() -> None:
    args = cli._build_parser().parse_args(["analyze-audio", "source.wav"])
    assert args.command == "analyze-audio"
    assert args.file == Path("source.wav")


def test_analyze_audio_prints_aggregate_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "import_audio", lambda *args, **kwargs: FakeSource())
    monkeypatch.setattr(cli, "analyze_audio_source_code_v5", lambda source: FakeAnalysis())
    assert cli.main(["analyze-audio", "source.wav"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["audio"]["sample_rate"] == 48000
    assert payload["code_v5_analysis"]["schema_version"] == 1


def test_analyze_audio_writes_deterministic_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "import_audio", lambda *args, **kwargs: FakeSource())
    monkeypatch.setattr(cli, "analyze_audio_source_code_v5", lambda source: FakeAnalysis())
    report = tmp_path / "nested" / "report.json"
    assert cli.main(["analyze-audio", "source.wav", "--report", str(report)]) == 0
    assert report.read_text(encoding="utf-8").endswith("\n")
    assert json.loads(report.read_text(encoding="utf-8"))["code_v5_analysis"]["analysis_sha256"] == "b" * 64


def test_analyze_audio_forwards_policies(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    def fake_import(path: Path, **kwargs: object) -> FakeSource:
        captured["path"] = path
        captured.update(kwargs)
        return FakeSource()
    monkeypatch.setattr(cli, "import_audio", fake_import)
    monkeypatch.setattr(cli, "analyze_audio_source_code_v5", lambda source: FakeAnalysis())
    assert cli.main(["analyze-audio", "source.wav"]) == 0
    assert captured == {
        "path": Path("source.wav"),
        "mono_policy": "auto",
        "invalid_sample_policy": "reject",
    }


def test_analyze_audio_reports_boundary_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "import_audio", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad audio")))
    assert cli.main(["analyze-audio", "source.wav"]) == 1
    assert "bad audio" in capsys.readouterr().err
