from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from importlib.resources import files
import json
import re
from typing import Any, Mapping, Sequence

from ..version import __version__
from .models import (
    ComplianceFormatError,
    ComplianceRegistry,
    RequirementScope,
    canonical_json_bytes,
)
from .registry import load_compliance_registry


PRE_V8_CLOSURE_ID = "w-mwxt-pre-v8-closure"
PRE_V8_CLOSURE_SCHEMA_VERSION = 1
PRE_V8_SOURCE_CHAIN_SCHEMA_VERSION = 1
PRE_V8_DECISION_PLAN_SCHEMA_VERSION = 1
CODE_V8_PREFLIGHT_SCHEMA_VERSION = 1
PRE_V8_CLOSURE_RESOURCE = "data/pre_v8_closure_v1.json"
PRE_V8_DESTINATION_PREFIX = "V8-0"
EXPECTED_PRE_V8_REQUIREMENT_COUNT = 62

_REQUIREMENT_ID_RE = re.compile(r"^CDC-[A-Z0-9]+-[0-9]{3}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PreV8LinkError(ValueError):
    """Raised when a pre-V8 component link or readiness invariant is invalid."""


class ClosureStage(str, Enum):
    CODE_V6 = "CODE V6"
    CODE_V8_0B = "CODE V8-0B"
    CODE_V8_0C = "CODE V8-0C"
    CODE_V8_0D = "CODE V8-0D"
    CODE_V8_0E = "CODE V8-0E"
    CODE_V8_0F = "CODE V8-0F"


class ClosureSupport(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    ABSENT = "absent"


class PreV8ReadinessStatus(str, Enum):
    READY = "ready"
    REJECTED = "rejected"


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ComplianceFormatError(f"{label} must be a JSON object")
    return value


def _require_sequence(value: object, *, label: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ComplianceFormatError(f"{label} must be a JSON array")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], *, expected: set[str], label: str
) -> None:
    actual = set(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append(f"missing={missing}")
    if extra:
        details.append(f"extra={extra}")
    raise ComplianceFormatError(f"{label} fields are invalid: {', '.join(details)}")


def _require_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ComplianceFormatError(f"{label} must be a non-empty normalized string")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    result = _require_string(value, label=label)
    if not _SHA256_RE.fullmatch(result):
        raise ComplianceFormatError(f"{label} must be a lowercase SHA-256 digest")
    return result


def _require_runtime_hash(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PreV8LinkError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


def _normalized_strings(value: Sequence[object], *, label: str) -> tuple[str, ...]:
    result = tuple(_require_string(item, label=label) for item in value)
    if not result:
        raise ComplianceFormatError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise ComplianceFormatError(f"{label} must not contain duplicates")
    return result


def _attribute(value: object, name: str, *, label: str) -> Any:
    if not hasattr(value, name):
        raise PreV8LinkError(f"{label} does not expose {name}")
    return getattr(value, name)


def _analysis_hash(value: object, *, label: str) -> str:
    return _require_runtime_hash(
        _attribute(value, "analysis_sha256", label=label),
        label=f"{label}.analysis_sha256",
    )


@dataclass(frozen=True, slots=True)
class RequirementClosureEvidence:
    requirement_id: str
    stage: ClosureStage
    support: ClosureSupport
    modules: tuple[str, ...]
    tests: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not _REQUIREMENT_ID_RE.fullmatch(self.requirement_id):
            raise ComplianceFormatError(
                f"Invalid closure requirement ID: {self.requirement_id!r}"
            )
        if not self.modules or any(
            not item or item.strip() != item for item in self.modules
        ):
            raise ComplianceFormatError("closure modules must be normalized and non-empty")
        if len(set(self.modules)) != len(self.modules):
            raise ComplianceFormatError("closure modules must be unique")
        if not self.tests or any(not item or item.strip() != item for item in self.tests):
            raise ComplianceFormatError("closure tests must be normalized and non-empty")
        if len(set(self.tests)) != len(self.tests):
            raise ComplianceFormatError("closure tests must be unique")
        if not self.reason or self.reason.strip() != self.reason:
            raise ComplianceFormatError("closure reason must be normalized and non-empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "requirement_id": self.requirement_id,
            "stage": self.stage.value,
            "support": self.support.value,
            "modules": list(self.modules),
            "tests": list(self.tests),
            "reason": self.reason,
        }

    @property
    def evidence_sha256(self) -> str:
        return _canonical_hash(self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> RequirementClosureEvidence:
        payload = _require_mapping(value, label="closure evidence")
        _require_exact_keys(
            payload,
            expected={
                "requirement_id",
                "stage",
                "support",
                "modules",
                "tests",
                "reason",
            },
            label="closure evidence",
        )
        try:
            stage = ClosureStage(_require_string(payload["stage"], label="stage"))
            support = ClosureSupport(
                _require_string(payload["support"], label="support")
            )
        except ValueError as exc:
            raise ComplianceFormatError("Unsupported closure enum value") from exc
        return cls(
            requirement_id=_require_string(
                payload["requirement_id"], label="requirement_id"
            ),
            stage=stage,
            support=support,
            modules=_normalized_strings(
                _require_sequence(payload["modules"], label="modules"),
                label="modules entry",
            ),
            tests=_normalized_strings(
                _require_sequence(payload["tests"], label="tests"),
                label="tests entry",
            ),
            reason=_require_string(payload["reason"], label="reason"),
        )


@dataclass(frozen=True, slots=True)
class PreV8ComplianceClosure:
    closure_id: str
    schema_version: int
    baseline_registry_sha256: str
    requirement_destination_prefix: str
    evidence: tuple[RequirementClosureEvidence, ...]
    closure_sha256: str

    def __post_init__(self) -> None:
        if self.closure_id != PRE_V8_CLOSURE_ID:
            raise ComplianceFormatError(f"closure_id must be {PRE_V8_CLOSURE_ID!r}")
        if self.schema_version != PRE_V8_CLOSURE_SCHEMA_VERSION:
            raise ComplianceFormatError("Unsupported pre-V8 closure schema version")
        _require_sha256(
            self.baseline_registry_sha256, label="baseline_registry_sha256"
        )
        if self.requirement_destination_prefix != PRE_V8_DESTINATION_PREFIX:
            raise ComplianceFormatError(
                f"requirement_destination_prefix must be {PRE_V8_DESTINATION_PREFIX!r}"
            )
        if len(self.evidence) != EXPECTED_PRE_V8_REQUIREMENT_COUNT:
            raise ComplianceFormatError(
                "Pre-V8 closure must contain exactly "
                f"{EXPECTED_PRE_V8_REQUIREMENT_COUNT} evidence records"
            )
        ids = tuple(item.requirement_id for item in self.evidence)
        if len(set(ids)) != len(ids):
            raise ComplianceFormatError("Pre-V8 closure requirement IDs must be unique")
        _require_sha256(self.closure_sha256, label="closure_sha256")
        if self.closure_sha256 != self.compute_sha256():
            raise ComplianceFormatError("Pre-V8 closure SHA-256 mismatch")

    @property
    def requirement_ids(self) -> tuple[str, ...]:
        return tuple(item.requirement_id for item in self.evidence)

    @property
    def supported_count(self) -> int:
        return sum(item.support is ClosureSupport.SUPPORTED for item in self.evidence)

    @property
    def debt_requirement_ids(self) -> tuple[str, ...]:
        return tuple(
            item.requirement_id
            for item in self.evidence
            if item.support is not ClosureSupport.SUPPORTED
        )

    @property
    def zero_required_debt(self) -> bool:
        return not self.debt_requirement_ids

    def _content_dict(self) -> dict[str, object]:
        return {
            "closure_id": self.closure_id,
            "schema_version": self.schema_version,
            "baseline_registry_sha256": self.baseline_registry_sha256,
            "requirement_destination_prefix": self.requirement_destination_prefix,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    def compute_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["required_count"] = len(self.evidence)
        result["supported_count"] = self.supported_count
        result["debt_requirement_ids"] = list(self.debt_requirement_ids)
        result["zero_required_debt"] = self.zero_required_debt
        result["evidence_sha256"] = [item.evidence_sha256 for item in self.evidence]
        result["closure_sha256"] = self.closure_sha256
        return result

    def validate_against_registry(self, registry: ComplianceRegistry) -> None:
        if registry.registry_sha256 != self.baseline_registry_sha256:
            raise ComplianceFormatError(
                "Pre-V8 closure baseline does not match the executable registry"
            )
        expected = tuple(
            item.id
            for item in registry.requirements
            if item.active
            and item.destination.startswith(self.requirement_destination_prefix)
        )
        if self.requirement_ids != expected:
            missing = sorted(set(expected) - set(self.requirement_ids))
            extra = sorted(set(self.requirement_ids) - set(expected))
            raise ComplianceFormatError(
                f"Pre-V8 closure coverage mismatch. Missing={missing!r} Extra={extra!r}"
            )
        if len(expected) != EXPECTED_PRE_V8_REQUIREMENT_COUNT:
            raise ComplianceFormatError(
                "Executable registry pre-V8 requirement count changed unexpectedly"
            )
        if not self.zero_required_debt:
            raise ComplianceFormatError(
                f"Pre-V8 required debt remains: {self.debt_requirement_ids!r}"
            )
        if any(
            registry.requirement(item.requirement_id).scope
            in {RequirementScope.EXCLUDED, RequirementScope.POST_PROTOTYPE}
            for item in self.evidence
        ):
            raise ComplianceFormatError(
                "Pre-V8 closure must not claim excluded or post-prototype requirements"
            )
        taxonomy = next(
            item for item in self.evidence if item.requirement_id == "CDC-CLS-001"
        )
        if "27" not in taxonomy.reason or "correct" not in taxonomy.reason.lower():
            raise ComplianceFormatError(
                "CDC-CLS-001 closure must record the canonical 27-class correction"
            )

    @classmethod
    def from_dict(cls, value: object) -> PreV8ComplianceClosure:
        payload = _require_mapping(value, label="pre-V8 closure")
        _require_exact_keys(
            payload,
            expected={
                "closure_id",
                "schema_version",
                "baseline_registry_sha256",
                "requirement_destination_prefix",
                "evidence",
                "closure_sha256",
            },
            label="pre-V8 closure",
        )
        schema_version = payload["schema_version"]
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise ComplianceFormatError("schema_version must be an integer")
        evidence = tuple(
            RequirementClosureEvidence.from_dict(item)
            for item in _require_sequence(payload["evidence"], label="evidence")
        )
        return cls(
            closure_id=_require_string(payload["closure_id"], label="closure_id"),
            schema_version=schema_version,
            baseline_registry_sha256=_require_sha256(
                payload["baseline_registry_sha256"],
                label="baseline_registry_sha256",
            ),
            requirement_destination_prefix=_require_string(
                payload["requirement_destination_prefix"],
                label="requirement_destination_prefix",
            ),
            evidence=evidence,
            closure_sha256=_require_sha256(
                payload["closure_sha256"], label="closure_sha256"
            ),
        )


def load_pre_v8_compliance_closure(
    registry: ComplianceRegistry | None = None,
) -> PreV8ComplianceClosure:
    selected_registry = load_compliance_registry() if registry is None else registry
    resource = files(__package__).joinpath("data").joinpath("pre_v8_closure_v1.json")
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComplianceFormatError(f"Cannot load bundled pre-V8 closure: {exc}") from exc
    closure = PreV8ComplianceClosure.from_dict(payload)
    closure.validate_against_registry(selected_registry)
    return closure


def assert_zero_pre_v8_debt(
    registry: ComplianceRegistry | None = None,
    closure: PreV8ComplianceClosure | None = None,
) -> PreV8ComplianceClosure:
    selected_registry = load_compliance_registry() if registry is None else registry
    selected_closure = (
        load_pre_v8_compliance_closure(selected_registry)
        if closure is None
        else closure
    )
    selected_closure.validate_against_registry(selected_registry)
    if not selected_closure.zero_required_debt:
        raise ComplianceFormatError(
            f"Pre-V8 required debt remains: {selected_closure.debt_requirement_ids!r}"
        )
    return selected_closure


@dataclass(frozen=True, slots=True)
class PreV8SourceChain:
    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    imported_state_sha256: str
    signal_analysis_sha256: str
    code_v5_analysis_sha256: str
    code_v6_analysis_sha256: str
    reconstructed_wave_set_sha256: str
    xt_projection_set_sha256: str
    xt_trajectory_sha256: str | None
    xt_qc_sha256: str | None
    xt_hardware_package_sha256: str | None

    def __post_init__(self) -> None:
        if self.schema_version != PRE_V8_SOURCE_CHAIN_SCHEMA_VERSION:
            raise PreV8LinkError("Unsupported pre-V8 source-chain schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise PreV8LinkError("tool_version must be normalized and non-empty")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise PreV8LinkError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "imported_state_sha256",
            "signal_analysis_sha256",
            "code_v5_analysis_sha256",
            "code_v6_analysis_sha256",
            "reconstructed_wave_set_sha256",
            "xt_projection_set_sha256",
        ):
            _require_runtime_hash(getattr(self, name), label=name)
        for name in (
            "xt_trajectory_sha256",
            "xt_qc_sha256",
            "xt_hardware_package_sha256",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_runtime_hash(value, label=name)
        if self.xt_qc_sha256 is not None and self.xt_trajectory_sha256 is None:
            raise PreV8LinkError("XT QC evidence requires an XT trajectory link")
        if self.xt_hardware_package_sha256 is not None and self.xt_qc_sha256 is None:
            raise PreV8LinkError("XT hardware package evidence requires an XT QC link")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "imported_state_sha256": self.imported_state_sha256,
            "signal_analysis_sha256": self.signal_analysis_sha256,
            "code_v5_analysis_sha256": self.code_v5_analysis_sha256,
            "code_v6_analysis_sha256": self.code_v6_analysis_sha256,
            "reconstructed_wave_set_sha256": self.reconstructed_wave_set_sha256,
            "xt_projection_set_sha256": self.xt_projection_set_sha256,
            "xt_trajectory_sha256": self.xt_trajectory_sha256,
            "xt_qc_sha256": self.xt_qc_sha256,
            "xt_hardware_package_sha256": self.xt_hardware_package_sha256,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class PreV8DecisionPlan:
    schema_version: int
    sample_rate: int
    sample_count: int
    sample_sha256: str
    signal_extension_analysis_sha256: str
    behavior_classification_sha256: str
    region_interest_analysis_sha256: str
    formant_analysis_sha256: str
    spectral_evolution_analysis_sha256: str
    perceptual_feature_sha256: str
    musical_classification_sha256: str
    mode_decision_sha256: str
    profile_selection_sha256: str
    xt_wave_set_optimization_sha256: str
    auto_repair_sequence_sha256: str
    mode_status: str
    selected_mode: str | None
    selected_profile: str
    optimized_wave_count: int
    repaired_wave_count: int
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != PRE_V8_DECISION_PLAN_SCHEMA_VERSION:
            raise PreV8LinkError("Unsupported pre-V8 decision-plan schema version")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise PreV8LinkError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "signal_extension_analysis_sha256",
            "behavior_classification_sha256",
            "region_interest_analysis_sha256",
            "formant_analysis_sha256",
            "spectral_evolution_analysis_sha256",
            "perceptual_feature_sha256",
            "musical_classification_sha256",
            "mode_decision_sha256",
            "profile_selection_sha256",
            "xt_wave_set_optimization_sha256",
            "auto_repair_sequence_sha256",
        ):
            _require_runtime_hash(getattr(self, name), label=name)
        if self.mode_status not in {"selected", "overridden", "rejected"}:
            raise PreV8LinkError("mode_status is invalid")
        if self.mode_status == "rejected":
            if self.selected_mode is not None:
                raise PreV8LinkError("rejected mode plans must not select a mode")
        elif not self.selected_mode:
            raise PreV8LinkError("accepted mode plans require selected_mode")
        if not self.selected_profile or self.selected_profile.strip() != self.selected_profile:
            raise PreV8LinkError("selected_profile must be normalized and non-empty")
        if self.optimized_wave_count <= 0 or self.repaired_wave_count <= 0:
            raise PreV8LinkError("wave counts must be positive")
        if self.optimized_wave_count != self.repaired_wave_count:
            raise PreV8LinkError("optimized and repaired wave counts must match")
        if any(not item or item.strip() != item for item in self.warnings):
            raise PreV8LinkError("warnings must contain normalized entries")

    @property
    def ready_for_v8(self) -> bool:
        return self.mode_status != "rejected"

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "signal_extension_analysis_sha256": self.signal_extension_analysis_sha256,
            "behavior_classification_sha256": self.behavior_classification_sha256,
            "region_interest_analysis_sha256": self.region_interest_analysis_sha256,
            "formant_analysis_sha256": self.formant_analysis_sha256,
            "spectral_evolution_analysis_sha256": self.spectral_evolution_analysis_sha256,
            "perceptual_feature_sha256": self.perceptual_feature_sha256,
            "musical_classification_sha256": self.musical_classification_sha256,
            "mode_decision_sha256": self.mode_decision_sha256,
            "profile_selection_sha256": self.profile_selection_sha256,
            "xt_wave_set_optimization_sha256": self.xt_wave_set_optimization_sha256,
            "auto_repair_sequence_sha256": self.auto_repair_sequence_sha256,
            "mode_status": self.mode_status,
            "selected_mode": self.selected_mode,
            "selected_profile": self.selected_profile,
            "optimized_wave_count": self.optimized_wave_count,
            "repaired_wave_count": self.repaired_wave_count,
            "warnings": list(self.warnings),
            "ready_for_v8": self.ready_for_v8,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class CodeV8PreflightAnalysis:
    schema_version: int
    tool_version: str
    source_chain: PreV8SourceChain
    decision_plan: PreV8DecisionPlan
    compliance_closure: PreV8ComplianceClosure
    status: PreV8ReadinessStatus
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8_PREFLIGHT_SCHEMA_VERSION:
            raise PreV8LinkError("Unsupported CODE V8 preflight schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise PreV8LinkError("tool_version must be normalized and non-empty")
        if not self.compliance_closure.zero_required_debt:
            raise PreV8LinkError("CODE V8 preflight requires zero pre-V8 debt")
        if (
            self.source_chain.sample_rate != self.decision_plan.sample_rate
            or self.source_chain.sample_count != self.decision_plan.sample_count
            or self.source_chain.sample_sha256 != self.decision_plan.sample_sha256
        ):
            raise PreV8LinkError("source chain and decision plan sample identity disagree")
        if self.status is PreV8ReadinessStatus.READY:
            if self.blockers or not self.decision_plan.ready_for_v8:
                raise PreV8LinkError("ready preflight cannot contain blockers")
        else:
            if not self.blockers or self.decision_plan.ready_for_v8:
                raise PreV8LinkError("rejected preflight requires explicit blockers")
        if any(not item or item.strip() != item for item in self.blockers):
            raise PreV8LinkError("blockers must contain normalized entries")
        if not self.reason or self.reason.strip() != self.reason:
            raise PreV8LinkError("reason must be normalized and non-empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "source_chain": self.source_chain.to_dict(),
            "decision_plan": self.decision_plan.to_dict(),
            "compliance_closure": self.compliance_closure.to_dict(),
            "status": self.status.value,
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "builds_wavetable": False,
                "allocates_xt_memory": False,
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

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"


def assemble_pre_v8_source_chain(
    audio_source: object,
    code_v6_analysis: object,
    xt_projection_set: object,
    *,
    xt_trajectory: object | None = None,
    xt_qc: object | None = None,
    xt_hardware_package: object | None = None,
    tool_version: str = __version__,
) -> PreV8SourceChain:
    sample_rate = int(_attribute(_attribute(audio_source, "metadata", label="audio_source"), "sample_rate", label="audio_source.metadata"))
    mono_samples = _attribute(audio_source, "mono_samples", label="audio_source")
    sample_count = int(getattr(mono_samples, "size", len(mono_samples)))
    sample_sha256 = _require_runtime_hash(
        _attribute(audio_source, "sample_sha256", label="audio_source"),
        label="audio_source.sample_sha256",
    )
    imported_state_sha256 = _require_runtime_hash(
        _attribute(audio_source, "state_sha256", label="audio_source"),
        label="audio_source.state_sha256",
    )

    if int(_attribute(code_v6_analysis, "sample_rate", label="code_v6_analysis")) != sample_rate:
        raise PreV8LinkError("V3 and V6 sample rates disagree")
    if int(_attribute(code_v6_analysis, "sample_count", label="code_v6_analysis")) != sample_count:
        raise PreV8LinkError("V3 and V6 sample counts disagree")
    if _attribute(code_v6_analysis, "sample_sha256", label="code_v6_analysis") != sample_sha256:
        raise PreV8LinkError("V3 and V6 sample hashes disagree")

    code_v5 = _attribute(code_v6_analysis, "code_v5_analysis", label="code_v6_analysis")
    signal = _attribute(code_v5, "signal_analysis", label="code_v5_analysis")
    signal_hash = _analysis_hash(signal, label="signal_analysis")
    code_v5_hash = _analysis_hash(code_v5, label="code_v5_analysis")
    code_v6_hash = _analysis_hash(code_v6_analysis, label="code_v6_analysis")
    reconstructed = _attribute(
        code_v6_analysis, "reconstructed_wave_set", label="code_v6_analysis"
    )
    reconstructed_hash = _analysis_hash(
        reconstructed, label="reconstructed_wave_set"
    )
    projection_hash = _analysis_hash(xt_projection_set, label="xt_projection_set")

    if (
        _attribute(
            xt_projection_set,
            "source_code_v6_analysis_sha256",
            label="xt_projection_set",
        )
        != code_v6_hash
    ):
        raise PreV8LinkError("V7 projection does not link to the supplied V6 aggregate")
    if (
        _attribute(
            xt_projection_set,
            "source_reconstructed_wave_set_sha256",
            label="xt_projection_set",
        )
        != reconstructed_hash
    ):
        raise PreV8LinkError(
            "V7 projection does not link to the supplied reconstructed-wave set"
        )

    trajectory_hash: str | None = None
    qc_hash: str | None = None
    package_hash: str | None = None
    if xt_trajectory is not None:
        trajectory_hash = _analysis_hash(xt_trajectory, label="xt_trajectory")
        if (
            _attribute(
                xt_trajectory,
                "source_projection_set_sha256",
                label="xt_trajectory",
            )
            != projection_hash
        ):
            raise PreV8LinkError("XT trajectory does not link to the projection set")
        if (
            _attribute(
                xt_trajectory,
                "source_reconstructed_wave_set_sha256",
                label="xt_trajectory",
            )
            != reconstructed_hash
        ):
            raise PreV8LinkError(
                "XT trajectory does not link to the reconstructed-wave set"
            )
    if xt_qc is not None:
        if xt_trajectory is None:
            raise PreV8LinkError("XT QC cannot be supplied without a trajectory")
        qc_hash = _analysis_hash(xt_qc, label="xt_qc")
        if _attribute(xt_qc, "source_trajectory_sha256", label="xt_qc") != trajectory_hash:
            raise PreV8LinkError("XT QC does not link to the supplied trajectory")
        if _attribute(xt_qc, "source_projection_set_sha256", label="xt_qc") != projection_hash:
            raise PreV8LinkError("XT QC does not link to the projection set")
    if xt_hardware_package is not None:
        if xt_trajectory is None or xt_qc is None:
            raise PreV8LinkError(
                "XT hardware package cannot be supplied without trajectory and QC"
            )
        package_hash = _analysis_hash(
            xt_hardware_package, label="xt_hardware_package"
        )
        if (
            _attribute(
                xt_hardware_package,
                "source_trajectory_sha256",
                label="xt_hardware_package",
            )
            != trajectory_hash
        ):
            raise PreV8LinkError("XT package does not link to the supplied trajectory")
        if (
            _attribute(
                xt_hardware_package,
                "source_qc_sha256",
                label="xt_hardware_package",
            )
            != qc_hash
        ):
            raise PreV8LinkError("XT package does not link to the supplied QC")
        if (
            _attribute(
                xt_hardware_package,
                "source_projection_set_sha256",
                label="xt_hardware_package",
            )
            != projection_hash
        ):
            raise PreV8LinkError("XT package does not link to the projection set")

    return PreV8SourceChain(
        schema_version=PRE_V8_SOURCE_CHAIN_SCHEMA_VERSION,
        tool_version=tool_version,
        sample_rate=sample_rate,
        sample_count=sample_count,
        sample_sha256=sample_sha256,
        imported_state_sha256=imported_state_sha256,
        signal_analysis_sha256=signal_hash,
        code_v5_analysis_sha256=code_v5_hash,
        code_v6_analysis_sha256=code_v6_hash,
        reconstructed_wave_set_sha256=reconstructed_hash,
        xt_projection_set_sha256=projection_hash,
        xt_trajectory_sha256=trajectory_hash,
        xt_qc_sha256=qc_hash,
        xt_hardware_package_sha256=package_hash,
    )


def assemble_pre_v8_decision_plan(
    code_v6_analysis: object,
    signal_extension: object,
    behavior_classification: object,
    region_interest: object,
    formant_analysis: object,
    spectral_evolution: object,
    perceptual_features: object,
    musical_classification: object,
    mode_decision: object,
    profile_selection: object,
    xt_wave_set_optimization: object,
    auto_repair_sequence: object,
) -> PreV8DecisionPlan:
    sample_rate = int(_attribute(code_v6_analysis, "sample_rate", label="code_v6_analysis"))
    sample_count = int(_attribute(code_v6_analysis, "sample_count", label="code_v6_analysis"))
    sample_sha256 = _require_runtime_hash(
        _attribute(code_v6_analysis, "sample_sha256", label="code_v6_analysis"),
        label="code_v6_analysis.sample_sha256",
    )
    code_v5 = _attribute(code_v6_analysis, "code_v5_analysis", label="code_v6_analysis")
    signal = _attribute(code_v5, "signal_analysis", label="code_v5_analysis")
    spectral = _attribute(code_v5, "spectral_analysis", label="code_v5_analysis")
    harmonic = _attribute(
        code_v5, "harmonic_perceptual_analysis", label="code_v5_analysis"
    )
    segmentation = _attribute(
        code_v6_analysis, "segmentation_analysis", label="code_v6_analysis"
    )
    signal_hash = _analysis_hash(signal, label="signal_analysis")
    spectral_hash = _analysis_hash(spectral, label="spectral_analysis")
    harmonic_hash = _analysis_hash(harmonic, label="harmonic_perceptual_analysis")
    segmentation_hash = _analysis_hash(segmentation, label="segmentation_analysis")

    def check_identity(component: object, label: str) -> None:
        if int(_attribute(component, "sample_rate", label=label)) != sample_rate:
            raise PreV8LinkError(f"{label} sample rate disagrees with V6")
        if int(_attribute(component, "sample_count", label=label)) != sample_count:
            raise PreV8LinkError(f"{label} sample count disagrees with V6")
        if _attribute(component, "sample_sha256", label=label) != sample_sha256:
            raise PreV8LinkError(f"{label} sample hash disagrees with V6")

    for component, label in (
        (signal_extension, "signal_extension"),
        (behavior_classification, "behavior_classification"),
        (region_interest, "region_interest"),
        (formant_analysis, "formant_analysis"),
        (spectral_evolution, "spectral_evolution"),
        (perceptual_features, "perceptual_features"),
        (musical_classification, "musical_classification"),
        (mode_decision, "mode_decision"),
    ):
        check_identity(component, label)

    extension_hash = _analysis_hash(signal_extension, label="signal_extension")
    behavior_hash = _analysis_hash(
        behavior_classification, label="behavior_classification"
    )
    region_hash = _analysis_hash(region_interest, label="region_interest")
    formant_hash = _analysis_hash(formant_analysis, label="formant_analysis")
    evolution_hash = _analysis_hash(spectral_evolution, label="spectral_evolution")
    perceptual_hash = _analysis_hash(perceptual_features, label="perceptual_features")
    musical_hash = _analysis_hash(
        musical_classification, label="musical_classification"
    )
    mode_hash = _analysis_hash(mode_decision, label="mode_decision")
    profile_hash = _analysis_hash(profile_selection, label="profile_selection")
    optimization_hash = _analysis_hash(
        xt_wave_set_optimization, label="xt_wave_set_optimization"
    )
    repair_hash = _analysis_hash(auto_repair_sequence, label="auto_repair_sequence")

    expected_links = (
        (
            _attribute(
                signal_extension,
                "signal_analysis_sha256",
                label="signal_extension",
            ),
            signal_hash,
            "signal extension -> signal",
        ),
        (
            _attribute(
                behavior_classification,
                "signal_analysis_sha256",
                label="behavior_classification",
            ),
            signal_hash,
            "behavior -> signal",
        ),
        (
            _attribute(
                behavior_classification,
                "signal_extension_analysis_sha256",
                label="behavior_classification",
            ),
            extension_hash,
            "behavior -> signal extension",
        ),
        (
            _attribute(
                region_interest,
                "signal_analysis_sha256",
                label="region_interest",
            ),
            signal_hash,
            "regions -> signal",
        ),
        (
            _attribute(
                region_interest,
                "signal_extension_analysis_sha256",
                label="region_interest",
            ),
            extension_hash,
            "regions -> signal extension",
        ),
        (
            _attribute(
                region_interest,
                "segmentation_analysis_sha256",
                label="region_interest",
            ),
            segmentation_hash,
            "regions -> segmentation",
        ),
        (
            _attribute(
                formant_analysis,
                "spectral_analysis_sha256",
                label="formant_analysis",
            ),
            spectral_hash,
            "formants -> spectral",
        ),
        (
            _attribute(
                spectral_evolution,
                "spectral_analysis_sha256",
                label="spectral_evolution",
            ),
            spectral_hash,
            "spectral evolution -> spectral",
        ),
        (
            _attribute(
                spectral_evolution,
                "harmonic_perceptual_analysis_sha256",
                label="spectral_evolution",
            ),
            harmonic_hash,
            "spectral evolution -> harmonic",
        ),
        (
            _attribute(
                perceptual_features,
                "signal_analysis_sha256",
                label="perceptual_features",
            ),
            signal_hash,
            "perceptual -> signal",
        ),
        (
            _attribute(
                perceptual_features,
                "signal_extension_analysis_sha256",
                label="perceptual_features",
            ),
            extension_hash,
            "perceptual -> signal extension",
        ),
        (
            _attribute(
                perceptual_features,
                "spectral_analysis_sha256",
                label="perceptual_features",
            ),
            spectral_hash,
            "perceptual -> spectral",
        ),
        (
            _attribute(
                perceptual_features,
                "harmonic_perceptual_analysis_sha256",
                label="perceptual_features",
            ),
            harmonic_hash,
            "perceptual -> harmonic",
        ),
        (
            _attribute(
                perceptual_features,
                "spectral_evolution_analysis_sha256",
                label="perceptual_features",
            ),
            evolution_hash,
            "perceptual -> spectral evolution",
        ),
        (
            _attribute(
                perceptual_features,
                "formant_analysis_sha256",
                label="perceptual_features",
            ),
            formant_hash,
            "perceptual -> formants",
        ),
        (
            _attribute(
                musical_classification,
                "behavior_classification_sha256",
                label="musical_classification",
            ),
            behavior_hash,
            "musical -> behavior",
        ),
        (
            _attribute(
                musical_classification,
                "perceptual_feature_sha256",
                label="musical_classification",
            ),
            perceptual_hash,
            "musical -> perceptual",
        ),
        (
            _attribute(
                musical_classification,
                "formant_analysis_sha256",
                label="musical_classification",
            ),
            formant_hash,
            "musical -> formants",
        ),
        (
            _attribute(
                mode_decision,
                "behavior_classification_sha256",
                label="mode_decision",
            ),
            behavior_hash,
            "mode -> behavior",
        ),
        (
            _attribute(
                mode_decision,
                "musical_classification_sha256",
                label="mode_decision",
            ),
            musical_hash,
            "mode -> musical",
        ),
        (
            _attribute(
                mode_decision,
                "perceptual_feature_sha256",
                label="mode_decision",
            ),
            perceptual_hash,
            "mode -> perceptual",
        ),
        (
            _attribute(
                mode_decision,
                "spectral_evolution_analysis_sha256",
                label="mode_decision",
            ),
            evolution_hash,
            "mode -> spectral evolution",
        ),
        (
            _attribute(
                profile_selection,
                "musical_classification_sha256",
                label="profile_selection",
            ),
            musical_hash,
            "profile -> musical",
        ),
        (
            _attribute(
                profile_selection,
                "mode_decision_sha256",
                label="profile_selection",
            ),
            mode_hash,
            "profile -> mode",
        ),
    )
    for actual, expected, label in expected_links:
        if actual != expected:
            raise PreV8LinkError(f"Invalid pre-V8 link: {label}")

    selected_definition = _attribute(
        profile_selection, "definition", label="profile_selection"
    )
    optimized_definition = _attribute(
        xt_wave_set_optimization, "profile", label="xt_wave_set_optimization"
    )
    if _analysis_hash(selected_definition, label="profile_definition") != _analysis_hash(
        optimized_definition, label="optimized_profile_definition"
    ):
        raise PreV8LinkError("XT optimization profile disagrees with profile selection")

    mode_status_value = str(
        getattr(_attribute(mode_decision, "status", label="mode_decision"), "value", _attribute(mode_decision, "status", label="mode_decision"))
    )
    selected_mode_object = _attribute(
        mode_decision, "selected_mode", label="mode_decision"
    )
    selected_mode = (
        None
        if selected_mode_object is None
        else str(getattr(selected_mode_object, "value", selected_mode_object))
    )
    selected_profile_object = _attribute(
        profile_selection, "selected_profile", label="profile_selection"
    )
    selected_profile = str(
        getattr(selected_profile_object, "value", selected_profile_object)
    )
    optimized_entries = tuple(
        _attribute(xt_wave_set_optimization, "entries", label="xt_wave_set_optimization")
    )
    repaired_entries = tuple(
        _attribute(auto_repair_sequence, "entries", label="auto_repair_sequence")
    )
    warnings = tuple(
        str(item)
        for item in (
            tuple(_attribute(mode_decision, "warnings", label="mode_decision"))
            + tuple(_attribute(profile_selection, "warnings", label="profile_selection"))
        )
    )

    return PreV8DecisionPlan(
        schema_version=PRE_V8_DECISION_PLAN_SCHEMA_VERSION,
        sample_rate=sample_rate,
        sample_count=sample_count,
        sample_sha256=sample_sha256,
        signal_extension_analysis_sha256=extension_hash,
        behavior_classification_sha256=behavior_hash,
        region_interest_analysis_sha256=region_hash,
        formant_analysis_sha256=formant_hash,
        spectral_evolution_analysis_sha256=evolution_hash,
        perceptual_feature_sha256=perceptual_hash,
        musical_classification_sha256=musical_hash,
        mode_decision_sha256=mode_hash,
        profile_selection_sha256=profile_hash,
        xt_wave_set_optimization_sha256=optimization_hash,
        auto_repair_sequence_sha256=repair_hash,
        mode_status=mode_status_value,
        selected_mode=selected_mode,
        selected_profile=selected_profile,
        optimized_wave_count=len(optimized_entries),
        repaired_wave_count=len(repaired_entries),
        warnings=warnings,
    )


def assemble_code_v8_preflight(
    source_chain: PreV8SourceChain,
    decision_plan: PreV8DecisionPlan,
    *,
    registry: ComplianceRegistry | None = None,
    compliance_closure: PreV8ComplianceClosure | None = None,
    tool_version: str = __version__,
) -> CodeV8PreflightAnalysis:
    selected_registry = load_compliance_registry() if registry is None else registry
    selected_closure = assert_zero_pre_v8_debt(
        selected_registry, compliance_closure
    )
    if decision_plan.ready_for_v8:
        status = PreV8ReadinessStatus.READY
        blockers: tuple[str, ...] = ()
        reason = (
            "V3-V7 provenance, V8-0 decision/profile/optimization/repair links, and "
            "all 62 pre-V8 compliance obligations are closed."
        )
    else:
        status = PreV8ReadinessStatus.REJECTED
        blockers = (
            "The source-level conversion-mode decision rejected this source; no hidden fallback is allowed.",
        )
        reason = (
            "The implementation debt gate is closed, but this specific source is not ready "
            "to enter CODE V8 generation."
        )
    return CodeV8PreflightAnalysis(
        schema_version=CODE_V8_PREFLIGHT_SCHEMA_VERSION,
        tool_version=tool_version,
        source_chain=source_chain,
        decision_plan=decision_plan,
        compliance_closure=selected_closure,
        status=status,
        blockers=blockers,
        reason=reason,
    )
