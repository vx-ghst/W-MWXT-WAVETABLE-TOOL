from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool import cli


def test_parser_accepts_cycle_discovery_defaults() -> None:
    args = cli._build_parser().parse_args(["discover-cycles", "source.wav"])
    assert args.command == "discover-cycles"
    assert args.pitch_policy == "auto"
    assert args.attack_policy == "auto"
    assert args.maximum_cycles_per_segment == 64


def test_parser_accepts_explicit_quality_configuration() -> None:
    args = cli._build_parser().parse_args(
        [
            "discover-cycles",
            "source.wav",
            "--maximum-cycles-per-segment",
            "12",
            "--minimum-periodicity-score",
            "0.8",
            "--minimum-seam-score",
            "0.5",
        ]
    )
    assert args.maximum_cycles_per_segment == 12
    assert args.minimum_periodicity_score == 0.8
    assert args.minimum_seam_score == 0.5


def test_parser_rejects_unknown_attack_policy() -> None:
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(
            ["discover-cycles", "source.wav", "--attack-policy", "unknown"]
        )


def test_discover_cycles_writes_report(monkeypatch, tmp_path, capsys) -> None:
    source = SimpleNamespace(
        mono_samples=[0.0, 1.0, 0.0, -1.0],
        to_summary=lambda: {"sample_sha256": "a" * 64},
    )
    signal = SimpleNamespace(
        pitch_periodicity_analysis=SimpleNamespace(),
        to_dict=lambda: {"analysis_sha256": "b" * 64},
    )
    plan = SimpleNamespace(to_dict=lambda: {"analysis_sha256": "c" * 64})
    segmentation = SimpleNamespace(to_dict=lambda: {"analysis_sha256": "d" * 64})
    cycles = SimpleNamespace(to_dict=lambda: {"analysis_sha256": "e" * 64})
    monkeypatch.setattr(cli, "import_audio", lambda *args, **kwargs: source)
    monkeypatch.setattr(cli, "analyze_audio_source_signal", lambda value: signal)
    monkeypatch.setattr(cli, "plan_working_pitch", lambda *args, **kwargs: plan)
    monkeypatch.setattr(cli, "segment_source", lambda *args, **kwargs: segmentation)
    monkeypatch.setattr(cli, "discover_cycles", lambda *args, **kwargs: cycles)
    report = tmp_path / "cycles.json"
    status = cli.main(["discover-cycles", "source.wav", "--report", str(report)])
    assert status == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert set(payload) == {
        "audio",
        "signal_analysis",
        "working_pitch_plan",
        "segmentation_analysis",
        "cycle_discovery_analysis",
    }
    assert json.loads(capsys.readouterr().out) == payload


def test_discover_cycles_returns_one_on_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "import_audio",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    assert cli.main(["discover-cycles", "source.wav"]) == 1
    assert "ERROR: boom" in capsys.readouterr().err
