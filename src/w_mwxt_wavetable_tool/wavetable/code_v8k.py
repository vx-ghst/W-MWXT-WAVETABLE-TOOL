from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Mapping, Sequence

from ..destinations import DeviceAddress
from .code_v8i import CodeV8IAnalysis, CodeV8IStatus, CodeV8IVariant
from .code_v8j import CodeV8JAnalysis, CodeV8JStatus
from .hardware_gate import (
    V8KHardwareCampaignEvidence,
    V8KHardwareGatePlan,
    V8KHardwareGateReport,
    V8KHardwareGateStatus,
    create_v8k_hardware_gate_plan,
    evaluate_v8k_hardware_campaign,
)
from .materialization import (
    DEFAULT_WCTD_MATERIALIZATION_POLICY,
    WctdMaterialization,
    WctdMaterializationPolicy,
    WctdMode,
    materialize_v8k_wctd,
)
from .models import FixedTailContract, WavetableContractError
from .package import (
    CompletePackageContract,
    WavetablePackage,
    build_wavetable_package,
    complete_package_contract,
)

CODE_V8K_SCHEMA_VERSION = 1
_STEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")


def _canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _strings(values: Sequence[str], *, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence")
    result = tuple(dict.fromkeys(values))
    if any(not isinstance(item, str) or not item for item in result):
        raise WavetableContractError(f"{name} must contain non-empty strings")
    return result


class CodeV8KStatus(str, Enum):
    READY_FOR_HARDWARE = "ready_for_hardware"
    HARDWARE_ACCEPTED = "hardware_accepted"
    HARDWARE_FAILED = "hardware_failed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CodeV8KPolicy:
    schema_version: int = CODE_V8K_SCHEMA_VERSION
    materialization: WctdMaterializationPolicy = DEFAULT_WCTD_MATERIALIZATION_POLICY
    package_stem: str = "CODE_V8_K_WAVETABLE"
    reason: str = "Build dense by default, retain sparse as disabled candidate, and never transmit MIDI in V8."

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8K_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-K policy schema version")
        if not isinstance(self.materialization, WctdMaterializationPolicy):
            raise WavetableContractError("materialization must be WctdMaterializationPolicy")
        if not _STEM_RE.fullmatch(self.package_stem):
            raise WavetableContractError("package_stem must use 1..48 safe filename characters")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "materialization": self.materialization.to_dict(),
            "package_stem": self.package_stem,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_CODE_V8K_POLICY = CodeV8KPolicy()


@dataclass(frozen=True, slots=True)
class CodeV8KAnalysis:
    schema_version: int
    status: CodeV8KStatus
    v8i_analysis_sha256: str
    v8j_analysis_sha256: str
    selected_variant_id: str | None
    selected_v8i_variant_sha256: str | None
    fixed_tail_sha256: str
    policy: CodeV8KPolicy
    materialization: WctdMaterialization | None
    dense_package: WavetablePackage | None
    sparse_package_candidate: WavetablePackage | None
    active_package_mode: WctdMode | None
    complete_package_contract: CompletePackageContract | None
    hardware_plan: V8KHardwareGatePlan | None
    hardware_report: V8KHardwareGateReport | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8K_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-K schema version")
        if not isinstance(self.status, CodeV8KStatus):
            raise WavetableContractError("status must be CodeV8KStatus")
        for name in ("v8i_analysis_sha256", "v8j_analysis_sha256", "fixed_tail_sha256"):
            _sha256(getattr(self, name), name=name)
        if not isinstance(self.policy, CodeV8KPolicy):
            raise WavetableContractError("policy must be CodeV8KPolicy")
        warnings = _strings(self.warnings, name="warnings")
        blockers = _strings(self.blockers, name="blockers")
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "blockers", blockers)
        outputs = (
            self.materialization,
            self.dense_package,
            self.sparse_package_candidate,
            self.complete_package_contract,
            self.hardware_plan,
            self.hardware_report,
        )
        if self.status is CodeV8KStatus.REJECTED:
            if not blockers or any(item is not None for item in outputs) or self.active_package_mode is not None:
                raise WavetableContractError("rejected V8-K analysis requires blockers and no partial outputs")
            if self.selected_variant_id is not None or self.selected_v8i_variant_sha256 is not None:
                raise WavetableContractError("rejected V8-K analysis cannot expose a selected variant")
        else:
            if blockers or any(item is None for item in outputs):
                raise WavetableContractError("non-rejected V8-K analysis requires all outputs and no aggregate blockers")
            if not self.selected_variant_id or self.selected_v8i_variant_sha256 is None:
                raise WavetableContractError("V8-K analysis requires selected V8-I variant linkage")
            _sha256(self.selected_v8i_variant_sha256, name="selected_v8i_variant_sha256")
            if not isinstance(self.active_package_mode, WctdMode):
                raise WavetableContractError("active_package_mode must be WctdMode")
            assert self.materialization is not None
            assert self.dense_package is not None
            assert self.sparse_package_candidate is not None
            assert self.hardware_report is not None
            expected_status = {
                V8KHardwareGateStatus.PENDING: CodeV8KStatus.READY_FOR_HARDWARE,
                V8KHardwareGateStatus.PASS: CodeV8KStatus.HARDWARE_ACCEPTED,
                V8KHardwareGateStatus.FAIL: CodeV8KStatus.HARDWARE_FAILED,
            }[self.hardware_report.status]
            if self.status is not expected_status:
                raise WavetableContractError("V8-K status disagrees with hardware report")
            if self.materialization.sparse_enabled != self.hardware_report.sparse_enabled:
                raise WavetableContractError("sparse enablement disagrees with hardware report")
            if self.active_package_mode is WctdMode.SPARSE and not self.hardware_report.sparse_enabled:
                raise WavetableContractError("sparse package cannot be active before real hardware PASS")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def active_package(self) -> WavetablePackage | None:
        if self.active_package_mode is WctdMode.SPARSE:
            return self.sparse_package_candidate
        return self.dense_package

    @property
    def hardware_accepted(self) -> bool:
        return self.status is CodeV8KStatus.HARDWARE_ACCEPTED

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "v8i_analysis_sha256": self.v8i_analysis_sha256,
            "v8j_analysis_sha256": self.v8j_analysis_sha256,
            "selected_variant_id": self.selected_variant_id,
            "selected_v8i_variant_sha256": self.selected_v8i_variant_sha256,
            "fixed_tail_sha256": self.fixed_tail_sha256,
            "policy": self.policy.to_dict(),
            "materialization": None if self.materialization is None else self.materialization.to_dict(),
            "dense_package": None if self.dense_package is None else self.dense_package.to_dict(),
            "sparse_package_candidate": None if self.sparse_package_candidate is None else self.sparse_package_candidate.to_dict(),
            "active_package_mode": None if self.active_package_mode is None else self.active_package_mode.value,
            "active_package_sha256": None if self.active_package is None else self.active_package.sha256,
            "complete_package_contract": None if self.complete_package_contract is None else self.complete_package_contract.to_dict(),
            "hardware_plan": None if self.hardware_plan is None else self.hardware_plan.to_dict(),
            "hardware_report": None if self.hardware_report is None else self.hardware_report.to_dict(),
            "hardware_accepted": self.hardware_accepted,
            "requirements": {
                "CDC-SYX-002": "implemented",
                "CDC-SYX-005": "implemented",
                "CDC-HW-002": (
                    "V8_SCOPE_PASS_V10_OPEN"
                    if self.hardware_accepted
                    else "PENDING_REAL_HARDWARE_CAMPAIGN"
                ),
            },
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "boundaries": {
                "offline_sysex_generated": self.status is not CodeV8KStatus.REJECTED,
                "wavetable_package_n_plus_1": self.status is not CodeV8KStatus.REJECTED,
                "complete_package_n_plus_2": False,
                "sound_generated": False,
                "opens_midi_port": False,
                "transmits_midi": False,
                "writes_memory": False,
                "claims_hardware_pass_without_real_artifacts": False,
                "v8_l_started": False,
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


def _selected_variant(v8i: CodeV8IAnalysis, v8j: CodeV8JAnalysis) -> CodeV8IVariant | None:
    if v8j.selected_variant_id is None:
        return None
    for item in v8i.variants:
        if item.variant_id == v8j.selected_variant_id:
            return item
    return None


def _rejected(
    v8i: CodeV8IAnalysis,
    v8j: CodeV8JAnalysis,
    fixed_tail: FixedTailContract,
    policy: CodeV8KPolicy,
    blockers: Sequence[str],
    reason: str,
) -> CodeV8KAnalysis:
    return CodeV8KAnalysis(
        schema_version=CODE_V8K_SCHEMA_VERSION,
        status=CodeV8KStatus.REJECTED,
        v8i_analysis_sha256=v8i.analysis_sha256,
        v8j_analysis_sha256=v8j.analysis_sha256,
        selected_variant_id=None,
        selected_v8i_variant_sha256=None,
        fixed_tail_sha256=fixed_tail.analysis_sha256,
        policy=policy,
        materialization=None,
        dense_package=None,
        sparse_package_candidate=None,
        active_package_mode=None,
        complete_package_contract=None,
        hardware_plan=None,
        hardware_report=None,
        warnings=(),
        blockers=tuple(blockers),
        reason=reason,
    )


def build_code_v8k(
    v8i_analysis: CodeV8IAnalysis,
    v8j_analysis: CodeV8JAnalysis,
    fixed_tail: FixedTailContract,
    device: DeviceAddress,
    policy: CodeV8KPolicy = DEFAULT_CODE_V8K_POLICY,
    hardware_evidence: V8KHardwareCampaignEvidence | None = None,
) -> CodeV8KAnalysis:
    """Materialize dense/sparse WCTD and deterministic N+1 packages.

    V8-K generates offline SysEx bytes but never opens MIDI, transmits data, or
    writes XT memory.  Sparse mode remains disabled until a real artifact-backed
    18-step campaign passes.
    """

    if not isinstance(v8i_analysis, CodeV8IAnalysis):
        raise WavetableContractError("v8i_analysis must be CodeV8IAnalysis")
    if not isinstance(v8j_analysis, CodeV8JAnalysis):
        raise WavetableContractError("v8j_analysis must be CodeV8JAnalysis")
    if not isinstance(fixed_tail, FixedTailContract):
        raise WavetableContractError("fixed_tail must be FixedTailContract")
    if not isinstance(device, DeviceAddress):
        raise WavetableContractError("device must be DeviceAddress")
    if not isinstance(policy, CodeV8KPolicy):
        raise WavetableContractError("policy must be CodeV8KPolicy")

    if v8i_analysis.status is not CodeV8IStatus.COMPLETE:
        return _rejected(v8i_analysis, v8j_analysis, fixed_tail, policy, ("V8-K requires complete V8-I input.",), "V8-K rejected incomplete V8-I without partial package output.")
    if v8j_analysis.status is not CodeV8JStatus.COMPLETE:
        return _rejected(v8i_analysis, v8j_analysis, fixed_tail, policy, ("V8-K requires complete V8-J input.",), "V8-K rejected incomplete V8-J without partial package output.")
    if v8j_analysis.v8i_analysis_sha256 != v8i_analysis.analysis_sha256:
        return _rejected(v8i_analysis, v8j_analysis, fixed_tail, policy, ("V8-J does not link to the supplied V8-I analysis.",), "V8-K rejected mismatched V8-I/V8-J evidence.")
    variant = _selected_variant(v8i_analysis, v8j_analysis)
    if variant is None or variant.analysis_sha256 != v8j_analysis.selected_v8i_variant_sha256:
        return _rejected(v8i_analysis, v8j_analysis, fixed_tail, policy, ("Selected V8-I variant linkage is invalid.",), "V8-K rejected invalid selected-variant evidence.")
    if v8j_analysis.allocation is None or not v8j_analysis.allocation_ready:
        blockers = (
            "V8-J allocation is not ready; V8-K cannot materialize a package.",
            *(v8j_analysis.allocation.blockers if v8j_analysis.allocation is not None else ()),
        )
        return _rejected(v8i_analysis, v8j_analysis, fixed_tail, policy, blockers, "V8-K blocked package generation rather than using unsafe destinations.")
    if v8j_analysis.inventory is None:
        return _rejected(v8i_analysis, v8j_analysis, fixed_tail, policy, ("V8-J inventory is absent.",), "V8-K requires inventory linkage.")

    allocation = v8j_analysis.allocation
    physical_set = variant.consolidation.physical_wave_set
    if physical_set is None:
        raise WavetableContractError("complete V8-I variant lacks physical_wave_set")

    initial = materialize_v8k_wctd(
        variant,
        allocation,
        fixed_tail,
        policy.materialization,
        sparse_hardware_enabled=False,
    )
    if initial.sparse_candidate is None:
        return _rejected(v8i_analysis, v8j_analysis, fixed_tail, policy, ("V8-K requires a sparse candidate for the mandatory hardware comparison.",), "V8-K rejected a policy that omitted the canonical sparse candidate.")
    dense_package = build_wavetable_package(
        physical_set,
        allocation,
        initial.dense,
        device,
        package_name=f"{policy.package_stem}_DENSE",
    )
    sparse_package = build_wavetable_package(
        physical_set,
        allocation,
        initial.sparse_candidate,
        device,
        package_name=f"{policy.package_stem}_SPARSE",
    )
    hardware_plan = create_v8k_hardware_gate_plan(dense_package, sparse_package, v8j_analysis)
    hardware_report = evaluate_v8k_hardware_campaign(hardware_plan, hardware_evidence)

    materialization = initial
    if hardware_report.sparse_enabled:
        materialization = materialize_v8k_wctd(
            variant,
            allocation,
            fixed_tail,
            policy.materialization,
            sparse_hardware_enabled=True,
        )
        assert materialization.sparse_candidate is not None
        dense_package = build_wavetable_package(
            physical_set,
            allocation,
            materialization.dense,
            device,
            package_name=f"{policy.package_stem}_DENSE",
        )
        sparse_package = build_wavetable_package(
            physical_set,
            allocation,
            materialization.sparse_candidate,
            device,
            package_name=f"{policy.package_stem}_SPARSE",
        )

    active_mode = (
        WctdMode.SPARSE
        if policy.materialization.default_mode is WctdMode.SPARSE and hardware_report.sparse_enabled
        else WctdMode.DENSE
    )
    contract = complete_package_contract(dense_package)
    status = {
        V8KHardwareGateStatus.PENDING: CodeV8KStatus.READY_FOR_HARDWARE,
        V8KHardwareGateStatus.PASS: CodeV8KStatus.HARDWARE_ACCEPTED,
        V8KHardwareGateStatus.FAIL: CodeV8KStatus.HARDWARE_FAILED,
    }[hardware_report.status]
    warnings = list(v8i_analysis.warnings)
    warnings.extend(v8j_analysis.warnings)
    warnings.extend(materialization.warnings)
    warnings.extend(hardware_report.warnings)
    if hardware_report.status is V8KHardwareGateStatus.FAIL:
        warnings.extend(hardware_report.blockers)

    return CodeV8KAnalysis(
        schema_version=CODE_V8K_SCHEMA_VERSION,
        status=status,
        v8i_analysis_sha256=v8i_analysis.analysis_sha256,
        v8j_analysis_sha256=v8j_analysis.analysis_sha256,
        selected_variant_id=variant.variant_id,
        selected_v8i_variant_sha256=variant.analysis_sha256,
        fixed_tail_sha256=fixed_tail.analysis_sha256,
        policy=policy,
        materialization=materialization,
        dense_package=dense_package,
        sparse_package_candidate=sparse_package,
        active_package_mode=active_mode,
        complete_package_contract=contract,
        hardware_plan=hardware_plan,
        hardware_report=hardware_report,
        warnings=tuple(warnings),
        blockers=(),
        reason=(
            "V8-K hardware campaign passed; sparse WCTD is enabled while V10 calibration remains open."
            if status is CodeV8KStatus.HARDWARE_ACCEPTED
            else "V8-K materialized deterministic dense/sparse packages and retained explicit real-hardware gate state."
        ),
    )


__all__ = [
    "CODE_V8K_SCHEMA_VERSION",
    "CodeV8KStatus",
    "CodeV8KPolicy",
    "DEFAULT_CODE_V8K_POLICY",
    "CodeV8KAnalysis",
    "build_code_v8k",
]
