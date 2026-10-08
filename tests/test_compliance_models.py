from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

from w_mwxt_wavetable_tool.compliance import (
    ComplianceFormatError,
    ComplianceRegistry,
    REGISTRY_ID,
    REGISTRY_SCHEMA_VERSION,
    canonical_json_bytes,
    load_compliance_registry,
)


def _reseal(payload: dict[str, object]) -> dict[str, object]:
    content = {key: value for key, value in payload.items() if key != "registry_sha256"}
    payload["registry_sha256"] = sha256(canonical_json_bytes(content)).hexdigest()
    return payload


def test_canonical_json_is_stable_utf8_and_newline_terminated() -> None:
    first = canonical_json_bytes({"z": 1, "a": "é"})
    second = canonical_json_bytes({"a": "é", "z": 1})
    assert first == second == b'{"a":"\xc3\xa9","z":1}\n'


def test_registry_roundtrip_is_canonical() -> None:
    registry = load_compliance_registry()
    assert registry.registry_id == REGISTRY_ID
    assert registry.schema_version == REGISTRY_SCHEMA_VERSION
    reparsed = ComplianceRegistry.from_dict(registry.to_dict())
    assert reparsed == registry
    assert reparsed.compute_sha256() == registry.registry_sha256


def test_registry_rejects_tampered_requirement_without_resealing() -> None:
    payload = deepcopy(load_compliance_registry().to_dict())
    payload["requirements"][0]["requirement"] += " tampered"  # type: ignore[index]
    with pytest.raises(ComplianceFormatError, match="SHA-256 mismatch"):
        ComplianceRegistry.from_dict(payload)


def test_registry_rejects_extra_fields_even_when_resealed() -> None:
    payload = deepcopy(load_compliance_registry().to_dict())
    payload["unexpected"] = True
    _reseal(payload)
    with pytest.raises(ComplianceFormatError, match="fields are invalid"):
        ComplianceRegistry.from_dict(payload)


def test_registry_rejects_future_schema() -> None:
    payload = deepcopy(load_compliance_registry().to_dict())
    payload["schema_version"] = REGISTRY_SCHEMA_VERSION + 1
    _reseal(payload)
    with pytest.raises(ComplianceFormatError, match="Unsupported compliance registry schema"):
        ComplianceRegistry.from_dict(payload)


def test_requirement_support_must_match_baseline_status() -> None:
    payload = deepcopy(load_compliance_registry().to_dict())
    payload["requirements"][0]["support"] = "planned"  # type: ignore[index]
    _reseal(payload)
    with pytest.raises(ComplianceFormatError, match="disagrees with baseline status"):
        ComplianceRegistry.from_dict(payload)
