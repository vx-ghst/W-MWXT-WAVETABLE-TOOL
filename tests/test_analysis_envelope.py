from __future__ import annotations

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import analyze_envelope
from w_mwxt_wavetable_tool.analysis.framing import frame_starts
from w_mwxt_wavetable_tool.errors import AnalysisError


def test_frame_grid_covers_the_end_without_padding() -> None:
    starts = frame_starts(10, frame_size=4, hop_size=3)
    assert starts == (0, 3, 6)
    end_aligned = frame_starts(11, frame_size=4, hop_size=4)
    assert end_aligned == (0, 4, 7)


def test_short_signal_uses_one_partial_frame() -> None:
    result = analyze_envelope(np.ones(5), 1000, frame_size=16, hop_size=4)
    assert result.frame_count == 1
    assert result.frame_starts == (0,)
    assert result.frame_center_seconds == pytest.approx((0.002,))
    assert result.frame_rms == pytest.approx((1.0,))


def test_constant_amplitude_is_fully_stable() -> None:
    result = analyze_envelope(
        np.full(4096, 0.25), 48000, frame_size=512, hop_size=256
    )
    assert result.standard_deviation_rms == pytest.approx(0.0, abs=1e-15)
    assert result.coefficient_of_variation == pytest.approx(0.0)
    assert result.amplitude_stability == pytest.approx(1.0)
    assert result.envelope_dynamic_range_db == pytest.approx(0.0)


def test_two_level_envelope_reports_dynamic_range_and_lower_stability() -> None:
    samples = np.concatenate([np.full(2048, 0.5), np.full(2048, 0.25)])
    result = analyze_envelope(samples, 48000, frame_size=512, hop_size=512)
    assert result.frame_count == 8
    assert result.minimum_frame_rms == pytest.approx(0.25)
    assert result.maximum_frame_rms == pytest.approx(0.5)
    assert result.envelope_dynamic_range_db == pytest.approx(6.020599913279624)
    assert 0.0 < result.amplitude_stability < 1.0


def test_silence_is_stable_but_has_no_log_dynamic_range() -> None:
    result = analyze_envelope(np.zeros(1024), 44100, frame_size=256, hop_size=128)
    assert result.active_frame_count == 0
    assert result.active_frame_ratio == 0.0
    assert result.coefficient_of_variation is None
    assert result.amplitude_stability == 1.0
    assert result.envelope_dynamic_range_db is None


def test_envelope_is_deterministic() -> None:
    samples = np.linspace(-0.75, 0.75, 4097, dtype=np.float64)
    first = analyze_envelope(samples, 44100, frame_size=257, hop_size=113)
    second = analyze_envelope(samples, 44100, frame_size=257, hop_size=113)
    assert first == second
    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize(
    "sample_rate,frame_size,hop_size,active_threshold",
    [
        (0, 128, 64, 1e-8),
        (44100, 0, 64, 1e-8),
        (44100, 128, 0, 1e-8),
        (44100, 128, 64, -1.0),
    ],
)
def test_invalid_envelope_configuration_is_rejected(
    sample_rate: int, frame_size: int, hop_size: int, active_threshold: float
) -> None:
    with pytest.raises(AnalysisError):
        analyze_envelope(
            np.zeros(32),
            sample_rate,
            frame_size=frame_size,
            hop_size=hop_size,
            active_threshold=active_threshold,
        )
