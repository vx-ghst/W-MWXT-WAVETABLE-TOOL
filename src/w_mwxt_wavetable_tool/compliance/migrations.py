from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from .adapters import adapt_audit_matrix_rows
from .models import ComplianceFormatError, ComplianceRegistry, REGISTRY_SCHEMA_VERSION


def migrate_registry_payload(
    payload: object,
    *,
    document_id: str | None = None,
    document_sha256: str | None = None,
    audit_matrix_sha256: str | None = None,
    execution_plan_sha256: str | None = None,
) -> dict[str, object]:
    """Migrate a supported legacy registry payload to the current strict schema.

    Supported legacy inputs are the validated audit-matrix row list and an object
    containing that list under ``rows``. Current schema payloads are validated and
    returned as a detached canonical dictionary.
    """

    if isinstance(payload, Mapping) and "schema_version" in payload:
        version = payload["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise ComplianceFormatError("schema_version must be an integer")
        if version != REGISTRY_SCHEMA_VERSION:
            raise ComplianceFormatError(
                f"Unsupported compliance registry schema version: {version}"
            )
        return ComplianceRegistry.from_dict(deepcopy(dict(payload))).to_dict()

    rows: Sequence[Mapping[str, Any]]
    if isinstance(payload, Mapping):
        if set(payload) != {"rows"}:
            raise ComplianceFormatError(
                "Legacy registry object must contain exactly one 'rows' field"
            )
        candidate = payload["rows"]
    else:
        candidate = payload

    if isinstance(candidate, (str, bytes, bytearray)) or not isinstance(
        candidate, Sequence
    ):
        raise ComplianceFormatError("Legacy registry rows must be a JSON array")
    rows = candidate  # type: ignore[assignment]

    metadata = {
        "document_id": document_id,
        "document_sha256": document_sha256,
        "audit_matrix_sha256": audit_matrix_sha256,
        "execution_plan_sha256": execution_plan_sha256,
    }
    missing = sorted(key for key, value in metadata.items() if value is None)
    if missing:
        raise ComplianceFormatError(
            f"Legacy migration requires source metadata: missing={missing}"
        )
    return adapt_audit_matrix_rows(
        rows,
        document_id=document_id or "",
        document_sha256=document_sha256 or "",
        audit_matrix_sha256=audit_matrix_sha256 or "",
        execution_plan_sha256=execution_plan_sha256 or "",
    )
