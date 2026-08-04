import pytest

from w_mwxt_wavetable_tool import (
    LEGACY_REQUIREMENT_ID_CROSSWALK,
    ComplianceFormatError,
    load_compliance_registry,
    migrate_requirement_references,
    resolve_requirement_reference,
)


def test_all_21_historical_ids_are_explicitly_mapped():
    assert len(LEGACY_REQUIREMENT_ID_CROSSWALK) == 21


def test_every_alias_resolves_only_to_canonical_registry_ids():
    registry = load_compliance_registry()
    canonical = {item.id for item in registry.requirements}
    for legacy in LEGACY_REQUIREMENT_ID_CROSSWALK:
        assert set(resolve_requirement_reference(legacy, registry=registry)) <= canonical


def test_internal_wctd_label_is_recognized_without_claim():
    registry = load_compliance_registry()
    assert resolve_requirement_reference("CDC-WCTD-003", registry=registry) == ()


def test_unknown_identifier_fails_closed():
    registry = load_compliance_registry()
    with pytest.raises(ComplianceFormatError):
        resolve_requirement_reference("CDC-UNKNOWN-999", registry=registry)


def test_migration_deduplicates_canonical_results():
    registry = load_compliance_registry()
    assert migrate_requirement_references(
        ("CDC-INT-001", "CDC-TRN-001"), registry=registry
    ) == ("CDC-TRN-001",)
