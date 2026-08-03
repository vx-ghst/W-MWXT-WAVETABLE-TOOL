from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from v8f_materialization_helpers import passing_hardware_evidence, v8f_context

from w_mwxt_wavetable_tool.wavetable.factory_style import FactoryStyleAction, FactoryStylePolicy
from w_mwxt_wavetable_tool.wavetable.hardware_gate import (
    CodeV8FStatus,
    HardwareGatePlanStatus,
    HardwareGateResultStatus,
    evaluate_hardware_gates,
)
from w_mwxt_wavetable_tool.wavetable.models import WavetableContractError
from w_mwxt_wavetable_tool.wavetable.wctd import WctdReferenceKind


def test_v8f_aggregate_is_frozen() -> None:
    result = v8f_context()[-1]
    with pytest.raises(FrozenInstanceError):
        result.status = CodeV8FStatus.HARDWARE_ACCEPTED


def test_factory_style_decision_hashes_are_lowercase_sha256() -> None:
    result = v8f_context(factory_style=True)[-1]
    for item in result.factory_style.primary_variant.decisions:
        assert len(item.analysis_sha256) == 64
        assert item.analysis_sha256 == item.analysis_sha256.lower()


def test_wctd_reference_hashes_are_lowercase_sha256() -> None:
    result = v8f_context()[-1]
    for item in result.wctd_models.primary_model.entries:
        assert len(item.analysis_sha256) == 64


def test_hardware_gate_results_have_canonical_requirement_order() -> None:
    result = v8f_context(resolved=True)[-1]
    assert tuple(item.requirement.gate_id for item in result.hardware_gates.results) == tuple(
        item.gate_id for item in result.hardware_gates.requirements
    )


def test_factory_style_actions_are_stable() -> None:
    assert tuple(item.value for item in FactoryStyleAction) == (
        "preserve_protected",
        "preserve_keyframe",
        "preserve_edge_hold",
        "preserve_transition",
        "smooth_transition",
    )


def test_wctd_reference_kinds_are_stable() -> None:
    assert tuple(item.value for item in WctdReferenceKind) == ("user_slot", "fixed_tail")


def test_code_v8f_status_values_are_stable() -> None:
    assert tuple(item.value for item in CodeV8FStatus) == (
        "ready_for_hardware",
        "hardware_accepted",
        "hardware_failed",
        "rejected",
    )


def test_hardware_plan_status_values_are_stable() -> None:
    assert tuple(item.value for item in HardwareGatePlanStatus) == ("pending", "accepted", "failed")


def test_hardware_result_status_values_are_stable() -> None:
    assert tuple(item.value for item in HardwareGateResultStatus) == ("blocked", "pending", "pass", "fail")


def test_factory_policy_to_dict_is_complete() -> None:
    data = FactoryStylePolicy().to_dict()
    assert set(data) == {
        "schema_version",
        "enabled",
        "smoothing_passes",
        "smoothing_strength",
        "neighbor_blend",
        "maximum_sample_delta",
        "require_non_worsening_continuity",
        "continuity_tolerance",
    }


def test_v8f_to_dict_contains_all_aggregates() -> None:
    data = v8f_context()[-1].to_dict()
    assert data["factory_style"] is not None
    assert data["wctd_models"] is not None
    assert data["hardware_gates"] is not None
    assert data["analysis_sha256"]


def test_passing_gate_plan_contains_no_blockers() -> None:
    result = v8f_context(resolved=True, evidence_mode="pass")[-1]
    assert result.hardware_gates.blockers == ()
    assert all(item.blockers == () for item in result.hardware_gates.results)


def test_failed_gate_plan_exposes_blockers() -> None:
    result = v8f_context(resolved=True, evidence_mode="fail")[-1]
    assert result.hardware_gates.blockers


def test_hardware_evidence_is_immutable() -> None:
    model = v8f_context(resolved=True)[-1].wctd_models.primary_model
    item = passing_hardware_evidence(model)[0]
    with pytest.raises(FrozenInstanceError):
        item.passed = False


def test_invalid_gate_model_type_is_rejected() -> None:
    with pytest.raises(WavetableContractError):
        evaluate_hardware_gates(object())


def test_invalid_factory_policy_boolean_is_rejected() -> None:
    with pytest.raises(WavetableContractError):
        FactoryStylePolicy(enabled=1)
