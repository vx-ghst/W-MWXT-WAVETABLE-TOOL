import math
import pytest

from v8b_helpers import candidate
from v8e_transition_helpers import ALL_INTERPOLATION_METHODS

from w_mwxt_wavetable_tool import InterpolationPolicy, interpolate_xt_wave


def _opposed_pair():
    left = tuple(
        round(
            110 * math.sin(2 * math.pi * index / 128)
            + 12 * math.sin(6 * math.pi * index / 128)
        )
        for index in range(64)
    )
    right = tuple(
        round(
            -42 * math.sin(2 * math.pi * index / 128 + 0.7)
            + 80 * math.sin(4 * math.pi * index / 128)
        )
        for index in range(64)
    )
    return (
        candidate("left", left, source_index=0),
        candidate("right", right, source_index=1),
    )


@pytest.mark.parametrize("method", ALL_INTERPOLATION_METHODS)
def test_all_methods_protect_level_fundamental_and_xt_range(method):
    left, right = _opposed_pair()
    policy = InterpolationPolicy()
    wave = interpolate_xt_wave(left, right, 0.5, method, policy)
    assert wave.level_error <= policy.level_tolerance
    assert wave.fundamental_error <= policy.fundamental_tolerance
    assert min(wave.stored_samples) >= -127
    assert max(wave.stored_samples) <= 127
    assert -128 not in wave.stored_samples
