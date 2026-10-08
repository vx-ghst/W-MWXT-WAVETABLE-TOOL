from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from .builder import CodeV8EAnalysis
from .factory_style import (
    DEFAULT_FACTORY_STYLE_POLICY,
    FactoryStyleAnalysis,
    FactoryStylePolicy,
    FactoryStyleStatus,
    apply_factory_style,
)
from .models import WavetableBuildRequest, WavetableContractError
from .wctd import (
    WCTD_MODEL_SCHEMA_VERSION,
    WctdMaterializationSet,
    WctdMaterializationStatus,
    WctdReferenceModel,
    materialize_wctd_models,
)

HARDWARE_GATE_SCHEMA_VERSION = 1


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _normalized(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise WavetableContractError(f"{name} must be a normalized non-empty string")
    return value


def _entries(values: Sequence[str], *, name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence")
    result = tuple(_normalized(value, name=f"{name} entry") for value in values)
    if not allow_empty and not result:
        raise WavetableContractError(f"{name} must not be empty")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


class HardwareGateKind(str, Enum):
    KNOWN_REFERENCE_PAIR = "known_reference_pair"
    INTERMEDIATE_POSITIONS = "intermediate_positions"
    TAIL_POSITIONS_60_63 = "tail_positions_60_63"
    SLOW_SCAN = "slow_scan"
    FAST_SCAN = "fast_scan"
    READ_BACK = "read_back"


class HardwareGateResultStatus(str, Enum):
    BLOCKED = "blocked"
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"


class HardwareGatePlanStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    FAILED = "failed"


class CodeV8FStatus(str, Enum):
    READY_FOR_HARDWARE = "ready_for_hardware"
    HARDWARE_ACCEPTED = "hardware_accepted"
    HARDWARE_FAILED = "hardware_failed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class HardwareGateRequirement:
    schema_version: int
    gate_id: str
    kind: HardwareGateKind
    required_positions: tuple[int, ...]
    minimum_observation_count: int
    requires_binary_ready_model: bool
    evidence_requirements: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != HARDWARE_GATE_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported hardware-gate requirement schema version")
        _normalized(self.gate_id, name="gate_id")
        if not isinstance(self.kind, HardwareGateKind):
            raise WavetableContractError("kind must be HardwareGateKind")
        positions = tuple(self.required_positions)
        object.__setattr__(self, "required_positions", positions)
        if positions != tuple(sorted(set(positions))) or any(not 0 <= item < 64 for item in positions):
            raise WavetableContractError("required_positions must be unique sorted positions in 0..63")
        if (
            isinstance(self.minimum_observation_count, bool)
            or not isinstance(self.minimum_observation_count, int)
            or self.minimum_observation_count < 0
        ):
            raise WavetableContractError("minimum_observation_count must be non-negative")
        if not isinstance(self.requires_binary_ready_model, bool):
            raise WavetableContractError("requires_binary_ready_model must be boolean")
        object.__setattr__(
            self,
            "evidence_requirements",
            _entries(self.evidence_requirements, name="evidence_requirements", allow_empty=False),
        )
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "gate_id": self.gate_id,
            "kind": self.kind.value,
            "required_positions": list(self.required_positions),
            "display_required_positions": [item + 1 for item in self.required_positions],
            "minimum_observation_count": self.minimum_observation_count,
            "requires_binary_ready_model": self.requires_binary_ready_model,
            "evidence_requirements": list(self.evidence_requirements),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class HardwareGateEvidence:
    schema_version: int
    gate_id: str
    source_artifact_sha256: str
    passed: bool
    observed_positions: tuple[int, ...]
    observed_references: tuple[int, ...]
    observed_reference_payload_sha256: str | None
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != HARDWARE_GATE_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported hardware-gate evidence schema version")
        _normalized(self.gate_id, name="gate_id")
        _sha256(self.source_artifact_sha256, name="source_artifact_sha256")
        if not isinstance(self.passed, bool):
            raise WavetableContractError("passed must be boolean")
        positions = tuple(self.observed_positions)
        references = tuple(self.observed_references)
        object.__setattr__(self, "observed_positions", positions)
        object.__setattr__(self, "observed_references", references)
        if positions != tuple(sorted(set(positions))) or any(not 0 <= item < 64 for item in positions):
            raise WavetableContractError("observed_positions must be unique sorted positions in 0..63")
        if len(references) != len(positions):
            raise WavetableContractError("observed_references must align with observed_positions")
        if any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 0xFFFF for item in references):
            raise WavetableContractError("observed reference is outside uint16")
        if self.observed_reference_payload_sha256 is not None:
            _sha256(self.observed_reference_payload_sha256, name="observed_reference_payload_sha256")
        object.__setattr__(self, "evidence", _entries(self.evidence, name="evidence", allow_empty=False))
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "gate_id": self.gate_id,
            "source_artifact_sha256": self.source_artifact_sha256,
            "passed": self.passed,
            "observed_positions": list(self.observed_positions),
            "display_observed_positions": [item + 1 for item in self.observed_positions],
            "observed_references": list(self.observed_references),
            "observed_reference_payload_sha256": self.observed_reference_payload_sha256,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class HardwareGateResult:
    schema_version: int
    requirement: HardwareGateRequirement
    status: HardwareGateResultStatus
    evidence: HardwareGateEvidence | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != HARDWARE_GATE_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported hardware-gate result schema version")
        if not isinstance(self.requirement, HardwareGateRequirement):
            raise WavetableContractError("requirement must be HardwareGateRequirement")
        if not isinstance(self.status, HardwareGateResultStatus):
            raise WavetableContractError("status must be HardwareGateResultStatus")
        if self.evidence is not None:
            if not isinstance(self.evidence, HardwareGateEvidence):
                raise WavetableContractError("evidence must be HardwareGateEvidence")
            if self.evidence.gate_id != self.requirement.gate_id:
                raise WavetableContractError("evidence gate_id disagrees with requirement")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        object.__setattr__(self, "blockers", _entries(self.blockers, name="blockers"))
        if self.status is HardwareGateResultStatus.PASS and (self.evidence is None or not self.evidence.passed or self.blockers):
            raise WavetableContractError("passing gate requires passing evidence and no blockers")
        if self.status is HardwareGateResultStatus.FAIL and (self.evidence is None or not self.blockers):
            raise WavetableContractError("failed gate requires evidence and blockers")
        if self.status in {HardwareGateResultStatus.PENDING, HardwareGateResultStatus.BLOCKED} and self.evidence is not None:
            raise WavetableContractError("pending or blocked gates cannot attach evidence")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "requirement": self.requirement.to_dict(),
            "status": self.status.value,
            "evidence": None if self.evidence is None else self.evidence.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class HardwareGatePlan:
    schema_version: int
    status: HardwareGatePlanStatus
    wctd_model_sha256: str
    requirements: tuple[HardwareGateRequirement, ...]
    results: tuple[HardwareGateResult, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != HARDWARE_GATE_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported hardware-gate plan schema version")
        if not isinstance(self.status, HardwareGatePlanStatus):
            raise WavetableContractError("status must be HardwareGatePlanStatus")
        _sha256(self.wctd_model_sha256, name="wctd_model_sha256")
        requirements = tuple(self.requirements)
        results = tuple(self.results)
        object.__setattr__(self, "requirements", requirements)
        object.__setattr__(self, "results", results)
        if len(requirements) != 6 or len(results) != 6:
            raise WavetableContractError("hardware gate plan requires exactly six gates")
        if tuple(item.gate_id for item in requirements) != tuple(item.requirement.gate_id for item in results):
            raise WavetableContractError("hardware gate results disagree with requirements")
        if len({item.gate_id for item in requirements}) != len(requirements):
            raise WavetableContractError("hardware gate IDs must be unique")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        object.__setattr__(self, "blockers", _entries(self.blockers, name="blockers"))
        statuses = tuple(item.status for item in results)
        if self.status is HardwareGatePlanStatus.ACCEPTED and any(item is not HardwareGateResultStatus.PASS for item in statuses):
            raise WavetableContractError("accepted hardware plan requires six passing gates")
        if self.status is HardwareGatePlanStatus.FAILED and HardwareGateResultStatus.FAIL not in statuses:
            raise WavetableContractError("failed hardware plan requires at least one failed gate")
        if self.status is HardwareGatePlanStatus.PENDING and all(item is HardwareGateResultStatus.PASS for item in statuses):
            raise WavetableContractError("pending hardware plan cannot have six passing gates")
        _normalized(self.reason, name="reason")

    @property
    def accepted(self) -> bool:
        return self.status is HardwareGatePlanStatus.ACCEPTED

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "wctd_model_sha256": self.wctd_model_sha256,
            "requirements": [item.to_dict() for item in self.requirements],
            "results": [item.to_dict() for item in self.results],
            "accepted": self.accepted,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "hardware_evidence_required": True,
                "claims_hardware_acceptance_without_evidence": False,
                "generates_sysex": False,
                "opens_midi_port": False,
                "transmits_midi": False,
            },
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class CodeV8FAnalysis:
    schema_version: int
    status: CodeV8FStatus
    request_sha256: str
    v8e_analysis_sha256: str
    factory_style: FactoryStyleAnalysis
    wctd_models: WctdMaterializationSet
    hardware_gates: HardwareGatePlan | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != HARDWARE_GATE_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-F schema version")
        if not isinstance(self.status, CodeV8FStatus):
            raise WavetableContractError("status must be CodeV8FStatus")
        _sha256(self.request_sha256, name="request_sha256")
        _sha256(self.v8e_analysis_sha256, name="v8e_analysis_sha256")
        if not isinstance(self.factory_style, FactoryStyleAnalysis):
            raise WavetableContractError("factory_style must be FactoryStyleAnalysis")
        if not isinstance(self.wctd_models, WctdMaterializationSet):
            raise WavetableContractError("wctd_models must be WctdMaterializationSet")
        if self.hardware_gates is not None and not isinstance(self.hardware_gates, HardwareGatePlan):
            raise WavetableContractError("hardware_gates must be HardwareGatePlan")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        object.__setattr__(self, "blockers", _entries(self.blockers, name="blockers"))
        _normalized(self.reason, name="reason")
        if self.status is CodeV8FStatus.REJECTED:
            if not self.blockers or self.hardware_gates is not None:
                raise WavetableContractError("rejected V8-F result requires blockers and no gate plan")
        else:
            if self.blockers or self.hardware_gates is None:
                raise WavetableContractError("non-rejected V8-F result requires a gate plan and no blockers")
            expected = {
                HardwareGatePlanStatus.PENDING: CodeV8FStatus.READY_FOR_HARDWARE,
                HardwareGatePlanStatus.ACCEPTED: CodeV8FStatus.HARDWARE_ACCEPTED,
                HardwareGatePlanStatus.FAILED: CodeV8FStatus.HARDWARE_FAILED,
            }[self.hardware_gates.status]
            if self.status is not expected:
                raise WavetableContractError("V8-F status disagrees with hardware gate plan")

    @property
    def hardware_accepted(self) -> bool:
        return self.status is CodeV8FStatus.HARDWARE_ACCEPTED

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "v8e_analysis_sha256": self.v8e_analysis_sha256,
            "factory_style": self.factory_style.to_dict(),
            "wctd_models": self.wctd_models.to_dict(),
            "hardware_gates": None if self.hardware_gates is None else self.hardware_gates.to_dict(),
            "hardware_accepted": self.hardware_accepted,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "applies_factory_style": self.factory_style.applied,
                "materializes_wctd_reference_model": True,
                "serializes_complete_wctd_dump": False,
                "generates_sysex": False,
                "opens_midi_port": False,
                "transmits_midi": False,
                "completes_release": False,
            },
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


def default_hardware_gate_requirements() -> tuple[HardwareGateRequirement, ...]:
    return (
        HardwareGateRequirement(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-known-reference-pair",
            HardwareGateKind.KNOWN_REFERENCE_PAIR,
            (),
            2,
            True,
            ("two known references", "observed reference words", "artifact hash"),
            "Confirm two known WCTD references before broader scanning.",
        ),
        HardwareGateRequirement(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-intermediate-positions",
            HardwareGateKind.INTERMEDIATE_POSITIONS,
            (),
            1,
            True,
            ("at least one intermediate position", "observed reference word", "artifact hash"),
            "Confirm at least one intermediate position between table endpoints.",
        ),
        HardwareGateRequirement(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-tail-positions-60-63",
            HardwareGateKind.TAIL_POSITIONS_60_63,
            (60, 61, 62, 63),
            4,
            True,
            ("positions 60 through 63", "exact reference words", "artifact hash"),
            "Confirm the final editable position and three fixed-tail references.",
        ),
        HardwareGateRequirement(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-slow-scan",
            HardwareGateKind.SLOW_SCAN,
            (),
            0,
            True,
            ("controlled slow scan", "capture or observation hash", "pass/fail rationale"),
            "Evaluate slow table traversal without inferring undocumented DSP behavior.",
        ),
        HardwareGateRequirement(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-fast-scan",
            HardwareGateKind.FAST_SCAN,
            (),
            0,
            True,
            ("controlled fast scan", "capture or observation hash", "pass/fail rationale"),
            "Evaluate fast table traversal without inferring undocumented DSP behavior.",
        ),
        HardwareGateRequirement(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-read-back",
            HardwareGateKind.READ_BACK,
            tuple(range(64)),
            64,
            True,
            ("complete read-back", "64 reference words", "exact reference payload hash"),
            "Require exact read-back of the complete 64-reference model.",
        ),
    )


def _validate_observation(requirement: HardwareGateRequirement, model: WctdReferenceModel, evidence: HardwareGateEvidence) -> tuple[str, ...]:
    problems: list[str] = []
    if len(evidence.observed_positions) < requirement.minimum_observation_count:
        problems.append("insufficient observed positions")
    if requirement.required_positions and not set(requirement.required_positions).issubset(evidence.observed_positions):
        problems.append("required positions are absent from evidence")
    expected = dict(enumerate(model.reference_words))
    for position, reference in zip(evidence.observed_positions, evidence.observed_references):
        if expected[position] != reference:
            problems.append(f"reference mismatch at position {position}")
    if requirement.kind is HardwareGateKind.KNOWN_REFERENCE_PAIR and len(evidence.observed_positions) < 2:
        problems.append("known-reference gate requires two positions")
    if requirement.kind is HardwareGateKind.INTERMEDIATE_POSITIONS and not any(0 < item < 60 for item in evidence.observed_positions):
        problems.append("intermediate-position evidence must include a position from 1 through 59")
    if requirement.kind is HardwareGateKind.READ_BACK:
        if evidence.observed_positions != tuple(range(64)):
            problems.append("read-back evidence must contain positions 0 through 63")
        if evidence.observed_reference_payload_sha256 != model.reference_payload_sha256:
            problems.append("read-back payload hash does not match the WCTD model")
    return tuple(dict.fromkeys(problems))


def evaluate_hardware_gates(
    model: WctdReferenceModel,
    evidence: Sequence[HardwareGateEvidence] = (),
) -> HardwareGatePlan:
    """Evaluate six explicit hardware gates without opening MIDI or transmitting data."""

    if not isinstance(model, WctdReferenceModel):
        raise WavetableContractError("model must be WctdReferenceModel")
    evidence_tuple = tuple(evidence)
    if any(not isinstance(item, HardwareGateEvidence) for item in evidence_tuple):
        raise WavetableContractError("evidence must contain HardwareGateEvidence")
    evidence_by_id = {item.gate_id: item for item in evidence_tuple}
    if len(evidence_by_id) != len(evidence_tuple):
        raise WavetableContractError("hardware gate evidence IDs must be unique")
    requirements = default_hardware_gate_requirements()
    unknown = sorted(set(evidence_by_id) - {item.gate_id for item in requirements})
    if unknown:
        raise WavetableContractError(f"unknown hardware gate evidence IDs: {unknown}")
    results: list[HardwareGateResult] = []
    for requirement in requirements:
        item = evidence_by_id.get(requirement.gate_id)
        if item is None:
            if requirement.requires_binary_ready_model and not model.binary_ready:
                status = HardwareGateResultStatus.BLOCKED
                blockers = ("WCTD user references are unresolved",)
                reason = "Gate blocked until an explicit 61-reference allocation is supplied."
            else:
                status = HardwareGateResultStatus.PENDING
                blockers = ()
                reason = "Gate awaits controlled hardware evidence."
            results.append(
                HardwareGateResult(
                    HARDWARE_GATE_SCHEMA_VERSION,
                    requirement,
                    status,
                    None,
                    (),
                    blockers,
                    reason,
                )
            )
            continue
        problems = list(_validate_observation(requirement, model, item))
        if not model.binary_ready:
            problems.append("WCTD model is not binary-ready")
        if not item.passed:
            problems.append("hardware evidence explicitly reports failure")
        if problems:
            results.append(
                HardwareGateResult(
                    HARDWARE_GATE_SCHEMA_VERSION,
                    requirement,
                    HardwareGateResultStatus.FAIL,
                    item,
                    (),
                    tuple(dict.fromkeys(problems)),
                    "Hardware gate failed with explicit evidence.",
                )
            )
        else:
            results.append(
                HardwareGateResult(
                    HARDWARE_GATE_SCHEMA_VERSION,
                    requirement,
                    HardwareGateResultStatus.PASS,
                    item,
                    (),
                    (),
                    "Hardware gate passed with explicit evidence.",
                )
            )
    statuses = tuple(item.status for item in results)
    if HardwareGateResultStatus.FAIL in statuses:
        status = HardwareGatePlanStatus.FAILED
    elif all(item is HardwareGateResultStatus.PASS for item in statuses):
        status = HardwareGatePlanStatus.ACCEPTED
    else:
        status = HardwareGatePlanStatus.PENDING
    blockers = tuple(dict.fromkeys(blocker for result in results for blocker in result.blockers))
    warnings = () if model.binary_ready else ("hardware gates remain blocked until user references are resolved",)
    return HardwareGatePlan(
        schema_version=HARDWARE_GATE_SCHEMA_VERSION,
        status=status,
        wctd_model_sha256=model.analysis_sha256,
        requirements=requirements,
        results=tuple(results),
        warnings=warnings,
        blockers=blockers,
        reason=(
            "All six hardware gates passed with explicit evidence."
            if status is HardwareGatePlanStatus.ACCEPTED
            else "Hardware gate plan records unresolved or failed evidence without guessing."
        ),
    )


def build_code_v8f(
    request: WavetableBuildRequest,
    v8e_analysis: CodeV8EAnalysis,
    factory_policy: FactoryStylePolicy = DEFAULT_FACTORY_STYLE_POLICY,
    allocations: Mapping[str, Sequence[int]] | None = None,
    hardware_evidence: Sequence[HardwareGateEvidence] = (),
) -> CodeV8FAnalysis:
    """Build the V8-F Factory Style, WCTD model and hardware-gate aggregate."""

    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(v8e_analysis, CodeV8EAnalysis):
        raise WavetableContractError("v8e_analysis must be CodeV8EAnalysis")
    if v8e_analysis.request_sha256 != request.analysis_sha256:
        raise WavetableContractError("V8-E analysis does not link to request")
    factory_style = apply_factory_style(request, v8e_analysis, factory_policy)
    wctd_models = materialize_wctd_models(factory_style, allocations)
    if factory_style.status is not FactoryStyleStatus.COMPLETE or wctd_models.status is not WctdMaterializationStatus.COMPLETE:
        blockers = tuple(dict.fromkeys(factory_style.blockers + wctd_models.blockers)) or ("V8-F prerequisite failed",)
        return CodeV8FAnalysis(
            schema_version=HARDWARE_GATE_SCHEMA_VERSION,
            status=CodeV8FStatus.REJECTED,
            request_sha256=request.analysis_sha256,
            v8e_analysis_sha256=v8e_analysis.analysis_sha256,
            factory_style=factory_style,
            wctd_models=wctd_models,
            hardware_gates=None,
            warnings=tuple(dict.fromkeys(factory_style.warnings + wctd_models.warnings)),
            blockers=blockers,
            reason="CODE V8-F rejected the input without partial hardware acceptance claims.",
        )
    primary = wctd_models.primary_model
    assert primary is not None
    hardware_gates = evaluate_hardware_gates(primary, hardware_evidence)
    status = {
        HardwareGatePlanStatus.PENDING: CodeV8FStatus.READY_FOR_HARDWARE,
        HardwareGatePlanStatus.ACCEPTED: CodeV8FStatus.HARDWARE_ACCEPTED,
        HardwareGatePlanStatus.FAILED: CodeV8FStatus.HARDWARE_FAILED,
    }[hardware_gates.status]
    return CodeV8FAnalysis(
        schema_version=HARDWARE_GATE_SCHEMA_VERSION,
        status=status,
        request_sha256=request.analysis_sha256,
        v8e_analysis_sha256=v8e_analysis.analysis_sha256,
        factory_style=factory_style,
        wctd_models=wctd_models,
        hardware_gates=hardware_gates,
        warnings=tuple(dict.fromkeys(factory_style.warnings + wctd_models.warnings + hardware_gates.warnings)),
        blockers=(),
        reason=(
            "CODE V8-F hardware evidence accepted."
            if status is CodeV8FStatus.HARDWARE_ACCEPTED
            else "CODE V8-F materialized canonical models and retained explicit hardware-gate state."
        ),
    )


__all__ = [
    "HARDWARE_GATE_SCHEMA_VERSION",
    "CodeV8FAnalysis",
    "CodeV8FStatus",
    "HardwareGateEvidence",
    "HardwareGateKind",
    "HardwareGatePlan",
    "HardwareGatePlanStatus",
    "HardwareGateRequirement",
    "HardwareGateResult",
    "HardwareGateResultStatus",
    "build_code_v8f",
    "default_hardware_gate_requirements",
    "evaluate_hardware_gates",
]

# ---------------------------------------------------------------------------
# CODE V8-K real-artifact hardware campaign contracts.
# These additive contracts intentionally do not alter the historical V8-F API.
# ---------------------------------------------------------------------------

from pathlib import Path as _Path

from .code_v8j import CodeV8JAnalysis, CodeV8JStatus
from .package import WavetablePackage

V8K_HARDWARE_GATE_SCHEMA_VERSION = 1


class V8KHardwareGateStatus(str, Enum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"


class V8KHardwareStep(str, Enum):
    BACKUP_EVERYTHING = "backup_everything"
    BACKUP_ALL_WAVETABLES_WAVES = "backup_all_wavetables_waves"
    BACKUP_GLOBAL = "backup_global"
    INVENTORY_AND_EMPTY_SIGNATURE = "inventory_and_empty_signature"
    RESERVE_DESTINATIONS = "reserve_destinations"
    INSTALL_KNOWN_WAVES = "install_known_waves"
    INSTALL_DENSE_WCTD = "install_dense_wctd"
    INSTALL_SPARSE_WCTD = "install_sparse_wctd"
    EXACT_REDUMP = "exact_redump"
    INTERPOLATION_50_50 = "interpolation_50_50"
    INTERPOLATION_2_3_1_3 = "interpolation_2_3_1_3"
    BOUNDARIES_59_60_61_62_63 = "boundaries_59_60_61_62_63"
    INVALID_REFERENCES_SAFE_PROTOCOL = "invalid_references_safe_protocol"
    SLOW_SWEEP = "slow_sweep"
    FAST_SWEEP = "fast_sweep"
    ROUND_TRIP_SWEEP = "round_trip_sweep"
    DENSE_SPARSE_COMPARISON = "dense_sparse_comparison"
    EXACT_RESTORE_AND_FINAL_STATE = "exact_restore_and_final_state"


V8K_REQUIRED_HARDWARE_STEPS = tuple(V8KHardwareStep)


@dataclass(frozen=True, slots=True)
class V8KHardwareCampaignStepResult:
    step: V8KHardwareStep
    passed: bool
    evidence_paths: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.step, V8KHardwareStep):
            raise WavetableContractError("step must be V8KHardwareStep")
        if not isinstance(self.passed, bool):
            raise WavetableContractError("passed must be boolean")
        paths = tuple(self.evidence_paths)
        object.__setattr__(self, "evidence_paths", paths)
        if not paths or any(not isinstance(item, str) or not item or item.startswith(("/", "\\")) or ".." in _Path(item).parts for item in paths):
            raise WavetableContractError("hardware step evidence paths must be safe non-empty relative paths")
        if len(set(paths)) != len(paths):
            raise WavetableContractError("hardware step evidence paths must be unique")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "step": self.step.value,
            "passed": self.passed,
            "evidence_paths": list(self.evidence_paths),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class V8KHardwareArtifact:
    relative_path: str
    sha256: str
    byte_length: int

    def __post_init__(self) -> None:
        if not isinstance(self.relative_path, str) or not self.relative_path or self.relative_path.startswith(("/", "\\")) or ".." in _Path(self.relative_path).parts:
            raise WavetableContractError("artifact relative_path must be safe and relative")
        _sha256(self.sha256, name="artifact.sha256")
        if isinstance(self.byte_length, bool) or not isinstance(self.byte_length, int) or self.byte_length <= 0:
            raise WavetableContractError("artifact byte_length must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
        }


@dataclass(frozen=True, slots=True)
class V8KHardwareCampaignEvidence:
    schema_version: int
    campaign_id: str
    device_model: str
    os_version: str
    dense_package_sha256: str
    sparse_package_sha256: str
    inventory_sha256: str
    empty_signature_sha256: str | None
    manifest_sha256: str
    artifacts: tuple[V8KHardwareArtifact, ...]
    steps: tuple[V8KHardwareCampaignStepResult, ...]
    verified_from_files: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != V8K_HARDWARE_GATE_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-K hardware evidence schema version")
        for name in ("campaign_id", "device_model", "os_version", "reason"):
            _normalized(getattr(self, name), name=name)
        for name in ("dense_package_sha256", "sparse_package_sha256", "inventory_sha256", "manifest_sha256"):
            _sha256(getattr(self, name), name=name)
        if self.empty_signature_sha256 is not None:
            _sha256(self.empty_signature_sha256, name="empty_signature_sha256")
        artifacts = tuple(self.artifacts)
        steps = tuple(self.steps)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "steps", steps)
        if not artifacts or any(not isinstance(item, V8KHardwareArtifact) for item in artifacts):
            raise WavetableContractError("hardware evidence requires verified artifacts")
        if len({item.relative_path for item in artifacts}) != len(artifacts):
            raise WavetableContractError("hardware artifact paths must be unique")
        if tuple(item.step for item in steps) != V8K_REQUIRED_HARDWARE_STEPS:
            raise WavetableContractError("hardware evidence must contain all 18 steps in canonical order")
        artifact_paths = {item.relative_path for item in artifacts}
        if any(path not in artifact_paths for step in steps for path in step.evidence_paths):
            raise WavetableContractError("hardware step references an unverified artifact")
        if not isinstance(self.verified_from_files, bool) or not self.verified_from_files:
            raise WavetableContractError("hardware evidence must be loaded and verified from real files")

    @property
    def all_steps_passed(self) -> bool:
        return all(item.passed for item in self.steps)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "device_model": self.device_model,
            "os_version": self.os_version,
            "dense_package_sha256": self.dense_package_sha256,
            "sparse_package_sha256": self.sparse_package_sha256,
            "inventory_sha256": self.inventory_sha256,
            "empty_signature_sha256": self.empty_signature_sha256,
            "manifest_sha256": self.manifest_sha256,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "steps": [item.to_dict() for item in self.steps],
            "all_steps_passed": self.all_steps_passed,
            "verified_from_files": self.verified_from_files,
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
class V8KHardwareGatePlan:
    schema_version: int
    dense_package_sha256: str
    sparse_package_sha256: str
    inventory_sha256: str
    empty_signature_sha256: str | None
    required_steps: tuple[V8KHardwareStep, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != V8K_HARDWARE_GATE_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-K hardware plan schema version")
        for name in ("dense_package_sha256", "sparse_package_sha256", "inventory_sha256"):
            _sha256(getattr(self, name), name=name)
        if self.empty_signature_sha256 is not None:
            _sha256(self.empty_signature_sha256, name="empty_signature_sha256")
        steps = tuple(self.required_steps)
        object.__setattr__(self, "required_steps", steps)
        if steps != V8K_REQUIRED_HARDWARE_STEPS:
            raise WavetableContractError("V8-K plan requires the canonical 18-step campaign")
        _normalized(self.reason, name="reason")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dense_package_sha256": self.dense_package_sha256,
            "sparse_package_sha256": self.sparse_package_sha256,
            "inventory_sha256": self.inventory_sha256,
            "empty_signature_sha256": self.empty_signature_sha256,
            "required_steps": [item.value for item in self.required_steps],
            "hardware_evidence_required": True,
            "synthetic_passing_evidence_accepted": False,
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
class V8KHardwareGateReport:
    schema_version: int
    status: V8KHardwareGateStatus
    plan_sha256: str
    evidence_sha256: str | None
    passed_steps: tuple[V8KHardwareStep, ...]
    failed_steps: tuple[V8KHardwareStep, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    sparse_enabled: bool
    restore_exact_pass: bool
    v8_scope_status: str
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != V8K_HARDWARE_GATE_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-K hardware report schema version")
        if not isinstance(self.status, V8KHardwareGateStatus):
            raise WavetableContractError("status must be V8KHardwareGateStatus")
        _sha256(self.plan_sha256, name="plan_sha256")
        if self.evidence_sha256 is not None:
            _sha256(self.evidence_sha256, name="evidence_sha256")
        passed = tuple(self.passed_steps)
        failed = tuple(self.failed_steps)
        object.__setattr__(self, "passed_steps", passed)
        object.__setattr__(self, "failed_steps", failed)
        if len(set(passed + failed)) != len(passed) + len(failed):
            raise WavetableContractError("hardware report step sets must not overlap")
        if any(not isinstance(item, V8KHardwareStep) for item in passed + failed):
            raise WavetableContractError("hardware report steps must be V8KHardwareStep")
        object.__setattr__(self, "blockers", _entries(self.blockers, name="blockers"))
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        for name in ("sparse_enabled", "restore_exact_pass"):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        if self.status is V8KHardwareGateStatus.PASS:
            if self.blockers or failed or passed != V8K_REQUIRED_HARDWARE_STEPS:
                raise WavetableContractError("passing V8-K report requires all 18 steps and no blockers")
            if not self.sparse_enabled or not self.restore_exact_pass:
                raise WavetableContractError("passing V8-K report requires sparse enablement and exact restore")
            if self.v8_scope_status != "V8_SCOPE_PASS_V10_OPEN":
                raise WavetableContractError("passing V8-K report requires V8_SCOPE_PASS_V10_OPEN")
        elif self.status is V8KHardwareGateStatus.PENDING:
            if self.evidence_sha256 is not None or passed or failed or self.sparse_enabled or self.restore_exact_pass:
                raise WavetableContractError("pending V8-K report cannot claim evidence or passed gates")
        else:
            if not self.blockers or not failed or self.sparse_enabled:
                raise WavetableContractError("failed V8-K report requires blockers and failed steps")
        _normalized(self.v8_scope_status, name="v8_scope_status")
        _normalized(self.reason, name="reason")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "plan_sha256": self.plan_sha256,
            "evidence_sha256": self.evidence_sha256,
            "passed_steps": [item.value for item in self.passed_steps],
            "failed_steps": [item.value for item in self.failed_steps],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "sparse_enabled": self.sparse_enabled,
            "restore_exact_pass": self.restore_exact_pass,
            "v8_scope_status": self.v8_scope_status,
            "boundaries": {
                "real_artifact_campaign_required": True,
                "claims_v10_calibration_complete": False,
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


def load_v8k_hardware_campaign(directory: str | _Path) -> V8KHardwareCampaignEvidence:
    """Load a V8-K campaign only after verifying every referenced artifact file.

    The directory must contain ``campaign.json`` and all files listed in its
    ``artifacts`` array.  The loader hashes the actual bytes; an in-memory
    synthetic ``passed=True`` object is not accepted by the V8-K gate.
    """

    root = _Path(directory)
    manifest_path = root / "campaign.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        payload = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WavetableContractError(f"Unable to load V8-K hardware campaign: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise WavetableContractError("campaign.json must contain an object")
    if int(payload.get("schema_version", 0)) != V8K_HARDWARE_GATE_SCHEMA_VERSION:
        raise WavetableContractError("Unsupported campaign.json schema version")

    artifacts_payload = payload.get("artifacts")
    if not isinstance(artifacts_payload, list) or not artifacts_payload:
        raise WavetableContractError("campaign.json requires a non-empty artifacts list")
    artifacts: list[V8KHardwareArtifact] = []
    for item in artifacts_payload:
        if not isinstance(item, Mapping):
            raise WavetableContractError("campaign artifact must be an object")
        relative = str(item.get("path", ""))
        expected = str(item.get("sha256", ""))
        if not relative or relative.startswith(("/", "\\")) or ".." in _Path(relative).parts:
            raise WavetableContractError("campaign artifact path must be safe and relative")
        _sha256(expected, name="campaign artifact sha256")
        path = root / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise WavetableContractError(f"Unable to read campaign artifact {relative}: {exc}") from exc
        actual = sha256(data).hexdigest()
        if actual != expected:
            raise WavetableContractError(f"Campaign artifact hash mismatch for {relative}")
        artifacts.append(V8KHardwareArtifact(relative, actual, len(data)))

    steps_payload = payload.get("steps")
    if not isinstance(steps_payload, list):
        raise WavetableContractError("campaign.json requires a steps list")
    by_step: dict[V8KHardwareStep, V8KHardwareCampaignStepResult] = {}
    for item in steps_payload:
        if not isinstance(item, Mapping):
            raise WavetableContractError("campaign step must be an object")
        try:
            step = V8KHardwareStep(str(item.get("step", "")))
        except ValueError as exc:
            raise WavetableContractError(f"Unknown V8-K campaign step: {item.get('step')}") from exc
        if step in by_step:
            raise WavetableContractError("campaign steps must be unique")
        evidence_paths = item.get("evidence_paths")
        if not isinstance(evidence_paths, list):
            raise WavetableContractError("campaign step evidence_paths must be a list")
        passed = item.get("passed")
        if not isinstance(passed, bool):
            raise WavetableContractError("campaign step passed must be boolean")
        by_step[step] = V8KHardwareCampaignStepResult(
            step=step,
            passed=passed,
            evidence_paths=tuple(str(value) for value in evidence_paths),
            reason=str(item.get("reason", "")),
        )
    if set(by_step) != set(V8K_REQUIRED_HARDWARE_STEPS):
        missing = sorted(item.value for item in set(V8K_REQUIRED_HARDWARE_STEPS) - set(by_step))
        extra = sorted(item.value for item in set(by_step) - set(V8K_REQUIRED_HARDWARE_STEPS))
        raise WavetableContractError(f"campaign steps mismatch; missing={missing}, extra={extra}")

    empty_value = payload.get("empty_signature_sha256")
    empty_signature = None if empty_value is None else str(empty_value)
    return V8KHardwareCampaignEvidence(
        schema_version=V8K_HARDWARE_GATE_SCHEMA_VERSION,
        campaign_id=str(payload.get("campaign_id", "")),
        device_model=str(payload.get("device_model", "")),
        os_version=str(payload.get("os_version", "")),
        dense_package_sha256=str(payload.get("dense_package_sha256", "")),
        sparse_package_sha256=str(payload.get("sparse_package_sha256", "")),
        inventory_sha256=str(payload.get("inventory_sha256", "")),
        empty_signature_sha256=empty_signature,
        manifest_sha256=sha256(manifest_bytes).hexdigest(),
        artifacts=tuple(sorted(artifacts, key=lambda item: item.relative_path)),
        steps=tuple(by_step[item] for item in V8K_REQUIRED_HARDWARE_STEPS),
        verified_from_files=True,
        reason=str(payload.get("reason", "")),
    )


def create_v8k_hardware_gate_plan(
    dense_package: WavetablePackage,
    sparse_package: WavetablePackage,
    v8j_analysis: CodeV8JAnalysis,
) -> V8KHardwareGatePlan:
    if not isinstance(dense_package, WavetablePackage) or not isinstance(sparse_package, WavetablePackage):
        raise WavetableContractError("V8-K hardware plan requires dense and sparse WavetablePackage values")
    if not isinstance(v8j_analysis, CodeV8JAnalysis) or v8j_analysis.status is not CodeV8JStatus.COMPLETE:
        raise WavetableContractError("V8-K hardware plan requires complete V8-J analysis")
    if v8j_analysis.inventory is None:
        raise WavetableContractError("V8-J analysis lacks inventory")
    empty_signature_sha = (
        None
        if v8j_analysis.inventory.empty_wave_signature is None
        else v8j_analysis.inventory.empty_wave_signature.hardware_evidence_sha256
    )
    return V8KHardwareGatePlan(
        schema_version=V8K_HARDWARE_GATE_SCHEMA_VERSION,
        dense_package_sha256=dense_package.sha256,
        sparse_package_sha256=sparse_package.sha256,
        inventory_sha256=v8j_analysis.inventory.analysis_sha256,
        empty_signature_sha256=empty_signature_sha,
        required_steps=V8K_REQUIRED_HARDWARE_STEPS,
        reason="V8-K requires the canonical 18-step real-artifact campaign before enabling sparse WCTD or claiming hardware acceptance.",
    )


def evaluate_v8k_hardware_campaign(
    plan: V8KHardwareGatePlan,
    evidence: V8KHardwareCampaignEvidence | None = None,
) -> V8KHardwareGateReport:
    if not isinstance(plan, V8KHardwareGatePlan):
        raise WavetableContractError("plan must be V8KHardwareGatePlan")
    if evidence is None:
        return V8KHardwareGateReport(
            schema_version=V8K_HARDWARE_GATE_SCHEMA_VERSION,
            status=V8KHardwareGateStatus.PENDING,
            plan_sha256=plan.analysis_sha256,
            evidence_sha256=None,
            passed_steps=(),
            failed_steps=(),
            blockers=(),
            warnings=("Real V8-K hardware campaign is not mounted; dense remains the only enabled mode.",),
            sparse_enabled=False,
            restore_exact_pass=False,
            v8_scope_status="PENDING_REAL_HARDWARE",
            reason="V8-K software materialization is ready, but no hardware acceptance is claimed.",
        )
    if not isinstance(evidence, V8KHardwareCampaignEvidence) or not evidence.verified_from_files:
        raise WavetableContractError("V8-K accepts only evidence verified from artifact files")

    blockers: list[str] = []
    if evidence.dense_package_sha256 != plan.dense_package_sha256:
        blockers.append("Dense package SHA-256 does not match the hardware plan.")
    if evidence.sparse_package_sha256 != plan.sparse_package_sha256:
        blockers.append("Sparse package SHA-256 does not match the hardware plan.")
    if evidence.inventory_sha256 != plan.inventory_sha256:
        blockers.append("Inventory SHA-256 does not match the hardware plan.")
    if evidence.empty_signature_sha256 != plan.empty_signature_sha256:
        blockers.append("Validated empty-wave signature does not match the hardware plan.")
    failed = tuple(item.step for item in evidence.steps if not item.passed)
    if failed:
        blockers.extend(f"Hardware step failed: {item.value}" for item in failed)
    passed = tuple(item.step for item in evidence.steps if item.passed)
    restore_pass = V8KHardwareStep.EXACT_RESTORE_AND_FINAL_STATE in passed

    if blockers:
        reported_failed = failed or (V8KHardwareStep.EXACT_REDUMP,)
        reported_passed = tuple(item for item in passed if item not in reported_failed)
        return V8KHardwareGateReport(
            schema_version=V8K_HARDWARE_GATE_SCHEMA_VERSION,
            status=V8KHardwareGateStatus.FAIL,
            plan_sha256=plan.analysis_sha256,
            evidence_sha256=evidence.analysis_sha256,
            passed_steps=reported_passed,
            failed_steps=reported_failed,
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=(),
            sparse_enabled=False,
            restore_exact_pass=restore_pass,
            v8_scope_status="HARDWARE_CAMPAIGN_FAILED",
            reason="V8-K hardware campaign failed or does not match the generated packages.",
        )
    return V8KHardwareGateReport(
        schema_version=V8K_HARDWARE_GATE_SCHEMA_VERSION,
        status=V8KHardwareGateStatus.PASS,
        plan_sha256=plan.analysis_sha256,
        evidence_sha256=evidence.analysis_sha256,
        passed_steps=V8K_REQUIRED_HARDWARE_STEPS,
        failed_steps=(),
        blockers=(),
        warnings=("V10 calibration and complete hardware emulation remain open.",),
        sparse_enabled=True,
        restore_exact_pass=True,
        v8_scope_status="V8_SCOPE_PASS_V10_OPEN",
        reason="All 18 real-artifact V8-K hardware steps passed, including exact restore and dense/sparse comparison.",
    )


__all__ += [
    "V8K_HARDWARE_GATE_SCHEMA_VERSION",
    "V8KHardwareGateStatus",
    "V8KHardwareStep",
    "V8K_REQUIRED_HARDWARE_STEPS",
    "V8KHardwareCampaignStepResult",
    "V8KHardwareArtifact",
    "V8KHardwareCampaignEvidence",
    "V8KHardwareGatePlan",
    "V8KHardwareGateReport",
    "load_v8k_hardware_campaign",
    "create_v8k_hardware_gate_plan",
    "evaluate_v8k_hardware_campaign",
]
