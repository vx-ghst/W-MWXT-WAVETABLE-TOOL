from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence


REGISTRY_ID = "w-mwxt-cdc-traceability"
REGISTRY_SCHEMA_VERSION = 1
EXPECTED_REQUIREMENT_COUNT = 206
EXPECTED_ACTIVE_COUNT = 195
EXPECTED_EXCLUDED_COUNT = 9
EXPECTED_POST_PROTOTYPE_COUNT = 2

_REQUIREMENT_ID_RE = re.compile(r"^CDC-[A-Z0-9]+-[0-9]{3}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ComplianceFormatError(ValueError):
    """Raised when the executable compliance registry is malformed or unsupported."""


class RequirementScope(str, Enum):
    IN = "IN"
    MODIFIED = "MODIFIÉE"
    EXCLUDED = "EXCLUE"
    VERIFY = "À VÉRIFIER"
    POST_PROTOTYPE = "POST-PROTOTYPE"


class BaselineStatus(str, Enum):
    COVERED = "COUVERT"
    PARTIAL = "PARTIEL"
    ABSENT = "ABSENT"
    EXCLUDED = "EXCLU"
    RESOLVED = "RÉSOLU"
    POST_PROTOTYPE = "POST-PROTOTYPE"


class SupportState(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    PLANNED = "planned"
    EXCLUDED = "excluded"
    POST_PROTOTYPE = "post_prototype"


_ALLOWED_DESTINATIONS = frozenset(
    {
        "ACQUIS+NON-RÉGRESSION",
        "EXCLUSION-GATE",
        "POST-PROTOTYPE-ARCH",
        "V8-0",
        "V8-0+V12+V13",
        "V8-0+V13",
        "V8-0+V15",
        "V8",
        "V8+V10",
        "V9",
        "V10",
        "V11",
        "V11+V13",
        "V12",
        "V13",
        "V14",
        "V15",
    }
)


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ComplianceFormatError(
            f"Compliance payload cannot be serialized canonically: {exc}"
        ) from exc
    return (rendered + "\n").encode("utf-8")


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


def _require_int(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ComplianceFormatError(f"{label} must be an integer >= {minimum}")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    result = _require_string(value, label=label)
    if not _SHA256_RE.fullmatch(result):
        raise ComplianceFormatError(f"{label} must be a lowercase SHA-256 digest")
    return result


def support_for_status(status: BaselineStatus) -> SupportState:
    if status in (BaselineStatus.COVERED, BaselineStatus.RESOLVED):
        return SupportState.SUPPORTED
    if status is BaselineStatus.PARTIAL:
        return SupportState.PARTIAL
    if status is BaselineStatus.ABSENT:
        return SupportState.PLANNED
    if status is BaselineStatus.EXCLUDED:
        return SupportState.EXCLUDED
    return SupportState.POST_PROTOTYPE


@dataclass(frozen=True, slots=True)
class RegistrySource:
    document_id: str
    document_sha256: str
    audit_matrix_sha256: str
    execution_plan_sha256: str
    requirement_count: int

    def __post_init__(self) -> None:
        _require_string(self.document_id, label="source.document_id")
        _require_sha256(self.document_sha256, label="source.document_sha256")
        _require_sha256(self.audit_matrix_sha256, label="source.audit_matrix_sha256")
        _require_sha256(self.execution_plan_sha256, label="source.execution_plan_sha256")
        if self.requirement_count != EXPECTED_REQUIREMENT_COUNT:
            raise ComplianceFormatError(
                f"source.requirement_count must be {EXPECTED_REQUIREMENT_COUNT}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "document_sha256": self.document_sha256,
            "audit_matrix_sha256": self.audit_matrix_sha256,
            "execution_plan_sha256": self.execution_plan_sha256,
            "requirement_count": self.requirement_count,
        }

    @classmethod
    def from_dict(cls, value: object) -> RegistrySource:
        payload = _require_mapping(value, label="source")
        _require_exact_keys(
            payload,
            expected={
                "document_id",
                "document_sha256",
                "audit_matrix_sha256",
                "execution_plan_sha256",
                "requirement_count",
            },
            label="source",
        )
        return cls(
            document_id=_require_string(payload["document_id"], label="source.document_id"),
            document_sha256=_require_sha256(
                payload["document_sha256"], label="source.document_sha256"
            ),
            audit_matrix_sha256=_require_sha256(
                payload["audit_matrix_sha256"], label="source.audit_matrix_sha256"
            ),
            execution_plan_sha256=_require_sha256(
                payload["execution_plan_sha256"], label="source.execution_plan_sha256"
            ),
            requirement_count=_require_int(
                payload["requirement_count"], label="source.requirement_count", minimum=1
            ),
        )


@dataclass(frozen=True, slots=True)
class RequirementRecord:
    line: int
    id: str
    scope: RequirementScope
    requirement: str
    old_phase: str
    old_module: str
    old_test: str
    old_acceptance: str
    baseline_status: BaselineStatus
    support: SupportState
    observed: str
    existing_tests: str
    gap: str
    destination: str
    target_modules: str
    target_tests: str

    def __post_init__(self) -> None:
        if self.line <= 0:
            raise ComplianceFormatError("requirement.line must be positive")
        if not _REQUIREMENT_ID_RE.fullmatch(self.id):
            raise ComplianceFormatError(f"Invalid requirement ID: {self.id!r}")
        for field_name in (
            "requirement",
            "old_phase",
            "old_module",
            "old_test",
            "old_acceptance",
            "observed",
            "existing_tests",
            "gap",
            "destination",
            "target_modules",
            "target_tests",
        ):
            _require_string(getattr(self, field_name), label=f"requirement.{field_name}")
        if self.destination not in _ALLOWED_DESTINATIONS:
            raise ComplianceFormatError(
                f"Unsupported destination {self.destination!r} for {self.id}"
            )
        expected_support = support_for_status(self.baseline_status)
        if self.support is not expected_support:
            raise ComplianceFormatError(
                f"{self.id} support {self.support.value!r} disagrees with "
                f"baseline status {self.baseline_status.value!r}"
            )
        if self.scope is RequirementScope.EXCLUDED:
            if self.baseline_status is not BaselineStatus.EXCLUDED:
                raise ComplianceFormatError(f"{self.id} excluded scope must use EXCLU status")
            if self.destination != "EXCLUSION-GATE":
                raise ComplianceFormatError(
                    f"{self.id} excluded scope must use EXCLUSION-GATE"
                )
        elif self.scope is RequirementScope.POST_PROTOTYPE:
            if self.baseline_status is not BaselineStatus.POST_PROTOTYPE:
                raise ComplianceFormatError(
                    f"{self.id} post-prototype scope must use POST-PROTOTYPE status"
                )
            if self.destination != "POST-PROTOTYPE-ARCH":
                raise ComplianceFormatError(
                    f"{self.id} post-prototype scope must use POST-PROTOTYPE-ARCH"
                )
        elif self.destination in {"EXCLUSION-GATE", "POST-PROTOTYPE-ARCH"}:
            raise ComplianceFormatError(
                f"{self.id} active scope cannot use destination {self.destination}"
            )

    @property
    def active(self) -> bool:
        return self.scope not in {
            RequirementScope.EXCLUDED,
            RequirementScope.POST_PROTOTYPE,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "line": self.line,
            "id": self.id,
            "scope": self.scope.value,
            "requirement": self.requirement,
            "old_phase": self.old_phase,
            "old_module": self.old_module,
            "old_test": self.old_test,
            "old_acceptance": self.old_acceptance,
            "baseline_status": self.baseline_status.value,
            "support": self.support.value,
            "observed": self.observed,
            "existing_tests": self.existing_tests,
            "gap": self.gap,
            "destination": self.destination,
            "target_modules": self.target_modules,
            "target_tests": self.target_tests,
        }

    @classmethod
    def from_dict(cls, value: object) -> RequirementRecord:
        payload = _require_mapping(value, label="requirement")
        _require_exact_keys(
            payload,
            expected={
                "line",
                "id",
                "scope",
                "requirement",
                "old_phase",
                "old_module",
                "old_test",
                "old_acceptance",
                "baseline_status",
                "support",
                "observed",
                "existing_tests",
                "gap",
                "destination",
                "target_modules",
                "target_tests",
            },
            label="requirement",
        )
        try:
            scope = RequirementScope(
                _require_string(payload["scope"], label="requirement.scope")
            )
            status = BaselineStatus(
                _require_string(
                    payload["baseline_status"], label="requirement.baseline_status"
                )
            )
            support = SupportState(
                _require_string(payload["support"], label="requirement.support")
            )
        except ValueError as exc:
            raise ComplianceFormatError("Unsupported requirement enum value") from exc
        return cls(
            line=_require_int(payload["line"], label="requirement.line", minimum=1),
            id=_require_string(payload["id"], label="requirement.id"),
            scope=scope,
            requirement=_require_string(
                payload["requirement"], label="requirement.requirement"
            ),
            old_phase=_require_string(payload["old_phase"], label="requirement.old_phase"),
            old_module=_require_string(
                payload["old_module"], label="requirement.old_module"
            ),
            old_test=_require_string(payload["old_test"], label="requirement.old_test"),
            old_acceptance=_require_string(
                payload["old_acceptance"], label="requirement.old_acceptance"
            ),
            baseline_status=status,
            support=support,
            observed=_require_string(payload["observed"], label="requirement.observed"),
            existing_tests=_require_string(
                payload["existing_tests"], label="requirement.existing_tests"
            ),
            gap=_require_string(payload["gap"], label="requirement.gap"),
            destination=_require_string(
                payload["destination"], label="requirement.destination"
            ),
            target_modules=_require_string(
                payload["target_modules"], label="requirement.target_modules"
            ),
            target_tests=_require_string(
                payload["target_tests"], label="requirement.target_tests"
            ),
        )


@dataclass(frozen=True, slots=True)
class ComplianceRegistry:
    registry_id: str
    schema_version: int
    source: RegistrySource
    requirements: tuple[RequirementRecord, ...]
    registry_sha256: str

    def __post_init__(self) -> None:
        if self.registry_id != REGISTRY_ID:
            raise ComplianceFormatError(f"registry_id must be {REGISTRY_ID!r}")
        if self.schema_version != REGISTRY_SCHEMA_VERSION:
            raise ComplianceFormatError(
                f"Unsupported compliance registry schema version: {self.schema_version}"
            )
        _require_sha256(self.registry_sha256, label="registry_sha256")
        if len(self.requirements) != EXPECTED_REQUIREMENT_COUNT:
            raise ComplianceFormatError(
                f"Registry must contain exactly {EXPECTED_REQUIREMENT_COUNT} requirements"
            )
        ids = tuple(item.id for item in self.requirements)
        if len(set(ids)) != len(ids):
            raise ComplianceFormatError("Requirement IDs must be unique")
        lines = tuple(item.line for item in self.requirements)
        if tuple(sorted(lines)) != lines or len(set(lines)) != len(lines):
            raise ComplianceFormatError(
                "Requirements must be ordered by unique ascending source line"
            )
        active_count = sum(item.active for item in self.requirements)
        excluded_count = sum(
            item.scope is RequirementScope.EXCLUDED for item in self.requirements
        )
        post_count = sum(
            item.scope is RequirementScope.POST_PROTOTYPE for item in self.requirements
        )
        if active_count != EXPECTED_ACTIVE_COUNT:
            raise ComplianceFormatError(
                f"Registry must contain {EXPECTED_ACTIVE_COUNT} active requirements"
            )
        if excluded_count != EXPECTED_EXCLUDED_COUNT:
            raise ComplianceFormatError(
                f"Registry must contain {EXPECTED_EXCLUDED_COUNT} exclusions"
            )
        if post_count != EXPECTED_POST_PROTOTYPE_COUNT:
            raise ComplianceFormatError(
                f"Registry must contain {EXPECTED_POST_PROTOTYPE_COUNT} post-prototype items"
            )
        if self.source.requirement_count != len(self.requirements):
            raise ComplianceFormatError("Source and registry requirement counts disagree")
        if self.registry_sha256 != self.compute_sha256():
            raise ComplianceFormatError("Compliance registry SHA-256 mismatch")

    @property
    def active_requirements(self) -> tuple[RequirementRecord, ...]:
        return tuple(item for item in self.requirements if item.active)

    @property
    def excluded_requirements(self) -> tuple[RequirementRecord, ...]:
        return tuple(
            item for item in self.requirements if item.scope is RequirementScope.EXCLUDED
        )

    @property
    def post_prototype_requirements(self) -> tuple[RequirementRecord, ...]:
        return tuple(
            item
            for item in self.requirements
            if item.scope is RequirementScope.POST_PROTOTYPE
        )

    def requirement(self, requirement_id: str) -> RequirementRecord:
        for item in self.requirements:
            if item.id == requirement_id:
                return item
        raise KeyError(requirement_id)

    def _content_dict(self) -> dict[str, object]:
        return {
            "registry_id": self.registry_id,
            "schema_version": self.schema_version,
            "source": self.source.to_dict(),
            "requirements": [item.to_dict() for item in self.requirements],
        }

    def compute_sha256(self) -> str:
        return sha256(canonical_json_bytes(self._content_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        payload = self._content_dict()
        payload["registry_sha256"] = self.registry_sha256
        return payload

    @classmethod
    def from_dict(cls, value: object) -> ComplianceRegistry:
        payload = _require_mapping(value, label="registry")
        _require_exact_keys(
            payload,
            expected={
                "registry_id",
                "schema_version",
                "source",
                "requirements",
                "registry_sha256",
            },
            label="registry",
        )
        schema_version = _require_int(
            payload["schema_version"], label="registry.schema_version", minimum=1
        )
        if schema_version != REGISTRY_SCHEMA_VERSION:
            raise ComplianceFormatError(
                f"Unsupported compliance registry schema version: {schema_version}"
            )
        requirements_payload = _require_sequence(
            payload["requirements"], label="registry.requirements"
        )
        return cls(
            registry_id=_require_string(
                payload["registry_id"], label="registry.registry_id"
            ),
            schema_version=schema_version,
            source=RegistrySource.from_dict(payload["source"]),
            requirements=tuple(
                RequirementRecord.from_dict(item) for item in requirements_payload
            ),
            registry_sha256=_require_sha256(
                payload["registry_sha256"], label="registry.registry_sha256"
            ),
        )
