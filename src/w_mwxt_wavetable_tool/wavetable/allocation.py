from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from ..constants import USER_WAVE_FIRST, USER_WAVE_LAST
from ..destinations import UserWavetableDestination
from ..errors import AllocationError
from ..inventory import InventoryState, XtMemoryInventory
from .consolidation import PhysicalWaveSet
from .models import WavetableContractError

WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION = 1


def _canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _strings(values: Sequence[str], *, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence")
    result = tuple(values)
    if any(not isinstance(item, str) or not item for item in result):
        raise WavetableContractError(f"{name} must contain non-empty strings")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


class AllocationProposalStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SafeAllocationPolicy:
    schema_version: int = WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION
    allow_non_contiguous: bool = False
    authorized_overwrite_numbers: tuple[int, ...] = ()
    prefer_lowest_number: bool = True
    reason: str = "Prefer the lowest contiguous SAFE_FREE block; explicit overwrite authorization is required otherwise."

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported safe-allocation policy schema version")
        if not isinstance(self.allow_non_contiguous, bool):
            raise WavetableContractError("allow_non_contiguous must be boolean")
        if not isinstance(self.prefer_lowest_number, bool):
            raise WavetableContractError("prefer_lowest_number must be boolean")
        values = tuple(self.authorized_overwrite_numbers)
        object.__setattr__(self, "authorized_overwrite_numbers", values)
        if tuple(sorted(set(values))) != values:
            raise WavetableContractError("authorized_overwrite_numbers must be sorted and unique")
        if any(not USER_WAVE_FIRST <= item <= USER_WAVE_LAST for item in values):
            raise WavetableContractError("authorized overwrite User Wave number out of range")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "allow_non_contiguous": self.allow_non_contiguous,
            "authorized_overwrite_numbers": list(self.authorized_overwrite_numbers),
            "prefer_lowest_number": self.prefer_lowest_number,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_SAFE_ALLOCATION_POLICY = SafeAllocationPolicy()


@dataclass(frozen=True, slots=True)
class UserWaveDestinationAssignment:
    schema_version: int
    physical_index: int
    wave_id: str
    physical_wave_sha256: str
    user_wave_number: int
    previous_state: InventoryState
    overwrite_required: bool
    previous_payload_sha256: str | None
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported destination assignment schema version")
        if isinstance(self.physical_index, bool) or not isinstance(self.physical_index, int) or self.physical_index < 0:
            raise WavetableContractError("physical_index must be a non-negative integer")
        if not isinstance(self.wave_id, str) or not self.wave_id:
            raise WavetableContractError("wave_id must not be empty")
        _sha256(self.physical_wave_sha256, name="physical_wave_sha256")
        if not USER_WAVE_FIRST <= self.user_wave_number <= USER_WAVE_LAST:
            raise WavetableContractError("User Wave destination out of range")
        if not isinstance(self.previous_state, InventoryState):
            raise WavetableContractError("previous_state must be InventoryState")
        if not isinstance(self.overwrite_required, bool):
            raise WavetableContractError("overwrite_required must be boolean")
        if self.previous_payload_sha256 is not None:
            _sha256(self.previous_payload_sha256, name="previous_payload_sha256")
        if self.previous_state is InventoryState.UNKNOWN:
            raise WavetableContractError("UNKNOWN inventory entries can never be assigned")
        if self.overwrite_required != (self.previous_state is not InventoryState.SAFE_FREE):
            raise WavetableContractError("overwrite_required disagrees with previous inventory state")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "physical_index": self.physical_index,
            "wave_id": self.wave_id,
            "physical_wave_sha256": self.physical_wave_sha256,
            "user_wave_number": self.user_wave_number,
            "previous_state": self.previous_state.value,
            "overwrite_required": self.overwrite_required,
            "previous_payload_sha256": self.previous_payload_sha256,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AllocationProposal:
    schema_version: int
    status: AllocationProposalStatus
    physical_wave_set_sha256: str
    inventory_sha256: str
    policy_sha256: str
    user_wavetable_destination: UserWavetableDestination
    assignments: tuple[UserWaveDestinationAssignment, ...]
    contiguous: bool
    overwrite_wave_numbers: tuple[int, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported allocation proposal schema version")
        for name in ("physical_wave_set_sha256", "inventory_sha256", "policy_sha256"):
            _sha256(getattr(self, name), name=name)
        if not isinstance(self.user_wavetable_destination, UserWavetableDestination):
            raise WavetableContractError("user_wavetable_destination must be selected manually")
        assignments = tuple(self.assignments)
        object.__setattr__(self, "assignments", assignments)
        if any(not isinstance(item, UserWaveDestinationAssignment) for item in assignments):
            raise WavetableContractError("assignments must contain UserWaveDestinationAssignment values")
        if not isinstance(self.contiguous, bool):
            raise WavetableContractError("contiguous must be boolean")
        overwrites = tuple(self.overwrite_wave_numbers)
        object.__setattr__(self, "overwrite_wave_numbers", overwrites)
        if tuple(sorted(set(overwrites))) != overwrites:
            raise WavetableContractError("overwrite_wave_numbers must be sorted and unique")
        expected_overwrites = tuple(sorted(item.user_wave_number for item in assignments if item.overwrite_required))
        if overwrites != expected_overwrites:
            raise WavetableContractError("overwrite_wave_numbers disagree with assignments")
        object.__setattr__(self, "blockers", _strings(self.blockers, name="blockers"))
        object.__setattr__(self, "warnings", _strings(self.warnings, name="warnings"))
        if self.status is AllocationProposalStatus.READY:
            if self.blockers or not assignments:
                raise WavetableContractError("ready allocation requires assignments and no blockers")
            if tuple(item.physical_index for item in assignments) != tuple(range(len(assignments))):
                raise WavetableContractError("assignments must follow canonical physical-wave order")
            numbers = tuple(item.user_wave_number for item in assignments)
            if len(set(numbers)) != len(numbers):
                raise WavetableContractError("allocation destinations must be unique")
            if any(item.previous_state is InventoryState.UNKNOWN for item in assignments):
                raise WavetableContractError("UNKNOWN entries cannot appear in a ready proposal")
            expected_contiguous = numbers == tuple(range(numbers[0], numbers[0] + len(numbers)))
            if self.contiguous != expected_contiguous:
                raise WavetableContractError("contiguous flag disagrees with destination numbers")
        else:
            if not self.blockers or assignments or overwrites or self.contiguous:
                raise WavetableContractError("blocked allocation must expose blockers without assignments")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def selected_user_wave_numbers(self) -> tuple[int, ...]:
        return tuple(item.user_wave_number for item in self.assignments)

    @property
    def collision_free(self) -> bool:
        return len(set(self.selected_user_wave_numbers)) == len(self.selected_user_wave_numbers)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "physical_wave_set_sha256": self.physical_wave_set_sha256,
            "inventory_sha256": self.inventory_sha256,
            "policy_sha256": self.policy_sha256,
            "user_wavetable_destination": {
                "display_number": self.user_wavetable_destination.display_number,
                "internal_number": self.user_wavetable_destination.internal_number,
                "selected_manually": True,
            },
            "assignments": [item.to_dict() for item in self.assignments],
            "selected_user_wave_numbers": list(self.selected_user_wave_numbers),
            "contiguous": self.contiguous,
            "collision_free": self.collision_free,
            "overwrite_wave_numbers": list(self.overwrite_wave_numbers),
            "overwrite_wavetable_display_number": self.user_wavetable_destination.display_number,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "boundaries": {
                "wctd_materialized": False,
                "sysex_generated": False,
                "midi_opened": False,
                "midi_transmitted": False,
                "memory_written": False,
            },
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _eligible_numbers(inventory: XtMemoryInventory, policy: SafeAllocationPolicy) -> tuple[int, ...]:
    authorized = set(policy.authorized_overwrite_numbers)
    values: list[int] = []
    for entry in inventory.user_waves:
        if entry.state is InventoryState.SAFE_FREE:
            values.append(entry.number)
        elif entry.number in authorized and entry.state in {InventoryState.USED, InventoryState.ORPHANED}:
            values.append(entry.number)
    return tuple(values)


def _contiguous_blocks(numbers: Sequence[int], count: int) -> tuple[tuple[int, ...], ...]:
    available = set(numbers)
    blocks: list[tuple[int, ...]] = []
    for start in numbers:
        block = tuple(range(start, start + count))
        if block[-1] <= USER_WAVE_LAST and all(item in available for item in block):
            blocks.append(block)
    return tuple(blocks)


def plan_safe_user_wave_allocation(
    physical_wave_set: PhysicalWaveSet,
    inventory: XtMemoryInventory,
    user_wavetable_destination: UserWavetableDestination,
    policy: SafeAllocationPolicy = DEFAULT_SAFE_ALLOCATION_POLICY,
) -> AllocationProposal:
    """Propose N deterministic User Wave destinations without writing memory.

    ``SAFE_FREE`` entries are eligible automatically only when inventory proof
    enabled that state. ``USED`` and ``ORPHANED`` require their exact numbers in
    ``authorized_overwrite_numbers``. ``UNKNOWN`` is never eligible.
    """

    if not isinstance(physical_wave_set, PhysicalWaveSet):
        raise AllocationError("physical_wave_set must be PhysicalWaveSet")
    if not isinstance(inventory, XtMemoryInventory):
        raise AllocationError("inventory must be XtMemoryInventory")
    if not isinstance(user_wavetable_destination, UserWavetableDestination):
        raise AllocationError("User Wavetable destination must be selected manually")
    if not isinstance(policy, SafeAllocationPolicy):
        raise AllocationError("policy must be SafeAllocationPolicy")

    count = physical_wave_set.physical_wave_count
    eligible = _eligible_numbers(inventory, policy)
    blocks = _contiguous_blocks(eligible, count)
    warnings: list[str] = []

    selected: tuple[int, ...] | None = None
    if blocks:
        def block_key(block: tuple[int, ...]) -> tuple[int, int]:
            overwrite_count = sum(inventory.wave_entry(number).state is not InventoryState.SAFE_FREE for number in block)
            start_key = block[0] if policy.prefer_lowest_number else -block[0]
            return overwrite_count, start_key
        selected = min(blocks, key=block_key)
    elif policy.allow_non_contiguous and len(eligible) >= count:
        ordered = sorted(
            eligible,
            key=lambda number: (
                inventory.wave_entry(number).state is not InventoryState.SAFE_FREE,
                number if policy.prefer_lowest_number else -number,
            ),
        )
        selected = tuple(ordered[:count])
        warnings.append("No eligible contiguous block exists; explicit policy allowed a non-contiguous proposal.")

    if selected is None:
        blockers = [
            f"Only {len(eligible)} eligible User Wave destinations are available for {count} physical waves."
        ]
        if not inventory.evidence_status.safe_free_enabled:
            blockers.append("SAFE_FREE is disabled because complete coverage and a validated empty signature are not both proven.")
        if not policy.allow_non_contiguous:
            blockers.append("No contiguous eligible block exists and non-contiguous allocation is disabled.")
        return AllocationProposal(
            schema_version=WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION,
            status=AllocationProposalStatus.BLOCKED,
            physical_wave_set_sha256=physical_wave_set.analysis_sha256,
            inventory_sha256=inventory.analysis_sha256,
            policy_sha256=policy.analysis_sha256,
            user_wavetable_destination=user_wavetable_destination,
            assignments=(),
            contiguous=False,
            overwrite_wave_numbers=(),
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(warnings),
            reason="Allocation is blocked rather than silently selecting UNKNOWN or unauthorized destinations.",
        )

    assignments: list[UserWaveDestinationAssignment] = []
    for wave, number in zip(physical_wave_set.waves, selected):
        entry = inventory.wave_entry(number)
        if entry.state is InventoryState.UNKNOWN:
            raise AllocationError("Internal safety error: UNKNOWN destination selected")
        overwrite = entry.state is not InventoryState.SAFE_FREE
        assignments.append(
            UserWaveDestinationAssignment(
                schema_version=WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION,
                physical_index=wave.physical_index,
                wave_id=wave.wave_id,
                physical_wave_sha256=wave.analysis_sha256,
                user_wave_number=number,
                previous_state=entry.state,
                overwrite_required=overwrite,
                previous_payload_sha256=entry.stored_samples_sha256,
                reason=(
                    "Destination is proven SAFE_FREE by complete inventory and validated empty signature."
                    if not overwrite
                    else "Destination overwrite was explicitly authorized by exact User Wave number."
                ),
            )
        )

    numbers = tuple(item.user_wave_number for item in assignments)
    contiguous = numbers == tuple(range(numbers[0], numbers[0] + len(numbers)))
    overwrites = tuple(sorted(item.user_wave_number for item in assignments if item.overwrite_required))
    if overwrites:
        warnings.append("The proposal contains explicit User Wave overwrites and must be confirmed before V8-K materialization.")

    return AllocationProposal(
        schema_version=WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION,
        status=AllocationProposalStatus.READY,
        physical_wave_set_sha256=physical_wave_set.analysis_sha256,
        inventory_sha256=inventory.analysis_sha256,
        policy_sha256=policy.analysis_sha256,
        user_wavetable_destination=user_wavetable_destination,
        assignments=tuple(assignments),
        contiguous=contiguous,
        overwrite_wave_numbers=overwrites,
        blockers=(),
        warnings=tuple(warnings),
        reason="Deterministic collision-free allocation proposal produced without WCTD, SysEx, MIDI or memory writes.",
    )


__all__ = [
    "WAVETABLE_SAFE_ALLOCATION_SCHEMA_VERSION",
    "AllocationProposalStatus",
    "SafeAllocationPolicy",
    "DEFAULT_SAFE_ALLOCATION_POLICY",
    "UserWaveDestinationAssignment",
    "AllocationProposal",
    "plan_safe_user_wave_allocation",
]
