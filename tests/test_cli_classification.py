from __future__ import annotations

import json
from types import SimpleNamespace

from w_mwxt_wavetable_tool import cli


def test_classify_audio_parser_defaults():
    args = cli._build_parser().parse_args(["classify-audio", "source.wav"])
    assert args.command == "classify-audio"
    assert args.file.name == "source.wav"
    assert args.mono_policy == "auto"
    assert args.invalid_sample_policy == "reject"
    assert args.report is None


def test_classify_audio_parser_accepts_import_policies(tmp_path):
    report = tmp_path / "classification.json"
    args = cli._build_parser().parse_args(
        [
            "classify-audio",
            "source.wav",
            "--mono-policy",
            "first_channel",
            "--invalid-sample-policy",
            "zero",
            "--report",
            str(report),
        ]
    )
    assert args.mono_policy == "first_channel"
    assert args.invalid_sample_policy == "zero"
    assert args.report == report


def _install_cli_fakes(monkeypatch):
    source = SimpleNamespace(to_summary=lambda: {"sample_sha256": "a" * 64})
    pitch = SimpleNamespace(frequency_hz=440.0)
    signal = SimpleNamespace(
        pitch_periodicity_analysis=pitch,
        to_dict=lambda: {"analysis_sha256": "b" * 64},
    )
    spectral = SimpleNamespace(
        to_dict=lambda: {"analysis_sha256": "c" * 64},
    )
    harmonic = SimpleNamespace(
        to_dict=lambda: {"analysis_sha256": "d" * 64},
    )
    classification = SimpleNamespace(
        to_dict=lambda: {
            "source_class": "stable_tonal",
            "confidence": 0.9,
            "analysis_sha256": "e" * 64,
        }
    )
    monkeypatch.setattr(cli, "import_audio", lambda *args, **kwargs: source)
    monkeypatch.setattr(cli, "analyze_audio_source_signal", lambda source: signal)
    monkeypatch.setattr(cli, "analyze_audio_source_spectral", lambda source: spectral)
    monkeypatch.setattr(
        cli,
        "analyze_harmonic_perceptual",
        lambda spectral, fundamental_frequency_hz: harmonic,
    )
    monkeypatch.setattr(
        cli,
        "classify_source",
        lambda signal, spectral, harmonic: classification,
    )


def test_classify_audio_cli_emits_linked_json(monkeypatch, capsys):
    _install_cli_fakes(monkeypatch)
    assert cli.main(["classify-audio", "source.wav"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["audio"]["sample_sha256"] == "a" * 64
    assert payload["signal_analysis"]["analysis_sha256"] == "b" * 64
    assert payload["spectral_analysis"]["analysis_sha256"] == "c" * 64
    assert payload["harmonic_perceptual_analysis"]["analysis_sha256"] == "d" * 64
    assert payload["source_classification"]["source_class"] == "stable_tonal"


def test_classify_audio_cli_writes_exact_report(monkeypatch, capsys, tmp_path):
    _install_cli_fakes(monkeypatch)
    report = tmp_path / "nested" / "classification.json"
    assert cli.main(["classify-audio", "source.wav", "--report", str(report)]) == 0
    stdout = capsys.readouterr().out
    assert report.read_text(encoding="utf-8") == stdout
    assert report.read_bytes().endswith(b"\n")
