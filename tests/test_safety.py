from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.allocation import UserWaveAllocation
from w_mwxt_wavetable_tool.destinations import SoundDestination, UserWavetableDestination
from w_mwxt_wavetable_tool.errors import SafetyError
from w_mwxt_wavetable_tool.safety import (
    MemoryTarget,
    MemoryTargetKind,
    OverwritePlan,
    analyze_collisions,
)


def test_overwrite_plan_lists_every_destination_in_stable_order() -> None:
    plan = OverwritePlan(
        user_waves=UserWaveAllocation.complete_table(1000),
        user_wavetable=UserWavetableDestination(97),
        sound=SoundDestination.parse("A001"),
    )
    assert len(plan.targets) == 63
    assert plan.labels[0] == "User Wave 1000"
    assert plan.labels[60] == "User Wave 1060"
    assert plan.labels[61] == "User Wavetable 097"
    assert plan.labels[62] == "Sound A001"
    assert plan.labels == tuple(plan.labels)


def test_edit_buffer_is_listed_explicitly() -> None:
    plan = OverwritePlan(
        user_waves=UserWaveAllocation(1249, 1),
        user_wavetable=UserWavetableDestination(128),
        sound=SoundDestination.edit_buffer(),
    )
    assert plan.labels == (
        "User Wave 1249",
        "User Wavetable 128",
        "Sound Edit Buffer",
    )


def test_collision_report_detects_duplicates_and_reserved_targets() -> None:
    wave = MemoryTarget(MemoryTargetKind.USER_WAVE, 1000)
    table = MemoryTarget(MemoryTargetKind.USER_WAVETABLE, 97)
    report = analyze_collisions(
        [wave, wave, table],
        reserved=[table],
    )
    assert report.has_collisions
    assert report.duplicate_targets == (wave,)
    assert report.reserved_collisions == (table,)
    assert report.labels == ("User Wave 1000", "User Wavetable 097")
    with pytest.raises(SafetyError, match="User Wave 1000"):
        report.assert_safe()


def test_collision_report_accepts_a_unique_unreserved_plan() -> None:
    plan = OverwritePlan(
        user_waves=UserWaveAllocation(1000, 2),
        user_wavetable=UserWavetableDestination(97),
        sound=SoundDestination.parse("B128"),
    )
    report = analyze_collisions(plan.targets)
    assert not report.has_collisions
    report.assert_safe()
