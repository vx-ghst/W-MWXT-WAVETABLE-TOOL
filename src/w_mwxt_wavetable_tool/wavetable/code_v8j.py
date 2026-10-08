from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping

from ..destinations import UserWavetableDestination
from ..inventory import XtMemoryInventory
from .allocation import (
    DEFAULT_SAFE_ALLOCATION_POLICY,
    AllocationProposal,
    AllocationProposalStatus,
    SafeAllocationPolicy,
    plan_safe_user_wave_allocation,
)
from .code_v8i import CodeV8IAnalysis, CodeV8IStatus, CodeV8IVariant
from .models import WavetableContractError

CODE_V8J_SCHEMA_VERSION = 1


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


class CodeV8JStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CodeV8JAnalysis:
    schema_version: int
    status: CodeV8JStatus
    v8i_analysis_sha256: str
    selected_variant_id: str | None
    selected_v8i_variant_sha256: str | None
    inventory: XtMemoryInventory | None
    policy: SafeAllocationPolicy
    allocation: AllocationProposal | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8J_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-J schema version")
        if not isinstance(self.status, CodeV8JStatus):
            raise WavetableContractError("status must be CodeV8JStatus")
        _sha256(self.v8i_analysis_sha256, name="v8i_analysis_sha256")
        if not isinstance(self.policy, SafeAllocationPolicy):
            raise WavetableContractError("policy must be SafeAllocationPolicy")
        warnings = tuple(dict.fromkeys(self.warnings))
        blockers = tuple(dict.fromkeys(self.blockers))
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "blockers", blockers)
        if any(not isinstance(item, str) or not item for item in warnings + blockers):
            raise WavetableContractError("warnings and blockers must contain non-empty strings")
        if self.status is CodeV8JStatus.COMPLETE:
            if blockers:
                raise WavetableContractError("complete V8-J analysis cannot have aggregate blockers")
            if not self.selected_variant_id or self.selected_v8i_variant_sha256 is None:
                raise WavetableContractError("complete V8-J analysis requires one selected V8-I variant")
            _sha256(self.selected_v8i_variant_sha256, name="selected_v8i_variant_sha256")
            if not isinstance(self.inventory, XtMemoryInventory):
                raise WavetableContractError("complete V8-J analysis requires XtMemoryInventory")
            if not isinstance(self.allocation, AllocationProposal):
                raise WavetableContractError("complete V8-J analysis requires AllocationProposal")
            if self.allocation.inventory_sha256 != self.inventory.analysis_sha256:
                raise WavetableContractError("allocation and inventory hashes disagree")
            if self.allocation.policy_sha256 != self.policy.analysis_sha256:
                raise WavetableContractError("allocation and policy hashes disagree")
        else:
            if not blockers:
                raise WavetableContractError("rejected V8-J analysis requires blockers")
            if any(
                item is not None
                for item in (
                    self.selected_variant_id,
                    self.selected_v8i_variant_sha256,
                    self.inventory,
                    self.allocation,
                )
            ):
                raise WavetableContractError("rejected V8-J analysis cannot expose partial outputs")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def allocation_ready(self) -> bool:
        return bool(
            self.allocation is not None
            and self.allocation.status is AllocationProposalStatus.READY
        )

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "v8i_analysis_sha256": self.v8i_analysis_sha256,
            "selected_variant_id": self.selected_variant_id,
            "selected_v8i_variant_sha256": self.selected_v8i_variant_sha256,
            "inventory": None if self.inventory is None else self.inventory.to_dict(),
            "policy": self.policy.to_dict(),
            "allocation": None if self.allocation is None else self.allocation.to_dict(),
            "allocation_ready": self.allocation_ready,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "software_gate": {
                "inventory_models": "implemented",
                "external_dump_parser": "implemented",
                "deterministic_allocation": "implemented",
                "unknown_never_selected": True,
                "safe_free_requires_proof": True,
                "safe_free_activation_gate": "v8_k_hardware_evidence",
            },
            "boundaries": {
                "user_wavetable_selected_manually": True,
                "wctd_materialized": False,
                "sysex_generated": False,
                "midi_opened": False,
                "midi_transmitted": False,
                "memory_written": False,
                "v8_k_started": False,
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
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"


def _variant_by_id(v8i_analysis: CodeV8IAnalysis, variant_id: str | None) -> CodeV8IVariant | None:
    if not v8i_analysis.variants:
        return None
    if variant_id is None:
        return v8i_analysis.primary_variant
    for item in v8i_analysis.variants:
        if item.variant_id == variant_id:
            return item
    return None


def build_code_v8j(
    v8i_analysis: CodeV8IAnalysis,
    inventory: XtMemoryInventory,
    user_wavetable_destination: UserWavetableDestination,
    policy: SafeAllocationPolicy = DEFAULT_SAFE_ALLOCATION_POLICY,
    *,
    variant_id: str | None = None,
) -> CodeV8JAnalysis:
    """Inventory XT memory and propose destinations for one V8-I physical set.

    The User Wavetable destination is always supplied explicitly.  A blocked
    allocation remains a valid V8-J software result: it proves that insufficient
    evidence never falls back to UNKNOWN or unauthorized overwrites.
    """

    if not isinstance(v8i_analysis, CodeV8IAnalysis):
        raise WavetableContractError("v8i_analysis must be CodeV8IAnalysis")
    if not isinstance(inventory, XtMemoryInventory):
        raise WavetableContractError("inventory must be XtMemoryInventory")
    if not isinstance(user_wavetable_destination, UserWavetableDestination):
        raise WavetableContractError("User Wavetable destination must be selected manually")
    if not isinstance(policy, SafeAllocationPolicy):
        raise WavetableContractError("policy must be SafeAllocationPolicy")

    if v8i_analysis.status is not CodeV8IStatus.COMPLETE:
        return CodeV8JAnalysis(
            schema_version=CODE_V8J_SCHEMA_VERSION,
            status=CodeV8JStatus.REJECTED,
            v8i_analysis_sha256=v8i_analysis.analysis_sha256,
            selected_variant_id=None,
            selected_v8i_variant_sha256=None,
            inventory=None,
            policy=policy,
            allocation=None,
            warnings=tuple(v8i_analysis.warnings),
            blockers=("V8-J requires a complete V8-I analysis.",),
            reason="CODE V8-J rejected incomplete V8-I input without partial output.",
        )

    selected = _variant_by_id(v8i_analysis, variant_id)
    if selected is None:
        return CodeV8JAnalysis(
            schema_version=CODE_V8J_SCHEMA_VERSION,
            status=CodeV8JStatus.REJECTED,
            v8i_analysis_sha256=v8i_analysis.analysis_sha256,
            selected_variant_id=None,
            selected_v8i_variant_sha256=None,
            inventory=None,
            policy=policy,
            allocation=None,
            warnings=tuple(v8i_analysis.warnings),
            blockers=("Requested V8-I variant does not exist.",),
            reason="CODE V8-J rejected an unknown V8-I variant identifier.",
        )

    physical_set = selected.consolidation.physical_wave_set
    if physical_set is None:
        raise WavetableContractError("complete V8-I variant is missing physical_wave_set")
    allocation = plan_safe_user_wave_allocation(
        physical_set,
        inventory,
        user_wavetable_destination,
        policy,
    )
    warnings = list(v8i_analysis.warnings)
    warnings.extend(inventory.evidence_status.warnings)
    warnings.extend(allocation.warnings)
    if allocation.status is AllocationProposalStatus.BLOCKED:
        warnings.extend(allocation.blockers)

    return CodeV8JAnalysis(
        schema_version=CODE_V8J_SCHEMA_VERSION,
        status=CodeV8JStatus.COMPLETE,
        v8i_analysis_sha256=v8i_analysis.analysis_sha256,
        selected_variant_id=selected.variant_id,
        selected_v8i_variant_sha256=selected.analysis_sha256,
        inventory=inventory,
        policy=policy,
        allocation=allocation,
        warnings=tuple(dict.fromkeys(warnings)),
        blockers=(),
        reason=(
            "V8-J produced a ready deterministic allocation proposal."
            if allocation.status is AllocationProposalStatus.READY
            else "V8-J completed the conservative inventory contract and correctly blocked unsafe allocation."
        ),
    )


__all__ = [
    "CODE_V8J_SCHEMA_VERSION",
    "CodeV8JStatus",
    "CodeV8JAnalysis",
    "build_code_v8j",
]
