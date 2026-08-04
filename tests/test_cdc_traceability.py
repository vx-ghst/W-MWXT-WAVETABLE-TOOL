from __future__ import annotations

from collections import Counter

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool.compliance import (
    EXPECTED_ACTIVE_COUNT,
    EXPECTED_EXCLUDED_COUNT,
    EXPECTED_POST_PROTOTYPE_COUNT,
    EXPECTED_REQUIREMENT_COUNT,
    RequirementScope,
    load_compliance_registry,
)


def test_registry_contains_every_requirement_exactly_once() -> None:
    registry = load_compliance_registry()
    ids = [item.id for item in registry.requirements]
    assert len(ids) == EXPECTED_REQUIREMENT_COUNT == 206
    assert len(set(ids)) == len(ids)
    assert ids[0] == "CDC-IMP-001"
    assert ids[-1] == "CDC-HW-011"
    assert all(item.destination for item in registry.requirements)
    assert all(item.target_modules for item in registry.requirements)
    assert all(item.target_tests for item in registry.requirements)


def test_registry_scope_counts_match_exhaustive_audit() -> None:
    registry = load_compliance_registry()
    counts = Counter(item.scope for item in registry.requirements)
    assert len(registry.active_requirements) == EXPECTED_ACTIVE_COUNT == 195
    assert counts[RequirementScope.IN] == 187
    assert counts[RequirementScope.MODIFIED] == 2
    assert counts[RequirementScope.VERIFY] == 6
    assert len(registry.excluded_requirements) == EXPECTED_EXCLUDED_COUNT == 9
    assert len(registry.post_prototype_requirements) == EXPECTED_POST_PROTOTYPE_COUNT == 2


def test_registry_source_fingerprints_are_pinned() -> None:
    source = load_compliance_registry().source
    assert source.document_id == "cahier-des-charges.md"
    assert source.document_sha256 == (
        "86019dab690e74f608659888ea599b45ee7b1d740a56b075ca66ef149c852ba0"
    )
    assert source.audit_matrix_sha256 == (
        "2621e479070635ae6bb008fbb588a4a80b31043f310977bfc9253a71fec13f76"
    )
    assert source.execution_plan_sha256 == (
        "2a6e0b248a47a5c7add8fd7d4b3b56c325972611e2a52d1ddb68f937338f22c0"
    )


def test_known_reconciliations_are_explicit() -> None:
    registry = load_compliance_registry()
    assert registry.requirement("CDC-IMP-006").destination == "V8-0"
    assert registry.requirement("CDC-W61-001").destination == "V8"
    assert registry.requirement("CDC-REP-001").destination == "V8-0"
    assert registry.requirement("CDC-EXP-001").destination == "V9"
    assert registry.requirement("CDC-BAT-001").destination == "V12"
    assert registry.requirement("CDC-GUI-001").destination == "V13"
    assert registry.requirement("CDC-SYX-012").destination == "V14"


def test_compliance_contract_is_available_from_public_api() -> None:
    assert tool.load_compliance_registry().registry_sha256 == (
        "64c486a4d9f3cbe5a6b7a5efe14bae631595112bfd2571a94fd9e018b3e4e0b9"
    )
    assert tool.summarize_capabilities(tool.load_compliance_registry()).total == 206
