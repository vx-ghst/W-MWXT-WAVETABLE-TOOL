from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from v8f_materialization_helpers import (
    allocation_map,
    build_v8e_context,
    failing_hardware_evidence,
    passing_hardware_evidence,
    v8f_context,
)

from w_mwxt_wavetable_tool.wavetable.factory_style import apply_factory_style
from w_mwxt_wavetable_tool.wavetable.hardware_gate import (
    HARDWARE_GATE_SCHEMA_VERSION,
    CodeV8FStatus,
    HardwareGateEvidence,
    HardwareGateKind,
    HardwareGatePlanStatus,
    HardwareGateResultStatus,
    default_hardware_gate_requirements,
    evaluate_hardware_gates,
)
from w_mwxt_wavetable_tool.wavetable.models import WavetableContractError
from w_mwxt_wavetable_tool.wavetable.wctd import materialize_wctd_models


def _resolved_model():
    request, _, _, _, v8e = build_v8e_context()
    factory = apply_factory_style(request, v8e)
    return materialize_wctd_models(factory, allocation_map(factory)).primary_model


def test_hardware_gate_schema_version_is_one() -> None:
    assert HARDWARE_GATE_SCHEMA_VERSION == 1


def test_exactly_six_hardware_requirements_exist() -> None:
    requirements = default_hardware_gate_requirements()
    assert len(requirements) == 6
    assert {item.kind for item in requirements} == set(HardwareGateKind)


def test_unresolved_model_blocks_all_gates_without_claiming_failure() -> None:
    *_, result = v8f_context(resolved=False)
    assert result.status is CodeV8FStatus.READY_FOR_HARDWARE
    assert result.hardware_gates.status is HardwareGatePlanStatus.PENDING
    assert all(item.status is HardwareGateResultStatus.BLOCKED for item in result.hardware_gates.results)
    assert result.hardware_accepted is False


def test_resolved_model_leaves_all_gates_pending_without_evidence() -> None:
    *_, result = v8f_context(resolved=True)
    assert result.status is CodeV8FStatus.READY_FOR_HARDWARE
    assert all(item.status is HardwareGateResultStatus.PENDING for item in result.hardware_gates.results)


def test_passing_evidence_accepts_all_six_gates() -> None:
    *_, result = v8f_context(resolved=True, evidence_mode="pass")
    assert result.status is CodeV8FStatus.HARDWARE_ACCEPTED
    assert result.hardware_gates.status is HardwareGatePlanStatus.ACCEPTED
    assert result.hardware_accepted is True
    assert all(item.status is HardwareGateResultStatus.PASS for item in result.hardware_gates.results)


def test_explicit_failure_never_claims_acceptance() -> None:
    *_, result = v8f_context(resolved=True, evidence_mode="fail")
    assert result.status is CodeV8FStatus.HARDWARE_FAILED
    assert result.hardware_gates.status is HardwareGatePlanStatus.FAILED
    assert result.hardware_accepted is False
    assert any(item.status is HardwareGateResultStatus.FAIL for item in result.hardware_gates.results)


def test_tail_requirement_covers_positions_60_to_63() -> None:
    requirement = next(item for item in default_hardware_gate_requirements() if item.kind is HardwareGateKind.TAIL_POSITIONS_60_63)
    assert requirement.required_positions == (60, 61, 62, 63)


def test_readback_requirement_covers_all_64_positions() -> None:
    requirement = next(item for item in default_hardware_gate_requirements() if item.kind is HardwareGateKind.READ_BACK)
    assert requirement.required_positions == tuple(range(64))
    assert requirement.minimum_observation_count == 64


def test_mismatched_reference_fails_even_if_evidence_says_pass() -> None:
    model = _resolved_model()
    evidence = list(passing_hardware_evidence(model))
    first = evidence[0]
    evidence[0] = replace(first, observed_references=(first.observed_references[0] + 1, first.observed_references[1]))
    plan = evaluate_hardware_gates(model, evidence)
    assert plan.status is HardwareGatePlanStatus.FAILED
    assert plan.results[0].status is HardwareGateResultStatus.FAIL
    assert "reference mismatch" in " ".join(plan.results[0].blockers)


def test_readback_hash_mismatch_fails() -> None:
    model = _resolved_model()
    evidence = list(passing_hardware_evidence(model))
    evidence[-1] = replace(evidence[-1], observed_reference_payload_sha256="0" * 64)
    plan = evaluate_hardware_gates(model, evidence)
    assert plan.results[-1].status is HardwareGateResultStatus.FAIL


def test_unknown_evidence_id_is_rejected() -> None:
    model = _resolved_model()
    item = passing_hardware_evidence(model)[0]
    with pytest.raises(WavetableContractError, match="unknown"):
        evaluate_hardware_gates(model, (replace(item, gate_id="unknown"),))


def test_duplicate_evidence_ids_are_rejected() -> None:
    model = _resolved_model()
    item = passing_hardware_evidence(model)[0]
    with pytest.raises(WavetableContractError, match="unique"):
        evaluate_hardware_gates(model, (item, item))


def test_hardware_models_are_frozen() -> None:
    plan = evaluate_hardware_gates(_resolved_model())
    with pytest.raises(FrozenInstanceError):
        plan.status = HardwareGatePlanStatus.ACCEPTED


def test_hardware_gate_hash_is_deterministic() -> None:
    model = _resolved_model()
    evidence = passing_hardware_evidence(model)
    assert evaluate_hardware_gates(model, evidence).analysis_sha256 == evaluate_hardware_gates(model, evidence).analysis_sha256


def test_hardware_gate_json_declares_no_midi_or_sysex() -> None:
    plan = evaluate_hardware_gates(_resolved_model())
    data = plan.to_dict()["boundaries"]
    assert data["generates_sysex"] is False
    assert data["opens_midi_port"] is False
    assert data["transmits_midi"] is False
    assert data["claims_hardware_acceptance_without_evidence"] is False


@pytest.mark.parametrize("passed", [True, False])
def test_evidence_requires_reference_alignment(passed: bool) -> None:
    with pytest.raises(WavetableContractError, match="align"):
        HardwareGateEvidence(
            HARDWARE_GATE_SCHEMA_VERSION,
            "v8f-known-reference-pair",
            "1" * 64,
            passed,
            (0, 1),
            (1000,),
            None,
            ("evidence",),
            "Invalid alignment.",
        )
