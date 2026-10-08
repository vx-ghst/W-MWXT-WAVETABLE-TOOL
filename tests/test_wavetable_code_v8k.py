from __future__ import annotations

from dataclasses import replace

from v8k_helpers import pending_v8k, v8k_inputs, write_campaign

from w_mwxt_wavetable_tool import (
    AllocationProposalStatus,
    CodeV8KStatus,
    WctdMode,
    build_code_v8k,
)


def test_code_v8k_builds_dense_and_sparse_candidate_without_hardware_claim() -> None:
    result = pending_v8k()
    assert result.status is CodeV8KStatus.READY_FOR_HARDWARE
    assert result.dense_package is not None
    assert result.sparse_package_candidate is not None
    assert result.active_package_mode is WctdMode.DENSE
    assert result.hardware_accepted is False
    payload = result.to_dict()
    assert payload["requirements"]["CDC-SYX-002"] == "implemented"
    assert payload["requirements"]["CDC-SYX-005"] == "implemented"
    assert payload["boundaries"]["offline_sysex_generated"] is True
    assert payload["boundaries"]["transmits_midi"] is False
    assert payload["boundaries"]["v8_l_started"] is False


def test_real_campaign_acceptance_enables_sparse_but_dense_remains_default(tmp_path) -> None:
    evidence = write_campaign(tmp_path)
    accepted = build_code_v8k(*v8k_inputs(), hardware_evidence=evidence)
    assert accepted.status is CodeV8KStatus.HARDWARE_ACCEPTED
    assert accepted.materialization.sparse_enabled is True
    assert accepted.active_package_mode is WctdMode.DENSE


def test_blocked_v8j_allocation_rejects_without_partial_outputs() -> None:
    v8i, v8j, fixed_tail, device = v8k_inputs()
    blocked_allocation = replace(
        v8j.allocation,
        status=AllocationProposalStatus.BLOCKED,
        assignments=(),
        contiguous=False,
        overwrite_wave_numbers=(),
        blockers=("synthetic capacity blocker",),
        reason="Synthetic blocked allocation.",
    )
    blocked_v8j = replace(v8j, allocation=blocked_allocation, warnings=v8j.warnings + ("synthetic capacity blocker",))
    result = build_code_v8k(v8i, blocked_v8j, fixed_tail, device)
    assert result.status is CodeV8KStatus.REJECTED
    assert result.materialization is None
    assert result.dense_package is None
    assert result.hardware_plan is None
    assert result.blockers


def test_code_v8k_is_deterministic() -> None:
    assert pending_v8k().analysis_sha256 == pending_v8k().analysis_sha256
