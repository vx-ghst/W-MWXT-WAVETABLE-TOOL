from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool import cli


def test_parser_accepts_segment_audio_defaults():
    args = cli._build_parser().parse_args(["segment-audio", "source.wav"])
    assert args.command == "segment-audio"
    assert args.attack_policy == "auto"
    assert args.pitch_policy == "auto"


def test_parser_accepts_explicit_attack_reject():
    args = cli._build_parser().parse_args(["segment-audio", "source.wav", "--attack-policy", "reject"])
    assert args.attack_policy == "reject"


def test_parser_rejects_unknown_attack_policy():
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(["segment-audio", "source.wav", "--attack-policy", "unknown"])


def test_segment_audio_writes_report(monkeypatch, tmp_path, capsys):
    source = SimpleNamespace(to_summary=lambda: {"sample_sha256": "a" * 64})
    signal = SimpleNamespace(
        pitch_periodicity_analysis=SimpleNamespace(),
        to_dict=lambda: {"analysis_sha256": "b" * 64},
    )
    plan = SimpleNamespace(to_dict=lambda: {"analysis_sha256": "c" * 64})
    segmentation = SimpleNamespace(to_dict=lambda: {"analysis_sha256": "d" * 64})
    monkeypatch.setattr(cli, "import_audio", lambda *args, **kwargs: source)
    monkeypatch.setattr(cli, "analyze_audio_source_signal", lambda source: signal)
    monkeypatch.setattr(cli, "plan_working_pitch", lambda *args, **kwargs: plan)
    monkeypatch.setattr(cli, "segment_source", lambda *args, **kwargs: segmentation)
    report = tmp_path / "segment.json"
    status = cli.main(["segment-audio", "source.wav", "--report", str(report)])
    assert status == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert set(payload) == {"audio", "signal_analysis", "working_pitch_plan", "segmentation_analysis"}
    assert json.loads(capsys.readouterr().out) == payload


def test_segment_audio_returns_one_on_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "import_audio", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")))
    assert cli.main(["segment-audio", "source.wav"]) == 1
    assert "ERROR: boom" in capsys.readouterr().err
