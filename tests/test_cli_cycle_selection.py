from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool import cli


def test_parser_accepts_cycle_selection_defaults() -> None:
    args = cli._build_parser().parse_args(["select-cycles", "source.wav"])
    assert args.command == "select-cycles"
    assert args.selection_policy == "auto"
    assert args.top_n == 16
    assert args.minimum_temporal_separation_periods == 1.0


def test_parser_accepts_forced_override_configuration() -> None:
    args = cli._build_parser().parse_args(
        [
            "select-cycles",
            "source.wav",
            "--selection-policy",
            "force",
            "--forced-candidate-index",
            "7",
            "--allow-rejected-forced-candidate",
            "--top-n",
            "12",
        ]
    )
    assert args.selection_policy == "force"
    assert args.forced_candidate_index == 7
    assert args.allow_rejected_forced_candidate is True
    assert args.top_n == 12


def test_parser_rejects_unknown_selection_policy() -> None:
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(
            ["select-cycles", "source.wav", "--selection-policy", "unknown"]
        )


def test_select_cycles_writes_complete_report(monkeypatch, tmp_path, capsys) -> None:
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
    selected = SimpleNamespace(to_dict=lambda: {"analysis_sha256": "f" * 64})
    monkeypatch.setattr(cli, "import_audio", lambda *args, **kwargs: source)
    monkeypatch.setattr(cli, "analyze_audio_source_signal", lambda value: signal)
    monkeypatch.setattr(cli, "plan_working_pitch", lambda *args, **kwargs: plan)
    monkeypatch.setattr(cli, "segment_source", lambda *args, **kwargs: segmentation)
    monkeypatch.setattr(cli, "discover_cycles", lambda *args, **kwargs: cycles)
    monkeypatch.setattr(
        cli,
        "select_representative_cycles",
        lambda *args, **kwargs: selected,
    )
    report = tmp_path / "selection.json"
    status = cli.main(["select-cycles", "source.wav", "--report", str(report)])
    assert status == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert set(payload) == {
        "audio",
        "signal_analysis",
        "working_pitch_plan",
        "segmentation_analysis",
        "cycle_discovery_analysis",
        "selected_cycle_set",
    }
    assert json.loads(capsys.readouterr().out) == payload


def test_select_cycles_returns_one_on_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "import_audio",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    assert cli.main(["select-cycles", "source.wav"]) == 1
    assert "ERROR: boom" in capsys.readouterr().err
