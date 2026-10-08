from __future__ import annotations

import json

import pytest

from v8k_helpers import pending_v8k, write_campaign

from w_mwxt_wavetable_tool import (
    V8KHardwareCampaignEvidence,
    V8KHardwareGateStatus,
    V8KHardwareStep,
    build_code_v8k,
    load_v8k_hardware_campaign,
)


def test_no_campaign_keeps_hardware_pending_and_sparse_disabled() -> None:
    result = pending_v8k()
    assert result.hardware_report.status is V8KHardwareGateStatus.PENDING
    assert result.hardware_report.sparse_enabled is False
    assert result.hardware_report.v8_scope_status == "PENDING_REAL_HARDWARE"


def test_file_backed_complete_campaign_passes_all_18_steps(tmp_path) -> None:
    pending = pending_v8k()
    evidence = write_campaign(tmp_path, pending)
    from v8k_helpers import v8k_inputs
    accepted = build_code_v8k(*v8k_inputs(), hardware_evidence=evidence)
    assert accepted.hardware_report.status is V8KHardwareGateStatus.PASS
    assert accepted.hardware_report.passed_steps == tuple(V8KHardwareStep)
    assert accepted.hardware_report.sparse_enabled is True
    assert accepted.hardware_report.restore_exact_pass is True
    assert accepted.hardware_report.v8_scope_status == "V8_SCOPE_PASS_V10_OPEN"


def test_failed_real_step_fails_campaign_and_keeps_sparse_disabled(tmp_path) -> None:
    pending = pending_v8k()
    evidence = write_campaign(tmp_path, pending, fail_step=V8KHardwareStep.SLOW_SWEEP.value)
    from v8k_helpers import v8k_inputs
    failed = build_code_v8k(*v8k_inputs(), hardware_evidence=evidence)
    assert failed.hardware_report.status is V8KHardwareGateStatus.FAIL
    assert V8KHardwareStep.SLOW_SWEEP in failed.hardware_report.failed_steps
    assert failed.hardware_report.sparse_enabled is False


def test_package_hash_mismatch_fails_campaign(tmp_path) -> None:
    pending = pending_v8k()
    evidence = write_campaign(tmp_path, pending, wrong_dense_hash=True)
    from v8k_helpers import v8k_inputs
    failed = build_code_v8k(*v8k_inputs(), hardware_evidence=evidence)
    assert failed.hardware_report.status is V8KHardwareGateStatus.FAIL
    assert any("Dense package" in item for item in failed.hardware_report.blockers)


def test_loader_rejects_tampered_artifact(tmp_path) -> None:
    pending = pending_v8k()
    write_campaign(tmp_path, pending)
    target = next((tmp_path / "evidence").glob("*.txt"))
    target.write_text("tampered", encoding="utf-8")
    with pytest.raises(Exception, match="hash mismatch"):
        load_v8k_hardware_campaign(tmp_path)


def test_in_memory_unverified_evidence_cannot_close_gate() -> None:
    with pytest.raises(Exception, match="verified artifacts|verified from real files"):
        V8KHardwareCampaignEvidence(
            schema_version=1,
            campaign_id="synthetic",
            device_model="Waldorf Microwave XT",
            os_version="2.33",
            dense_package_sha256="1" * 64,
            sparse_package_sha256="2" * 64,
            inventory_sha256="3" * 64,
            empty_signature_sha256=None,
            manifest_sha256="4" * 64,
            artifacts=(),
            steps=(),
            verified_from_files=False,
            reason="Synthetic evidence must not pass.",
        )
