from __future__ import annotations

import json
from types import SimpleNamespace

from w_mwxt_wavetable_tool import cli


class Serializable:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


class Source:
    def to_summary(self):
        return {"sample_sha256": "a" * 64}


def install_pipeline(monkeypatch, *, calls=None):
    signal = SimpleNamespace(
        pitch_periodicity_analysis=SimpleNamespace(frequency_hz=440.0),
        to_dict=lambda: {"analysis_sha256": "b" * 64},
    )
    spectral = Serializable({"analysis_sha256": "c" * 64})
    harmonic = Serializable({"analysis_sha256": "d" * 64})
    classification = Serializable({"analysis_sha256": "e" * 64})
    decision = Serializable({"status": "ready", "analysis_sha256": "f" * 64})

    def import_audio(path, mono_policy, invalid_sample_policy):
        if calls is not None:
            calls.append((path.name, mono_policy, invalid_sample_policy))
        return Source()

    monkeypatch.setattr(cli, "import_audio", import_audio)
    monkeypatch.setattr(cli, "analyze_audio_source_signal", lambda source: signal)
    monkeypatch.setattr(cli, "analyze_audio_source_spectral", lambda source: spectral)
    monkeypatch.setattr(cli, "analyze_harmonic_perceptual", lambda spectrum, fundamental_frequency_hz: harmonic)
    monkeypatch.setattr(cli, "classify_source", lambda *args: classification)
    monkeypatch.setattr(cli, "decide_wavetable_readiness", lambda value: decision)
    return decision


def test_parser_recognizes_recommend_audio():
    args = cli._build_parser().parse_args(["recommend-audio", "source.wav"])
    assert args.command == "recommend-audio"


def test_cli_outputs_engineering_decision(monkeypatch, capsys):
    install_pipeline(monkeypatch)
    assert cli.main(["recommend-audio", "source.wav"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["engineering_decision"]["status"] == "ready"


def test_cli_writes_report(monkeypatch, tmp_path):
    install_pipeline(monkeypatch)
    report = tmp_path / "report.json"
    assert cli.main(["recommend-audio", "source.wav", "--report", str(report)]) == 0
    assert json.loads(report.read_text())["engineering_decision"]["status"] == "ready"


def test_cli_report_is_deterministic(monkeypatch, tmp_path):
    install_pipeline(monkeypatch)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    cli.main(["recommend-audio", "source.wav", "--report", str(first)])
    cli.main(["recommend-audio", "source.wav", "--report", str(second)])
    assert first.read_bytes() == second.read_bytes()


def test_cli_passes_import_policies(monkeypatch):
    calls = []
    install_pipeline(monkeypatch, calls=calls)
    cli.main([
        "recommend-audio",
        "source.wav",
        "--mono-policy",
        "average",
        "--invalid-sample-policy",
        "zero",
    ])
    assert calls == [("source.wav", "average", "zero")]


def test_cli_calls_decision_engine(monkeypatch):
    decision = install_pipeline(monkeypatch)
    seen = []
    monkeypatch.setattr(cli, "decide_wavetable_readiness", lambda value: seen.append(value) or decision)
    cli.main(["recommend-audio", "source.wav"])
    assert len(seen) == 1


def test_classify_audio_remains_without_decision(monkeypatch, capsys):
    install_pipeline(monkeypatch)
    assert cli.main(["classify-audio", "source.wav"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "engineering_decision" not in payload
