from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from w_mwxt_wavetable_tool import cli


class _Report:
    def __init__(self, name: str):
        self.name = name
        self.pitch_periodicity_analysis = SimpleNamespace()

    def to_dict(self):
        return {"name": self.name}


class _Source:
    def __init__(self):
        self.mono_samples = np.array([0.0, 0.5, 0.0, -0.5] * 32, dtype=np.float64)

    def to_summary(self):
        return {"sample_sha256": "a" * 64}


def _install_chain(monkeypatch, captured=None):
    source = _Source()
    signal = _Report("signal")
    plan = _Report("plan")
    segmentation = _Report("segmentation")
    cycles = _Report("cycles")
    selected = _Report("selected")
    reconstructed = _Report("reconstructed")
    monkeypatch.setattr(cli, "import_audio", lambda *args, **kwargs: source)
    monkeypatch.setattr(cli, "analyze_audio_source_signal", lambda value: signal)
    monkeypatch.setattr(cli, "plan_working_pitch", lambda *args, **kwargs: plan)
    monkeypatch.setattr(cli, "segment_source", lambda *args, **kwargs: segmentation)
    monkeypatch.setattr(cli, "discover_cycles", lambda *args, **kwargs: cycles)
    monkeypatch.setattr(cli, "select_representative_cycles", lambda *args, **kwargs: selected)

    def reconstruct(*args, **kwargs):
        if captured is not None:
            captured.update(kwargs)
        return reconstructed

    monkeypatch.setattr(cli, "reconstruct_selected_cycles", reconstruct)


def test_reconstruct_waves_help_is_registered(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["reconstruct-waves", "--help"])
    assert exc.value.code == 0
    assert "--reconstruction-strategy" in capsys.readouterr().out


def test_reconstruct_waves_prints_complete_chain(monkeypatch, capsys):
    _install_chain(monkeypatch)
    assert cli.main(["reconstruct-waves", "source.wav"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert list(data) == sorted(data)
    assert data["reconstructed_wave_set"] == {"name": "reconstructed"}
    assert data["selected_cycle_set"] == {"name": "selected"}


def test_reconstruction_options_are_forwarded(monkeypatch, capsys):
    captured = {}
    _install_chain(monkeypatch, captured)
    assert cli.main(
        [
            "reconstruct-waves",
            "source.wav",
            "--reconstruction-strategy",
            "partial",
            "--target-sample-count",
            "256",
            "--maximum-partials",
            "12",
            "--hybrid-time-weight",
            "0.25",
            "--normalization-peak",
            "0.90",
            "--keep-dc",
        ]
    ) == 0
    capsys.readouterr()
    assert captured == {
        "strategy": "partial",
        "target_sample_count": 256,
        "maximum_partials": 12,
        "hybrid_time_weight": 0.25,
        "normalization_peak": 0.90,
        "remove_dc": False,
    }


def test_reconstruction_report_is_written(monkeypatch, tmp_path, capsys):
    _install_chain(monkeypatch)
    report = tmp_path / "nested" / "report.json"
    assert cli.main(
        ["reconstruct-waves", "source.wav", "--report", str(report)]
    ) == 0
    rendered = capsys.readouterr().out
    assert report.read_text(encoding="utf-8") == rendered
    assert rendered.endswith("\n")


def test_invalid_reconstruction_strategy_is_rejected():
    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "reconstruct-waves",
                "source.wav",
                "--reconstruction-strategy",
                "invalid",
            ]
        )
    assert exc.value.code == 2
