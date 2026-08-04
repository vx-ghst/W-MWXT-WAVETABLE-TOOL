from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from v8c_helpers import formant_like
from w_mwxt_wavetable_tool.analysis.formants import (
    FormantAnalysis,
    FormantCandidate,
    analyze_formants,
)
from w_mwxt_wavetable_tool.analysis.spectral import analyze_spectral


def spectral(samples: np.ndarray):
    return analyze_spectral(
        samples,
        16000,
        frame_size=1024,
        hop_size=256,
        fft_size=4096,
        low_band_max_hz=250.0,
        mid_band_max_hz=4000.0,
    )


def test_formant_like_signal_exposes_broad_envelope_candidates() -> None:
    result = analyze_formants(spectral(formant_like()))
    assert result.formant_structure_detected
    assert 2 <= len(result.candidates) <= 5
    frequencies = [candidate.frequency_hz for candidate in result.candidates]
    assert any(abs(value - 500.0) < 300.0 for value in frequencies)
    assert any(abs(value - 1500.0) < 400.0 for value in frequencies)
    assert all(candidate.confidence > 0.0 for candidate in result.candidates)


def test_silence_returns_explicit_zero_evidence_result() -> None:
    result = analyze_formants(spectral(np.zeros(16000, dtype=np.float64)))
    assert result.candidates == ()
    assert result.aggregate_confidence == 0.0
    assert not result.formant_structure_detected
    assert "No active" in result.reason


def test_formant_analysis_is_deterministic_and_json_safe() -> None:
    source = spectral(formant_like())
    first = analyze_formants(source)
    second = analyze_formants(source)
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256
    json.dumps(first.to_dict(), allow_nan=False, sort_keys=True)


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"minimum_frequency_hz": 0.0}, "bounds"),
        ({"maximum_frequency_hz": 50.0}, "bounds"),
        ({"smoothing_bandwidth_hz": 0.0}, "positive"),
        ({"minimum_prominence_db": -1.0}, "negative"),
        ({"minimum_separation_hz": 0.0}, "positive"),
        ({"maximum_candidates": 0}, "positive"),
    ],
)
def test_invalid_formant_configuration_is_rejected(kwargs, match) -> None:
    with pytest.raises(ValueError, match=match):
        analyze_formants(spectral(formant_like()), **kwargs)


def test_formant_model_rejects_non_finite_and_inconsistent_fields() -> None:
    candidate = FormantCandidate(
        index=0,
        frequency_hz=500.0,
        bandwidth_hz=100.0,
        envelope_power_ratio=0.1,
        prominence_db=3.0,
        confidence=0.5,
    )
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(candidate, confidence=2.0)

    result = analyze_formants(spectral(formant_like()))
    with pytest.raises(ValueError, match="inconsistent"):
        replace(result, formant_structure_detected=not result.formant_structure_detected)


def test_formant_search_range_is_clamped_to_nyquist() -> None:
    result = analyze_formants(spectral(formant_like()), maximum_frequency_hz=50000.0)
    assert result.maximum_frequency_hz == 8000.0


def test_candidate_indexes_and_frequency_order_are_canonical() -> None:
    result = analyze_formants(spectral(formant_like()))
    assert tuple(item.index for item in result.candidates) == tuple(
        range(len(result.candidates))
    )
    assert tuple(item.frequency_hz for item in result.candidates) == tuple(
        sorted(item.frequency_hz for item in result.candidates)
    )


def test_formant_analysis_requires_exact_spectral_type() -> None:
    with pytest.raises(TypeError, match="SpectralAnalysis"):
        analyze_formants(object())  # type: ignore[arg-type]
