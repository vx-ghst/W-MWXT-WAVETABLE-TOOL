from __future__ import annotations

from copy import deepcopy

import pytest

from w_mwxt_wavetable_tool.compliance import (
    ComplianceFormatError,
    ComplianceRegistry,
    load_compliance_registry,
    migrate_registry_payload,
)


def _legacy_rows() -> list[dict[str, object]]:
    registry = load_compliance_registry()
    rows: list[dict[str, object]] = []
    for item in registry.requirements:
        row = item.to_dict()
        del row["support"]
        rows.append(row)
    return rows


def _metadata() -> dict[str, str]:
    source = load_compliance_registry().source
    return {
        "document_id": source.document_id,
        "document_sha256": source.document_sha256,
        "audit_matrix_sha256": source.audit_matrix_sha256,
        "execution_plan_sha256": source.execution_plan_sha256,
    }


def test_legacy_row_list_migrates_to_exact_current_registry() -> None:
    migrated = migrate_registry_payload(_legacy_rows(), **_metadata())
    assert ComplianceRegistry.from_dict(migrated) == load_compliance_registry()


def test_legacy_rows_object_migrates() -> None:
    migrated = migrate_registry_payload({"rows": _legacy_rows()}, **_metadata())
    assert ComplianceRegistry.from_dict(migrated) == load_compliance_registry()


def test_current_registry_migration_is_idempotent_and_detached() -> None:
    original = load_compliance_registry().to_dict()
    migrated = migrate_registry_payload(original)
    assert migrated == original
    assert migrated is not original
    migrated["registry_id"] = "changed"
    assert original["registry_id"] != migrated["registry_id"]


def test_legacy_migration_requires_all_source_metadata() -> None:
    with pytest.raises(ComplianceFormatError, match="requires source metadata"):
        migrate_registry_payload(_legacy_rows())


def test_future_schema_is_rejected_without_best_effort_downgrade() -> None:
    payload = deepcopy(load_compliance_registry().to_dict())
    payload["schema_version"] = 999
    with pytest.raises(ComplianceFormatError, match="Unsupported compliance registry schema"):
        migrate_registry_payload(payload)
