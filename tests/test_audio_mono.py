from __future__ import annotations

import numpy as np
import pytest

from w_mwxt_wavetable_tool.audio import (
    MonoPolicy,
    MonoStrategy,
    convert_to_mono,
    stereo_correlation,
)
from w_mwxt_wavetable_tool.errors import InvalidAudioDataError


def test_mono_source_is_passed_through() -> None:
    source = np.array([[0.0], [0.5], [-0.5]], dtype=np.float64)
    mono, report = convert_to_mono(source)
    np.testing.assert_array_equal(mono, source[:, 0])
    assert report.strategy is MonoStrategy.MONO_PASSTHROUGH
    assert report.selected_channel == 0


def test_identical_stereo_is_averaged_without_change() -> None:
    wave = np.linspace(-1.0, 1.0, 32)
    source = np.column_stack((wave, wave))
    mono, report = convert_to_mono(source)
    np.testing.assert_allclose(mono, wave, atol=0.0, rtol=0.0)
    assert report.strategy is MonoStrategy.IDENTICAL_CHANNELS
    assert report.stereo_correlation == pytest.approx(1.0)


def test_silent_channel_is_removed() -> None:
    wave = np.sin(np.linspace(0.0, 4.0 * np.pi, 128, endpoint=False))
    source = np.column_stack((np.zeros_like(wave), wave))
    mono, report = convert_to_mono(source)
    np.testing.assert_allclose(mono, wave)
    assert report.strategy is MonoStrategy.SILENT_CHANNEL_REMOVED
    assert report.selected_channel == 1


def test_antiphase_stereo_selects_one_channel_instead_of_cancelling() -> None:
    wave = np.sin(np.linspace(0.0, 4.0 * np.pi, 128, endpoint=False))
    source = np.column_stack((wave, -wave))
    mono, report = convert_to_mono(source)
    np.testing.assert_allclose(mono, wave)
    assert report.strategy is MonoStrategy.ANTIPHASE_CHANNEL_SELECTED
    assert report.selected_channel == 0
    assert report.stereo_correlation == pytest.approx(-1.0)


def test_explicit_average_can_cancel_antiphase_stereo() -> None:
    wave = np.linspace(-1.0, 1.0, 32)
    source = np.column_stack((wave, -wave))
    mono, report = convert_to_mono(source, policy=MonoPolicy.AVERAGE)
    np.testing.assert_allclose(mono, 0.0, atol=1e-15)
    assert report.strategy is MonoStrategy.AVERAGE


def test_explicit_first_channel() -> None:
    source = np.array([[0.1, 0.8], [0.2, 0.7]])
    mono, report = convert_to_mono(source, policy=MonoPolicy.FIRST_CHANNEL)
    np.testing.assert_array_equal(mono, source[:, 0])
    assert report.strategy is MonoStrategy.FIRST_CHANNEL


def test_explicit_dominant_channel() -> None:
    source = np.array([[0.1, 0.8], [0.2, 0.7]])
    mono, report = convert_to_mono(source, policy=MonoPolicy.DOMINANT_CHANNEL)
    np.testing.assert_array_equal(mono, source[:, 1])
    assert report.strategy is MonoStrategy.DOMINANT_CHANNEL
    assert report.selected_channel == 1


def test_general_stereo_is_averaged() -> None:
    source = np.array([[0.0, 1.0], [0.25, 0.75], [-0.5, 0.5]])
    mono, report = convert_to_mono(source)
    np.testing.assert_allclose(mono, np.mean(source, axis=1))
    assert report.strategy is MonoStrategy.AVERAGE


def test_stereo_correlation_returns_none_for_constant_channels() -> None:
    source = np.ones((32, 2), dtype=np.float64)
    assert stereo_correlation(source) is None


def test_invalid_mono_input_is_rejected() -> None:
    with pytest.raises(InvalidAudioDataError):
        convert_to_mono(np.zeros((0, 2)))


def test_unknown_mono_policy_is_rejected() -> None:
    with pytest.raises(InvalidAudioDataError, match="Unknown mono policy"):
        convert_to_mono(np.zeros((4, 2)), policy="magic")
