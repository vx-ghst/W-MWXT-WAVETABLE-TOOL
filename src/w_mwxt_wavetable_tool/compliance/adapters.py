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
