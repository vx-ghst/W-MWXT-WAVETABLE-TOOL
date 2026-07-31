from __future__ import annotations

import numpy as np
import pytest

from w_mwxt_wavetable_tool.audio import measure_mono


def test_silence_measurements() -> None:
    result = measure_mono(np.zeros(128, dtype=np.float64))
    assert result.is_silent
    assert result.rms == 0.0
    assert result.peak_absolute == 0.0
    assert not result.has_dc_offset


def test_dc_offset_is_reported_without_modifying_samples() -> None:
    source = np.full(64, 0.25, dtype=np.float64)
    result = measure_mono(source)
    assert result.dc_offset == pytest.approx(0.25)
    assert result.has_dc_offset
    np.testing.assert_array_equal(source, np.full(64, 0.25))


def test_known_level_measurements() -> None:
    source = np.array([-1.0, 1.0, -1.0, 1.0])
    result = measure_mono(source)
    assert result.minimum == -1.0
    assert result.maximum == 1.0
    assert result.peak_absolute == 1.0
    assert result.rms == 1.0
    assert result.mean == 0.0


def test_empty_audio_cannot_be_measured() -> None:
    with pytest.raises(ValueError, match="empty"):
        measure_mono(np.array([], dtype=np.float64))


def test_non_finite_audio_cannot_be_measured() -> None:
    with pytest.raises(ValueError, match="NaN or infinity"):
        measure_mono(np.array([0.0, np.nan]))
