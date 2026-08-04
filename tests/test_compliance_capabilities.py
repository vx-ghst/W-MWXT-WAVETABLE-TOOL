from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.compliance import (
    CAPABILITY_SUMMARY_SCHEMA_VERSION,
    CapabilitySummary,
    load_compliance_registry,
    summarize_capabilities,
)


def test_capability_summary_matches_audited_v7_baseline() -> None:
    summary = summarize_capabilities(load_compliance_registry())
    assert summary.schema_version == CAPABILITY_SUMMARY_SCHEMA_VERSION
    assert summary.to_dict() == {
        "schema_version": 1,
        "total": 206,
        "supported": 62,
        "partial": 79,
        "planned": 54,
        "excluded": 9,
        "post_prototype": 2,
    }


def test_capability_summary_rejects_inconsistent_total() -> None:
    with pytest.raises(ValueError, match="do not add up"):
        CapabilitySummary(
            schema_version=1,
            total=2,
            supported=1,
            partial=1,
            planned=1,
            excluded=0,
            post_prototype=0,
        )
