from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .models import (
    ComplianceFormatError,
    ComplianceRegistry,
    REGISTRY_ID,
    REGISTRY_SCHEMA_VERSION,
    RegistrySource,
    RequirementRecord,
    canonical_json_bytes,
    support_for_status,
    BaselineStatus,
)


_LEGACY_ROW_KEYS = {
    "line",
    "id",
    "scope",
    "requirement",
    "old_phase",
    "old_module",
    "old_test",
    "old_acceptance",
    "baseline_status",
    "observed",
    "existing_tests",
    "gap",
    "destination",
    "target_modules",
    "target_tests",
}


def adapt_audit_matrix_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    document_id: str,
    document_sha256: str,
    audit_matrix_sha256: str,
    execution_plan_sha256: str,
) -> dict[str, object]:
    if isinstance(rows, (str, bytes, bytearray)) or not isinstance(rows, Sequence):
        raise ComplianceFormatError("Legacy audit matrix must be an array of rows")

    requirements: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ComplianceFormatError(f"Legacy row {index} must be a JSON object")
        if set(row) != _LEGACY_ROW_KEYS:
            missing = sorted(_LEGACY_ROW_KEYS - set(row))
            extra = sorted(set(row) - _LEGACY_ROW_KEYS)
            raise ComplianceFormatError(
                f"Legacy row {index} fields are invalid: missing={missing}, extra={extra}"
            )
        normalized = deepcopy(dict(row))
        try:
            status = BaselineStatus(normalized["baseline_status"])
        except (KeyError, ValueError) as exc:
            raise ComplianceFormatError(
                f"Legacy row {index} has unsupported baseline status"
            ) from exc
        normalized["support"] = support_for_status(status).value
        requirements.append(normalized)

    source = RegistrySource(
        document_id=document_id,
        document_sha256=document_sha256,
        audit_matrix_sha256=audit_matrix_sha256,
        execution_plan_sha256=execution_plan_sha256,
        requirement_count=len(requirements),
    )
    content: dict[str, object] = {
        "registry_id": REGISTRY_ID,
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "source": source.to_dict(),
        "requirements": requirements,
    }
    content["registry_sha256"] = sha256(canonical_json_bytes(content)).hexdigest()
    registry = ComplianceRegistry.from_dict(content)
    return registry.to_dict()

# Historical validation labels emitted before the canonical V8-G
# reconciliation. They are migration aliases only and never create a new
# requirement in the 206-record registry.
LEGACY_REQUIREMENT_ID_CROSSWALK: dict[str, tuple[str, ...]] = {
    "CDC-INT-001": ("CDC-TRN-001",),
    "CDC-INT-002": ("CDC-TRN-001",),
    "CDC-INT-003": ("CDC-TRN-001",),
    "CDC-INT-004": ("CDC-TRN-002",),
    "CDC-INT-005": ("CDC-TRN-002",),
    "CDC-INT-006": ("CDC-TRN-003",),
    "CDC-INT-007": ("CDC-TRN-005", "CDC-W61-006"),
    "CDC-INT-008": ("CDC-TRN-007",),
    "CDC-INT-009": ("CDC-TRN-004", "CDC-TRN-006"),
    "CDC-FAC-001": ("CDC-PROF-003",),
    "CDC-FAC-002": ("CDC-PLC-005",),
    "CDC-FAC-003": ("CDC-TRN-006",),
    "CDC-WCTD-001": ("CDC-SYX-002",),
    "CDC-WCTD-002": ("CDC-SYX-002",),
    # Recognized internal validation label; deliberately carries no CDC claim.
    "CDC-WCTD-003": (),
    "CDC-HWG-001": ("CDC-HW-002",),
    "CDC-HWG-002": ("CDC-HW-002",),
    "CDC-HWG-003": ("CDC-HW-002",),
    "CDC-HWG-004": ("CDC-HW-002",),
    "CDC-HWG-005": ("CDC-HW-002",),
    "CDC-HWG-006": ("CDC-HW-002",),
}


def resolve_requirement_reference(
    requirement_id: str,
    *,
    registry: ComplianceRegistry,
) -> tuple[str, ...]:
    """Resolve one canonical or explicitly mapped historical identifier."""

    if (
        not isinstance(requirement_id, str)
        or not requirement_id
        or requirement_id.strip() != requirement_id
    ):
        raise ComplianceFormatError(
            "requirement_id must be a normalized non-empty string"
        )
    if not isinstance(registry, ComplianceRegistry):
        raise ComplianceFormatError("registry must be ComplianceRegistry")
    canonical_ids = {item.id for item in registry.requirements}
    if requirement_id in canonical_ids:
        return (requirement_id,)
    try:
        resolved = LEGACY_REQUIREMENT_ID_CROSSWALK[requirement_id]
    except KeyError as exc:
        raise ComplianceFormatError(
            f"Unknown requirement identifier: {requirement_id}"
        ) from exc
    missing = tuple(item for item in resolved if item not in canonical_ids)
    if missing:
        raise ComplianceFormatError(
            f"Requirement crosswalk references unknown canonical IDs: {missing}"
        )
    return resolved


def resolve_requirement_references(
    requirement_ids: Sequence[str],
    *,
    registry: ComplianceRegistry,
) -> tuple[str, ...]:
    """Resolve a sequence and de-duplicate canonical IDs deterministically."""

    if isinstance(requirement_ids, (str, bytes, bytearray)) or not isinstance(
        requirement_ids, Sequence
    ):
        raise ComplianceFormatError("requirement_ids must be a sequence")
    result: list[str] = []
    for requirement_id in requirement_ids:
        for canonical_id in resolve_requirement_reference(
            requirement_id, registry=registry
        ):
            if canonical_id not in result:
                result.append(canonical_id)
    return tuple(result)
