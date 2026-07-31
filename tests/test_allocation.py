from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.allocation import UserWaveAllocation, allocate_user_waves
from w_mwxt_wavetable_tool.errors import AllocationError


def test_single_wave_allocation() -> None:
    allocation = allocate_user_waves(1000, 1)
    assert allocation.end_number == 1000
    assert allocation.numbers == (1000,)


def test_complete_table_from_first_destination() -> None:
    allocation = UserWaveAllocation.complete_table(1000)
    assert allocation.count == 61
    assert allocation.end_number == 1060
    assert allocation.numbers == tuple(range(1000, 1061))


def test_complete_table_from_last_valid_start() -> None:
    allocation = UserWaveAllocation.complete_table(1189)
    assert allocation.end_number == 1249
    assert allocation.display_range == "1189–1249"


def test_complete_table_after_last_valid_start_is_rejected() -> None:
    with pytest.raises(AllocationError, match="exceeds 1249"):
        UserWaveAllocation.complete_table(1190)


@pytest.mark.parametrize(
    ("start", "count"),
    [(999, 1), (1250, 1), (1000, 0), (1000, 251), (1249, 2)],
)
def test_invalid_allocations_are_rejected(start: int, count: int) -> None:
    with pytest.raises(AllocationError):
        UserWaveAllocation(start, count)
