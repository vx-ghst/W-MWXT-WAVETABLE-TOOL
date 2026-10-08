from __future__ import annotations

import w_mwxt_wavetable_tool as public
from w_mwxt_wavetable_tool import compliance


EXPECTED = (
    "ClosureStage",
    "ClosureSupport",
    "CodeV8PreflightAnalysis",
    "PreV8ComplianceClosure",
    "PreV8DecisionPlan",
    "PreV8LinkError",
    "PreV8ReadinessStatus",
    "PreV8SourceChain",
    "RequirementClosureEvidence",
    "assemble_code_v8_preflight",
    "assemble_pre_v8_decision_plan",
    "assemble_pre_v8_source_chain",
    "assert_zero_pre_v8_debt",
    "load_pre_v8_compliance_closure",
)


def test_compliance_package_exports_complete_v8f_surface() -> None:
    for name in EXPECTED:
        assert hasattr(compliance, name), name
        assert name in compliance.__all__


def test_package_root_exports_complete_v8f_surface() -> None:
    for name in EXPECTED:
        assert hasattr(public, name), name
        assert name in public.__all__


def test_public_zero_debt_gate_executes() -> None:
    closure = public.assert_zero_pre_v8_debt()
    assert closure.zero_required_debt is True
    assert closure.supported_count == 62


def test_public_constants_remain_versioned() -> None:
    assert compliance.PRE_V8_CLOSURE_SCHEMA_VERSION == 1
    assert compliance.PRE_V8_SOURCE_CHAIN_SCHEMA_VERSION == 1
    assert compliance.PRE_V8_DECISION_PLAN_SCHEMA_VERSION == 1
    assert compliance.CODE_V8_PREFLIGHT_SCHEMA_VERSION == 1
    assert compliance.EXPECTED_PRE_V8_REQUIREMENT_COUNT == 62
