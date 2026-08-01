from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool import cli


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("pitch_policy", "auto"),
        ("attack_policy", "auto"),
        ("selection_policy", "auto"),
        ("top_n", 16),
        ("reconstruction_strategy", "auto"),
        ("target_sample_count", 128),
        ("maximum_partials", 32),
        ("normalization_peak", 0.98),
    ],
)
def test_parser_defaults(attribute, expected):
    args = cli._build_parser().parse_args(["analyze-code-v6", "source.wav"])
    assert getattr(args, attribute) == expected


def fake_source():
    return SimpleNamespace(to_summary=lambda: {"sample_sha256": "a" * 64})


def fake_analysis():
    return SimpleNamespace(to_dict=lambda: {"tool_version": "0.6.0", "analysis_sha256": "b" * 64})


def test_command_prints_final_aggregate(monkeypatch, capsys):
    monkeypatch.setattr(cli, "import_audio", lambda *a, **k: fake_source())
    monkeypatch.setattr(cli, "analyze_audio_source_code_v6", lambda *a, **k: fake_analysis())
    assert cli.main(["analyze-code-v6", "source.wav"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"audio", "code_v6_analysis"}
    assert payload["code_v6_analysis"]["tool_version"] == "0.6.0"


def test_command_writes_lf_report(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(cli, "import_audio", lambda *a, **k: fake_source())
    monkeypatch.setattr(cli, "analyze_audio_source_code_v6", lambda *a, **k: fake_analysis())
    report = tmp_path / "report.json"
    assert cli.main(["analyze-code-v6", "source.wav", "--report", str(report)]) == 0
    capsys.readouterr()
    raw = report.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r\n" not in raw


def test_command_forwards_configuration(monkeypatch, capsys):
    captured = {}
    monkeypatch.setattr(cli, "import_audio", lambda *a, **k: fake_source())
    monkeypatch.setattr(cli, "analyze_audio_source_code_v6", lambda source, **kwargs: captured.update(kwargs) or fake_analysis())
    args = [
        "analyze-code-v6", "source.wav", "--pitch-policy", "lock",
        "--locked-frequency", "330", "--attack-policy", "keep",
        "--selection-policy", "force", "--forced-candidate-index", "7",
        "--top-n", "8", "--reconstruction-strategy", "hybrid",
        "--target-sample-count", "256", "--keep-dc",
    ]
    assert cli.main(args) == 0
    capsys.readouterr()
    assert captured["working_pitch_policy"] == "lock"
    assert captured["locked_frequency_hz"] == 330.0
    assert captured["attack_policy"] == "keep"
    assert captured["selection_policy"] == "force"
    assert captured["forced_candidate_index"] == 7
    assert captured["top_n"] == 8
    assert captured["reconstruction_strategy"] == "hybrid"
    assert captured["reconstruction_kwargs"]["target_sample_count"] == 256
    assert captured["reconstruction_kwargs"]["remove_dc"] is False


def test_help_lists_final_command(capsys):
    parser = cli._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    assert "analyze-code-v6" in capsys.readouterr().out


def test_legacy_code_v5_command_remains_available():
    args = cli._build_parser().parse_args(["analyze-audio", "source.wav"])
    assert args.command == "analyze-audio"
