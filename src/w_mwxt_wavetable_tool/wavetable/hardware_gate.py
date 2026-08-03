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
