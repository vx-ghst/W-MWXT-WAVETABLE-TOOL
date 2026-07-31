from __future__ import annotations

import numpy as np
import pytest

from w_mwxt_wavetable_tool.audio import InvalidSamplePolicy, normalize_float_samples
from w_mwxt_wavetable_tool.errors import InvalidAudioDataError


def test_one_dimensional_input_becomes_one_channel() -> None:
    result = normalize_float_samples([0.0, 0.5, -0.5])
    assert result.shape == (3, 1)
    assert result.dtype == np.float64


def test_two_dimensional_input_is_preserved() -> None:
    result = normalize_float_samples([[0.0, 1.0], [0.5, -0.5]])
    assert result.shape == (2, 2)
    assert result.flags.c_contiguous


@pytest.mark.parametrize("shape", [(1, 1, 1), (0,), (2, 0)])
def test_invalid_shapes_are_rejected(shape: tuple[int, ...]) -> None:
    with pytest.raises(InvalidAudioDataError):
        normalize_float_samples(np.zeros(shape))


def test_non_finite_samples_are_rejected_by_default() -> None:
    with pytest.raises(InvalidAudioDataError, match="NaN or infinite"):
        normalize_float_samples([0.0, np.nan, np.inf])


def test_non_finite_samples_can_be_zeroed_explicitly() -> None:
    result = normalize_float_samples(
        [0.0, np.nan, np.inf, -np.inf],
        policy=InvalidSamplePolicy.ZERO,
    )
    np.testing.assert_array_equal(result[:, 0], np.zeros(4))


def test_unknown_invalid_sample_policy_is_rejected() -> None:
    with pytest.raises(InvalidAudioDataError, match="Unknown invalid-sample policy"):
        normalize_float_samples([0.0], policy="guess")
