from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from ..constants import INTERPOLATED_WAVE_REFERENCE
from ..destinations import UserWavetableDestination
from ..models import UserWavetable
from .allocation import AllocationProposal, AllocationProposalStatus
from .code_v8i import CodeV8IVariant
from .models import FixedTailContract, USER_POSITION_COUNT, WCTD_POSITION_COUNT, WavetableContractError

WCTD_MATERIALIZATION_V8K_SCHEMA_VERSION = 1


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


class WctdMode(str, Enum):
    DENSE = "dense"
    SPARSE = "sparse"


@dataclass(frozen=True, slots=True)
class WctdMaterializationPolicy:
    schema_version: int = WCTD_MATERIALIZATION_V8K_SCHEMA_VERSION
    default_mode: WctdMode = WctdMode.DENSE
    build_sparse_candidate: bool = True
    reason: str = (
        "Dense WCTD is the V8 default; sparse remains a candidate until a real hardware campaign passes."
    )

    def __post_init__(self) -> None:
        if self.schema_version != WCTD_MATERIALIZATION_V8K_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-K WCTD policy schema version")
        if not isinstance(self.default_mode, WctdMode):
            raise WavetableContractError("default_mode must be WctdMode")
        if not isinstance(self.build_sparse_candidate, bool):
            raise WavetableContractError("build_sparse_candidate must be boolean")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "default_mode": self.default_mode.value,
            "build_sparse_candidate": self.build_sparse_candidate,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_WCTD_MATERIALIZATION_POLICY = WctdMaterializationPolicy()


@dataclass(frozen=True, slots=True)
class MaterializedWctd:
    schema_version: int
    mode: WctdMode
    v8i_variant_sha256: str
    allocation_sha256: str
    fixed_tail_sha256: str
    user_wavetable_destination: UserWavetableDestination
    references: tuple[int, ...]
    explicit_user_positions: tuple[int, ...]
    interpolated_user_positions: tuple[int, ...]
    allocated_user_wave_numbers: tuple[int, ...]
    sparse_hardware_enabled: bool
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WCTD_MATERIALIZATION_V8K_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-K WCTD materialization schema version")
        if not isinstance(self.mode, WctdMode):
            raise WavetableContractError("mode must be WctdMode")
        for name in ("v8i_variant_sha256", "allocation_sha256", "fixed_tail_sha256"):
            _sha256(getattr(self, name), name=name)
        if not isinstance(self.user_wavetable_destination, UserWavetableDestination):
            raise WavetableContractError("user_wavetable_destination must be UserWavetableDestination")
        references = tuple(self.references)
        object.__setattr__(self, "references", references)
        if len(references) != WCTD_POSITION_COUNT:
            raise WavetableContractError("WCTD materialization requires exactly 64 references")
        if any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 0xFFFF for item in references):
            raise WavetableContractError("WCTD references must be unsigned 16-bit integers")
        explicit = tuple(self.explicit_user_positions)
        interpolated = tuple(self.interpolated_user_positions)
        object.__setattr__(self, "explicit_user_positions", explicit)
        object.__setattr__(self, "interpolated_user_positions", interpolated)
        if tuple(sorted(set(explicit))) != explicit or tuple(sorted(set(interpolated))) != interpolated:
            raise WavetableContractError("WCTD position sets must be sorted and unique")
        if any(not 0 <= item < USER_POSITION_COUNT for item in explicit + interpolated):
            raise WavetableContractError("WCTD user positions must be in 0..60")
        if sorted(explicit + interpolated) != list(range(USER_POSITION_COUNT)):
            raise WavetableContractError("explicit and interpolated positions must partition 0..60")
        expected_explicit = tuple(index for index, ref in enumerate(references[:USER_POSITION_COUNT]) if ref != INTERPOLATED_WAVE_REFERENCE)
        expected_interpolated = tuple(index for index, ref in enumerate(references[:USER_POSITION_COUNT]) if ref == INTERPOLATED_WAVE_REFERENCE)
        if explicit != expected_explicit or interpolated != expected_interpolated:
            raise WavetableContractError("WCTD position metadata disagrees with references")
        allocated = tuple(self.allocated_user_wave_numbers)
        object.__setattr__(self, "allocated_user_wave_numbers", allocated)
        if tuple(sorted(set(allocated))) != tuple(sorted(allocated)) or not allocated:
            raise WavetableContractError("allocated_user_wave_numbers must be unique and non-empty")
        explicit_refs = tuple(ref for ref in references[:USER_POSITION_COUNT] if ref != INTERPOLATED_WAVE_REFERENCE)
        if any(ref not in set(allocated) for ref in explicit_refs):
            raise WavetableContractError("WCTD references an unallocated User Wave")
        if set(explicit_refs) != set(allocated):
            raise WavetableContractError("Every allocated physical User Wave must be referenced")
        if any(ref == INTERPOLATED_WAVE_REFERENCE for ref in references[USER_POSITION_COUNT:]):
            raise WavetableContractError("Fixed-tail references must always be explicit")
        if not isinstance(self.sparse_hardware_enabled, bool):
            raise WavetableContractError("sparse_hardware_enabled must be boolean")
        if self.mode is WctdMode.DENSE:
            if interpolated or explicit != tuple(range(USER_POSITION_COUNT)):
                raise WavetableContractError("Dense WCTD requires 61 explicit user positions")
            if self.sparse_hardware_enabled:
                raise WavetableContractError("Dense WCTD cannot claim sparse hardware enablement")
        else:
            if 0 not in explicit or USER_POSITION_COUNT - 1 not in explicit:
                raise WavetableContractError("Sparse WCTD requires explicit first and last user positions")
        object.__setattr__(self, "warnings", _strings(self.warnings, name="warnings"))
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def logical_reference_payload(self) -> bytes:
        return b"".join(reference.to_bytes(2, "big") for reference in self.references)

    @property
    def logical_reference_payload_sha256(self) -> str:
        return sha256(self.logical_reference_payload).hexdigest()

    def to_user_wavetable(self, device_id: int) -> UserWavetable:
        return UserWavetable.from_display_number(
            device_id,
            self.user_wavetable_destination.display_number,
            self.references,
        )

    def wire_payload(self, device_id: int = 0) -> bytes:
        return self.to_user_wavetable(device_id).to_message().payload

    def sysex_message(self, device_id: int = 0) -> bytes:
        return self.to_user_wavetable(device_id).to_message().to_bytes()

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode.value,
            "v8i_variant_sha256": self.v8i_variant_sha256,
            "allocation_sha256": self.allocation_sha256,
            "fixed_tail_sha256": self.fixed_tail_sha256,
            "user_wavetable_destination": {
                "display_number": self.user_wavetable_destination.display_number,
                "internal_number": self.user_wavetable_destination.internal_number,
                "selected_manually": True,
            },
            "references": list(self.references),
            "explicit_user_positions": list(self.explicit_user_positions),
            "interpolated_user_positions": list(self.interpolated_user_positions),
            "allocated_user_wave_numbers": list(self.allocated_user_wave_numbers),
            "logical_reference_bytes": len(self.logical_reference_payload),
            "logical_reference_payload_sha256": self.logical_reference_payload_sha256,
            "wire_wctd_nibbles": 256,
            "wire_wctd_message_bytes": 265,
            "sparse_hardware_enabled": self.sparse_hardware_enabled,
            "warnings": list(self.warnings),
            "boundaries": {
                "contains_wavetable_name": False,
                "opens_midi_port": False,
                "transmits_midi": False,
                "writes_memory": False,
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


@dataclass(frozen=True, slots=True)
class WctdMaterialization:
    schema_version: int
    policy: WctdMaterializationPolicy
    dense: MaterializedWctd
    sparse_candidate: MaterializedWctd | None
    sparse_enabled: bool
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WCTD_MATERIALIZATION_V8K_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-K WCTD set schema version")
        if not isinstance(self.policy, WctdMaterializationPolicy):
            raise WavetableContractError("policy must be WctdMaterializationPolicy")
        if not isinstance(self.dense, MaterializedWctd) or self.dense.mode is not WctdMode.DENSE:
            raise WavetableContractError("dense must be a dense MaterializedWctd")
        if self.sparse_candidate is not None and (
            not isinstance(self.sparse_candidate, MaterializedWctd)
            or self.sparse_candidate.mode is not WctdMode.SPARSE
        ):
            raise WavetableContractError("sparse_candidate must be sparse MaterializedWctd")
        if not isinstance(self.sparse_enabled, bool):
            raise WavetableContractError("sparse_enabled must be boolean")
        if self.sparse_enabled and self.sparse_candidate is None:
            raise WavetableContractError("sparse_enabled requires a sparse candidate")
        object.__setattr__(self, "warnings", _strings(self.warnings, name="warnings"))
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def active(self) -> MaterializedWctd:
        if self.policy.default_mode is WctdMode.SPARSE and self.sparse_enabled and self.sparse_candidate is not None:
            return self.sparse_candidate
        return self.dense

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy": self.policy.to_dict(),
            "dense": self.dense.to_dict(),
            "sparse_candidate": None if self.sparse_candidate is None else self.sparse_candidate.to_dict(),
            "sparse_enabled": self.sparse_enabled,
            "active_mode": self.active.mode.value,
            "warnings": list(self.warnings),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _assignment_numbers(allocation: AllocationProposal) -> tuple[int, ...]:
    if allocation.status is not AllocationProposalStatus.READY:
        raise WavetableContractError("V8-K materialization requires a ready allocation")
    assignments = tuple(allocation.assignments)
    if tuple(item.physical_index for item in assignments) != tuple(range(len(assignments))):
        raise WavetableContractError("Allocation assignments must use canonical physical order")
    return tuple(item.user_wave_number for item in assignments)


def _sparse_anchor_map(variant: CodeV8IVariant, numbers: tuple[int, ...]) -> dict[int, int]:
    consolidation = variant.consolidation
    if consolidation.mapping is None or consolidation.physical_wave_set is None:
        raise WavetableContractError("V8-I variant lacks consolidation mapping")
    mapping = consolidation.mapping
    waves = consolidation.physical_wave_set.waves
    anchors: dict[int, int] = {}
    for wave, logical_positions, number in zip(waves, mapping.physical_to_logical, numbers, strict=True):
        if 0 in logical_positions:
            position = 0
        elif USER_POSITION_COUNT - 1 in logical_positions:
            position = USER_POSITION_COUNT - 1
        elif wave.representative_position in logical_positions:
            position = wave.representative_position
        else:
            position = logical_positions[0]
        anchors[position] = number
    anchors[0] = numbers[mapping.logical_to_physical[0]]
    anchors[USER_POSITION_COUNT - 1] = numbers[mapping.logical_to_physical[USER_POSITION_COUNT - 1]]
    return anchors


def materialize_v8k_wctd(
    variant: CodeV8IVariant,
    allocation: AllocationProposal,
    fixed_tail: FixedTailContract,
    policy: WctdMaterializationPolicy = DEFAULT_WCTD_MATERIALIZATION_POLICY,
    *,
    sparse_hardware_enabled: bool = False,
) -> WctdMaterialization:
    """Materialize dense and optional sparse WCTD representations for V8-K.

    This function creates logical and wire-ready WCTD objects only.  It does not
    open MIDI, transmit data, or write instrument memory.
    """

    if not isinstance(variant, CodeV8IVariant):
        raise WavetableContractError("variant must be CodeV8IVariant")
    if not isinstance(allocation, AllocationProposal):
        raise WavetableContractError("allocation must be AllocationProposal")
    if not isinstance(fixed_tail, FixedTailContract):
        raise WavetableContractError("fixed_tail must be FixedTailContract")
    if not isinstance(policy, WctdMaterializationPolicy):
        raise WavetableContractError("policy must be WctdMaterializationPolicy")
    if allocation.physical_wave_set_sha256 != variant.consolidation.physical_wave_set.analysis_sha256:
        raise WavetableContractError("Allocation does not match the V8-I physical wave set")
    if allocation.user_wavetable_destination is None:
        raise WavetableContractError("User Wavetable destination must be selected manually")

    numbers = _assignment_numbers(allocation)
    mapping = variant.consolidation.mapping
    physical_set = variant.consolidation.physical_wave_set
    if mapping is None or physical_set is None:
        raise WavetableContractError("V8-I variant lacks complete consolidation outputs")
    if len(numbers) != physical_set.physical_wave_count:
        raise WavetableContractError("Allocation count disagrees with physical wave count")

    dense_user = tuple(numbers[index] for index in mapping.logical_to_physical)
    dense_refs = dense_user + tuple(fixed_tail.references)
    dense = MaterializedWctd(
        schema_version=WCTD_MATERIALIZATION_V8K_SCHEMA_VERSION,
        mode=WctdMode.DENSE,
        v8i_variant_sha256=variant.analysis_sha256,
        allocation_sha256=allocation.analysis_sha256,
        fixed_tail_sha256=fixed_tail.analysis_sha256,
        user_wavetable_destination=allocation.user_wavetable_destination,
        references=dense_refs,
        explicit_user_positions=tuple(range(USER_POSITION_COUNT)),
        interpolated_user_positions=(),
        allocated_user_wave_numbers=numbers,
        sparse_hardware_enabled=False,
        warnings=(),
        reason="Dense WCTD materializes all 61 logical positions explicitly and permits repeated physical references.",
    )

    sparse: MaterializedWctd | None = None
    warnings: list[str] = []
    if policy.build_sparse_candidate:
        anchors = _sparse_anchor_map(variant, numbers)
        sparse_user = tuple(anchors.get(position, INTERPOLATED_WAVE_REFERENCE) for position in range(USER_POSITION_COUNT))
        explicit = tuple(position for position, reference in enumerate(sparse_user) if reference != INTERPOLATED_WAVE_REFERENCE)
        interpolated = tuple(position for position, reference in enumerate(sparse_user) if reference == INTERPOLATED_WAVE_REFERENCE)
        sparse_warnings = []
        if not sparse_hardware_enabled:
            sparse_warnings.append("Sparse WCTD is a hardware-test candidate and is disabled until a real V8-K campaign passes.")
        sparse = MaterializedWctd(
            schema_version=WCTD_MATERIALIZATION_V8K_SCHEMA_VERSION,
            mode=WctdMode.SPARSE,
            v8i_variant_sha256=variant.analysis_sha256,
            allocation_sha256=allocation.analysis_sha256,
            fixed_tail_sha256=fixed_tail.analysis_sha256,
            user_wavetable_destination=allocation.user_wavetable_destination,
            references=sparse_user + tuple(fixed_tail.references),
            explicit_user_positions=explicit,
            interpolated_user_positions=interpolated,
            allocated_user_wave_numbers=numbers,
            sparse_hardware_enabled=sparse_hardware_enabled,
            warnings=tuple(sparse_warnings),
            reason="Sparse WCTD uses one explicit anchor per physical wave plus explicit user boundaries; remaining positions use the interpolation sentinel.",
        )
        warnings.extend(sparse_warnings)
    elif sparse_hardware_enabled:
        raise WavetableContractError("Sparse hardware cannot be enabled when no sparse candidate is built")

    return WctdMaterialization(
        schema_version=WCTD_MATERIALIZATION_V8K_SCHEMA_VERSION,
        policy=policy,
        dense=dense,
        sparse_candidate=sparse,
        sparse_enabled=sparse_hardware_enabled,
        warnings=tuple(warnings),
        reason="V8-K produced separate dense and sparse WCTD representations without confusing logical bytes, wire nibbles, or SysEx message length.",
    )


__all__ = [
    "WCTD_MATERIALIZATION_V8K_SCHEMA_VERSION",
    "WctdMode",
    "WctdMaterializationPolicy",
    "DEFAULT_WCTD_MATERIALIZATION_POLICY",
    "MaterializedWctd",
    "WctdMaterialization",
    "materialize_v8k_wctd",
]
