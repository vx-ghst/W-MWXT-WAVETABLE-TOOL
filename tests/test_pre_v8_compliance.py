from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from w_mwxt_wavetable_tool.compliance import (
    ClosureStage,
    ClosureSupport,
    ComplianceFormatError,
    EXPECTED_PRE_V8_REQUIREMENT_COUNT,
    PreV8ComplianceClosure,
    assert_zero_pre_v8_debt,
    load_compliance_registry,
    load_pre_v8_compliance_closure,
)


def test_bundled_closure_has_exact_zero_debt_gate() -> None:
    closure = load_pre_v8_compliance_closure()
    assert len(closure.evidence) == EXPECTED_PRE_V8_REQUIREMENT_COUNT == 62
    assert closure.supported_count == 62
    assert closure.debt_requirement_ids == ()
    assert closure.zero_required_debt is True


def test_closure_exactly_matches_registry_pre_v8_destinations() -> None:
    registry = load_compliance_registry()
    closure = load_pre_v8_compliance_closure(registry)
    expected = tuple(
        item.id
        for item in registry.requirements
        if item.active and item.destination.startswith("V8-0")
    )
    assert closure.requirement_ids == expected


def test_stage_distribution_is_exact() -> None:
    closure = load_pre_v8_compliance_closure()
    assert Counter(item.stage for item in closure.evidence) == {
        ClosureStage.CODE_V6: 2,
        ClosureStage.CODE_V8_0B: 12,
        ClosureStage.CODE_V8_0C: 19,
        ClosureStage.CODE_V8_0D: 24,
        ClosureStage.CODE_V8_0E: 4,
        ClosureStage.CODE_V8_0F: 1,
    }


def test_every_evidence_record_is_supported_and_hashed() -> None:
    closure = load_pre_v8_compliance_closure()
    assert all(item.support is ClosureSupport.SUPPORTED for item in closure.evidence)
    hashes = tuple(item.evidence_sha256 for item in closure.evidence)
    assert len(set(hashes)) == len(hashes)
    assert all(len(value) == 64 for value in hashes)


def test_all_declared_module_and_test_evidence_paths_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    closure = load_pre_v8_compliance_closure()
    paths = {
        item
        for evidence in closure.evidence
        for item in (*evidence.modules, *evidence.tests)
    }
    missing = sorted(path for path in paths if not (root / path).is_file())
    assert missing == []


def test_taxonomy_correction_is_explicit() -> None:
    closure = load_pre_v8_compliance_closure()
    record = next(
        item for item in closure.evidence if item.requirement_id == "CDC-CLS-001"
    )
    assert "27" in record.reason
    assert "correct" in record.reason.lower()


def test_windows_core_gate_is_explicit() -> None:
    closure = load_pre_v8_compliance_closure()
    record = next(
        item for item in closure.evidence if item.requirement_id == "CDC-QLT-010"
    )
    assert record.stage is ClosureStage.CODE_V8_0F
    assert ".github/workflows/tests.yml" in record.modules
    assert "Windows" in record.reason


def test_baseline_registry_remains_historical_and_immutable() -> None:
    registry = load_compliance_registry()
    closure = load_pre_v8_compliance_closure(registry)
    assert closure.baseline_registry_sha256 == registry.registry_sha256
    baseline_support = Counter(item.support.value for item in registry.requirements)
    assert baseline_support["partial"] > 0
    assert baseline_support["planned"] > 0
    assert closure.zero_required_debt is True


def test_assert_zero_debt_returns_validated_closure() -> None:
    closure = assert_zero_pre_v8_debt()
    assert closure.closure_sha256 == load_pre_v8_compliance_closure().closure_sha256


def test_serialized_summary_is_consistent() -> None:
    closure = load_pre_v8_compliance_closure()
    payload = closure.to_dict()
    assert payload["required_count"] == 62
    assert payload["supported_count"] == 62
    assert payload["debt_requirement_ids"] == []
    assert payload["zero_required_debt"] is True
    assert len(payload["evidence_sha256"]) == 62


def raw_payload() -> dict[str, object]:
    path = (
        Path(__file__).resolve().parents[1]
        / "src/w_mwxt_wavetable_tool/compliance/data/pre_v8_closure_v1.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "field",
    [
        "closure_id",
        "schema_version",
        "baseline_registry_sha256",
        "requirement_destination_prefix",
        "evidence",
        "closure_sha256",
    ],
)
def test_closure_rejects_missing_top_level_fields(field: str) -> None:
    payload = raw_payload()
    del payload[field]
    with pytest.raises(ComplianceFormatError):
        PreV8ComplianceClosure.from_dict(payload)


def test_closure_rejects_extra_top_level_field() -> None:
    payload = raw_payload()
    payload["unexpected"] = True
    with pytest.raises(ComplianceFormatError):
        PreV8ComplianceClosure.from_dict(payload)


def test_closure_rejects_unknown_support_state() -> None:
    payload = raw_payload()
    payload["evidence"][0]["support"] = "unknown"
    with pytest.raises(ComplianceFormatError):
        PreV8ComplianceClosure.from_dict(payload)


def test_closure_rejects_partial_debt_at_registry_gate() -> None:
    payload = raw_payload()
    payload["evidence"][0]["support"] = "partial"
    payload_without_hash = dict(payload)
    payload_without_hash.pop("closure_sha256")
    from hashlib import sha256
    from w_mwxt_wavetable_tool.compliance import canonical_json_bytes

    payload["closure_sha256"] = sha256(canonical_json_bytes(payload_without_hash)).hexdigest()
    closure = PreV8ComplianceClosure.from_dict(payload)
    assert closure.zero_required_debt is False
    with pytest.raises(ComplianceFormatError, match="debt remains"):
        closure.validate_against_registry(load_compliance_registry())


def test_closure_rejects_duplicate_requirement_id() -> None:
    payload = raw_payload()
    payload["evidence"][1]["requirement_id"] = payload["evidence"][0]["requirement_id"]
    with pytest.raises(ComplianceFormatError):
        PreV8ComplianceClosure.from_dict(payload)


def test_closure_rejects_hash_tampering() -> None:
    payload = raw_payload()
    payload["evidence"][0]["reason"] += " tampered"
    with pytest.raises(ComplianceFormatError, match="SHA-256 mismatch"):
        PreV8ComplianceClosure.from_dict(payload)


def test_closure_rejects_empty_module_or_test_evidence() -> None:
    for field in ("modules", "tests"):
        payload = raw_payload()
        payload["evidence"][0][field] = []
        with pytest.raises(ComplianceFormatError):
            PreV8ComplianceClosure.from_dict(payload)
