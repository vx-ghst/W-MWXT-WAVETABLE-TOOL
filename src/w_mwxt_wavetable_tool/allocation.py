from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    USER_WAVE_CAPACITY,
    USER_WAVE_FIRST,
    USER_WAVE_LAST,
    USER_WAVES_PER_COMPLETE_TABLE,
)
from .errors import AllocationError


@dataclass(frozen=True, slots=True)
class UserWaveAllocation:
    """A consecutive allocation inside the 250 Microwave XT User Waves."""

    start_number: int
    count: int

    def __post_init__(self) -> None:
        if not USER_WAVE_FIRST <= self.start_number <= USER_WAVE_LAST:
            raise AllocationError(
                f"User Wave start number out of range: {self.start_number}"
            )
        if not 1 <= self.count <= USER_WAVE_CAPACITY:
            raise AllocationError(
                f"User Wave count out of range: {self.count}; expected 1..{USER_WAVE_CAPACITY}"
            )
        if self.end_number > USER_WAVE_LAST:
            raise AllocationError(
                f"User Wave allocation {self.start_number}..{self.end_number} "
                f"exceeds {USER_WAVE_LAST}"
            )

    @property
    def end_number(self) -> int:
        return self.start_number + self.count - 1

    @property
    def numbers(self) -> tuple[int, ...]:
        return tuple(range(self.start_number, self.end_number + 1))

    @property
    def display_range(self) -> str:
        return f"{self.start_number}–{self.end_number}"

    @classmethod
    def complete_table(cls, start_number: int) -> "UserWaveAllocation":
        return cls(start_number, USER_WAVES_PER_COMPLETE_TABLE)


def allocate_user_waves(start_number: int, count: int) -> UserWaveAllocation:
    return UserWaveAllocation(start_number, count)
