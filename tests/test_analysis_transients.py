
from __future__ import annotations

import json

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import TransientChangeClass, analyze_transients
from w_mwxt_wavetable_tool.errors import AnalysisError

SAMPLE_RATE = 48000


def _sine(frequency: float = 440.0, seconds: float = 1.0, amplitude: float = 0.5) -> np.ndarray:
    time = np.arange(int(SAMPLE_RATE * seconds), dtype=np.float64) / SAMPLE_RATE
    return amplitude * np.sin(2.0 * np.pi * frequency * time)


def _analyze(samples: np.ndarray, **kwargs):
    return analyze_transients(samples, SAMPLE_RATE, frame_size=1024, hop_size=256, **kwargs)


def test_silence_has_no_events() -> None:
    result = _analyze(np.zeros(SAMPLE_RATE, dtype=np.float64))
    assert result.transient_change_class is TransientChangeClass.SILENT
    assert result.transient_count == 0
    assert result.change_point_count == 0


def test_steady_sine_has_no_transients() -> None:
    result = _analyze(_sine())
    assert result.transient_count == 0
    assert result.transient_change_class is TransientChangeClass.STEADY


def test_single_impulse_is_detected() -> None:
    samples = np.zeros(SAMPLE_RATE, dtype=np.float64)
    samples[SAMPLE_RATE // 2] = 1.0
    result = _analyze(samples, minimum_onset_strength=0.5)
    assert result.transient_count >= 1
    assert any(abs(event.time_seconds - 0.5) < 0.05 for event in result.transients)


def test_amplitude_step_creates_change_point() -> None:
    first = _sine(amplitude=0.1, seconds=0.5)
    second = _sine(amplitude=0.8, seconds=0.5)
    result = _analyze(np.concatenate([first, second]))
    assert result.change_point_count >= 1
    assert any(abs(event.time_seconds - 0.5) < 0.06 for event in result.change_points)


def test_frequency_step_creates_spectral_change() -> None:
    samples = np.concatenate([_sine(220.0, 0.5), _sine(880.0, 0.5)])
    result = _analyze(samples, change_spectral_flux_threshold=0.15)
    assert any(event.kind in {"spectral", "energy_and_spectral"} for event in result.change_points)


def test_click_train_is_transient_rich() -> None:
    samples = np.zeros(SAMPLE_RATE, dtype=np.float64)
    for index in range(0, SAMPLE_RATE, SAMPLE_RATE // 10):
        samples[index] = 1.0
    result = _analyze(samples, minimum_onset_strength=0.4)
    assert result.transient_count >= 5
    assert result.transient_change_class in {TransientChangeClass.TRANSIENT_RICH, TransientChangeClass.CHANGING}


def test_minimum_separation_reduces_duplicate_events() -> None:
    samples = np.zeros(SAMPLE_RATE, dtype=np.float64)
    center = SAMPLE_RATE // 2
    samples[center:center + 100] = 1.0
    dense = _analyze(samples, minimum_onset_strength=0.3, minimum_event_separation_ms=0.0)
    separated = _analyze(samples, minimum_onset_strength=0.3, minimum_event_separation_ms=100.0)
    assert separated.transient_count <= dense.transient_count


def test_configuration_is_recorded() -> None:
    result = _analyze(
        _sine(),
        sensitivity=4.0,
        minimum_onset_strength=0.8,
        change_energy_threshold_db=5.0,
        change_spectral_flux_threshold=0.25,
        minimum_event_separation_ms=30.0,
    )
    assert result.sensitivity == 4.0
    assert result.minimum_onset_strength == 0.8
    assert result.change_energy_threshold_db == 5.0
    assert result.change_spectral_flux_threshold == 0.25
    assert result.minimum_event_separation_ms == 30.0


def test_short_signal_uses_one_frame() -> None:
    result = _analyze(_sine(seconds=0.005))
    assert result.frame_count == 1
    assert result.transient_count == 0


def test_source_samples_are_not_modified() -> None:
    samples = _sine()
    before = samples.copy()
    _analyze(samples)
    assert np.array_equal(samples, before)


def test_deterministic_hash() -> None:
    samples = _sine()
    first = _analyze(samples)
    second = _analyze(samples)
    assert first.to_dict() == second.to_dict()
    assert first.analysis_sha256 == second.analysis_sha256


def test_hash_changes_when_signal_changes() -> None:
    first = _analyze(_sine())
    changed = _sine()
    changed[1000] += 0.2
    second = _analyze(changed)
    assert first.analysis_sha256 != second.analysis_sha256


def test_json_contains_no_nan_or_infinity() -> None:
    rendered = json.dumps(_analyze(np.zeros(4096)).to_dict(), allow_nan=False)
    assert "NaN" not in rendered and "Infinity" not in rendered


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan")])
def test_invalid_sensitivity_is_rejected(value: float) -> None:
    with pytest.raises(AnalysisError):
        _analyze(_sine(), sensitivity=value)


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan")])
def test_invalid_spectral_threshold_is_rejected(value: float) -> None:
    with pytest.raises(AnalysisError):
        _analyze(_sine(), change_spectral_flux_threshold=value)


def test_non_finite_samples_are_rejected() -> None:
    samples = _sine()
    samples[3] = np.nan
    with pytest.raises(AnalysisError):
        _analyze(samples)


def test_multichannel_samples_are_rejected() -> None:
    with pytest.raises(AnalysisError):
        _analyze(np.column_stack([_sine(), _sine()]))
