from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .allocation import UserWaveAllocation
from .destinations import SoundDestination, UserWavetableDestination
from .errors import SafetyError


class MemoryTargetKind(str, Enum):
    USER_WAVE = "user_wave"
    USER_WAVETABLE = "user_wavetable"
    SOUND = "sound"
    EDIT_BUFFER = "edit_buffer"


@dataclass(frozen=True, slots=True)
class MemoryTarget:
    kind: MemoryTargetKind
    identifier: int | str

    @property
    def label(self) -> str:
        if self.kind is MemoryTargetKind.USER_WAVE:
            return f"User Wave {self.identifier}"
        if self.kind is MemoryTargetKind.USER_WAVETABLE:
            return f"User Wavetable {int(self.identifier):03d}"
        if self.kind is MemoryTargetKind.SOUND:
            return f"Sound {self.identifier}"
        return "Sound Edit Buffer"


@dataclass(frozen=True, slots=True)
class OverwritePlan:
    user_waves: UserWaveAllocation
    user_wavetable: UserWavetableDestination
    sound: SoundDestination

    @property
    def targets(self) -> tuple[MemoryTarget, ...]:
        wave_targets = tuple(
            MemoryTarget(MemoryTargetKind.USER_WAVE, number)
            for number in self.user_waves.numbers
        )
        table_target = MemoryTarget(
            MemoryTargetKind.USER_WAVETABLE,
            self.user_wavetable.display_number,
        )
        if self.sound.is_edit_buffer:
            sound_target = MemoryTarget(MemoryTargetKind.EDIT_BUFFER, "EDIT_BUFFER")
        else:
            sound_target = MemoryTarget(
                MemoryTargetKind.SOUND,
                self.sound.display_location,
            )
        return wave_targets + (table_target, sound_target)

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(target.label for target in self.targets)


@dataclass(frozen=True, slots=True)
class CollisionReport:
    duplicate_targets: tuple[MemoryTarget, ...]
    reserved_collisions: tuple[MemoryTarget, ...]

    @property
    def has_collisions(self) -> bool:
        return bool(self.duplicate_targets or self.reserved_collisions)

    @property
    def labels(self) -> tuple[str, ...]:
        ordered = self.duplicate_targets + self.reserved_collisions
        return tuple(target.label for target in _unique_in_order(ordered))

    def assert_safe(self) -> None:
        if not self.has_collisions:
            return
        raise SafetyError("Destination collision(s): " + ", ".join(self.labels))


def analyze_collisions(
    requested: Iterable[MemoryTarget],
    *,
    reserved: Iterable[MemoryTarget] = (),
) -> CollisionReport:
    requested_targets = tuple(requested)
    counts = Counter(requested_targets)
    duplicates = tuple(
        target
        for target in _unique_in_order(requested_targets)
        if counts[target] > 1
    )
    reserved_set = set(reserved)
    reserved_collisions = tuple(
        target
        for target in _unique_in_order(requested_targets)
        if target in reserved_set
    )
    return CollisionReport(duplicates, reserved_collisions)


def _unique_in_order(targets: Iterable[MemoryTarget]) -> tuple[MemoryTarget, ...]:
    seen: set[MemoryTarget] = set()
    unique: list[MemoryTarget] = []
    for target in targets:
        if target not in seen:
            seen.add(target)
            unique.append(target)
    return tuple(unique)
