from __future__ import annotations

import json
from pathlib import Path

import pytest

from w_mwxt_wavetable_tool.constants import DumpType
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.message import SysExMessage
from w_mwxt_wavetable_tool.models import UserWave
from w_mwxt_wavetable_tool.xt import (
    XtGatePattern,
    XtGateStatus,
    XtGateVerdict,
    XtReconstructionGatePlan,
    XtReconstructionHypothesis,
    analyze_xt_reconstruction_gate,
    build_xt_reconstruction_gate,
    generate_xt_gate_probes,
    reconstruct_probe,
)


def _baseline(start: int = 1247, device_id: int = 0) -> DumpFile:
    messages = []
    for offset in range(3):
        samples = tuple(((index * (offset + 5) + offset * 17) % 256) - 128 for index in range(64))
        messages.append(UserWave(device_id, start + offset, samples).to_message())
    return DumpFile(tuple(messages))


def _observations(plan, hypothesis):
    return {
        probe.target_wave_number: reconstruct_probe(probe, hypothesis)
        for probe in plan.probes
    }


def test_generate_probes_are_deterministic_discriminating_and_complete() -> None:
    left = generate_xt_gate_probes(target_wave_start=1247, seed=1402)
    right = generate_xt_gate_probes(target_wave_start=1247, seed=1402)
    assert left == right
    assert tuple(probe.pattern for probe in left) == tuple(XtGatePattern)
    assert tuple(probe.target_wave_number for probe in left) == (1247, 1248, 1249)
    for probe in left:
        assert len(probe.stored_samples) == 64
        assert len(probe.requested_full_samples) == 128
        assert probe.requested_full_samples[:64] == probe.stored_samples
        requested_second = probe.requested_full_samples[64:]
        for hypothesis in XtReconstructionHypothesis:
            if hypothesis is XtReconstructionHypothesis.PRESERVE_REQUESTED_128:
                continue
            assert requested_second != reconstruct_probe(probe, hypothesis)[64:]


def test_build_produces_three_wavd_messages_restore_and_stable_manifest(tmp_path: Path) -> None:
    baseline = _baseline()
    build = build_xt_reconstruction_gate(baseline)
    assert build.ready_for_transmission
    assert len(build.probe_package.messages) == 3
    assert all(int(message.dump_type) == int(DumpType.USER_WAVE) for message in build.probe_package.messages)
    assert build.probe_package.to_bytes() != build.restore_bundle.to_bytes()
    assert DumpFile.from_bytes(build.probe_package.to_bytes()).to_bytes() == build.probe_package.to_bytes()
    plan = XtReconstructionGatePlan.from_json(build.plan.to_json())
    assert plan == build.plan
    assert plan.plan_sha256 == build.plan.plan_sha256

    paths = build.write(tmp_path)
    assert paths.probe_package.read_bytes() == build.probe_package.to_bytes()
    assert paths.restore_bundle.read_bytes() == build.restore_bundle.to_bytes()
    observation = json.loads(paths.observation_template_json.read_text(encoding="utf-8"))
    assert observation["gate_plan_sha256"] == build.plan.plan_sha256
    assert [item["target_wave_number"] for item in observation["cycles"]] == [1247, 1248, 1249]


def test_exact_readback_confirms_storage_but_keeps_reconstruction_pending() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    result = analyze_xt_reconstruction_gate(
        build.probe_package,
        build.probe_package,
        build.plan,
    )
    assert result.analysis.storage_passed
    assert result.analysis.status is XtGateStatus.PENDING_OBSERVATION
    assert result.analysis.verdict is XtGateVerdict.PROTOCOL_STORAGE_CONFIRMED_RECONSTRUCTION_UNRESOLVED
    assert result.analysis.architecture_decision == "do_not_freeze_symmetry_optimizer"
    assert not result.analysis.hypothesis_scores


@pytest.mark.parametrize(
    ("hypothesis", "verdict", "architecture"),
    [
        (
            XtReconstructionHypothesis.PRESERVE_REQUESTED_128,
            XtGateVerdict.FULL_128_PRESERVED,
            "native_full_128",
        ),
        (
            XtReconstructionHypothesis.REVERSE_NEGATE_WRAP_I8,
            XtGateVerdict.SECOND_HALF_REVERSED_ANTISYMMETRIC_WRAP_I8,
            "stored_64_plus_explicit_derived_128",
        ),
        (
            XtReconstructionHypothesis.REVERSE_NEGATE_SATURATE_I8,
            XtGateVerdict.SECOND_HALF_REVERSED_ANTISYMMETRIC_SATURATE_I8,
            "stored_64_plus_explicit_derived_128",
        ),
    ],
)
def test_independent_full_cycle_observation_yields_unique_verdict(
    hypothesis, verdict, architecture
) -> None:
    build = build_xt_reconstruction_gate(_baseline())
    result = analyze_xt_reconstruction_gate(
        build.probe_package,
        build.probe_package,
        build.plan,
        observed_cycles=_observations(build.plan, hypothesis),
        observation_method="independent digital phase-aligned capture",
    )
    assert result.analysis.status is XtGateStatus.PASS
    assert result.analysis.verdict is verdict
    assert result.analysis.matched_hypotheses == (hypothesis,)
    assert result.analysis.architecture_decision == architecture


def test_changed_stored_sample_blocks_gate() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    messages = list(build.probe_package.messages)
    wave = UserWave.from_message(messages[1])
    changed = list(wave.stored_samples)
    changed[17] = -128 if changed[17] == 127 else changed[17] + 1
    messages[1] = UserWave(wave.device_id, wave.number, tuple(changed)).to_message()
    readback = DumpFile(tuple(messages))
    result = analyze_xt_reconstruction_gate(
        build.probe_package,
        readback,
        build.plan,
    )
    assert result.analysis.status is XtGateStatus.FAIL
    assert result.analysis.verdict is XtGateVerdict.READBACK_FAILED
    assert not result.analysis.storage_passed
    assert result.analysis.storage_evidence[1].differing_sample_indexes == (17,)


def test_unmodeled_observation_is_inconclusive_not_nearest_guess() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    observations = {
        probe.target_wave_number: tuple(float(value) for value in probe.stored_samples)
        + tuple(3.5 for _ in range(64))
        for probe in build.plan.probes
    }
    result = analyze_xt_reconstruction_gate(
        build.probe_package,
        build.probe_package,
        build.plan,
        observed_cycles=observations,
    )
    assert result.analysis.status is XtGateStatus.INCONCLUSIVE
    assert result.analysis.verdict is XtGateVerdict.NO_HYPOTHESIS_MATCH
    assert not result.analysis.matched_hypotheses


def test_manifest_rejects_tampering() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    data = build.plan.to_dict()
    data["probes"][0]["stored_samples"][0] += 1
    with pytest.raises(Exception):
        XtReconstructionGatePlan.from_dict(data)


def test_restore_bundle_verification_passes_and_detects_failure() -> None:
    from w_mwxt_wavetable_tool.xt import verify_xt_reconstruction_gate_restore

    build = build_xt_reconstruction_gate(_baseline())
    passed = verify_xt_reconstruction_gate_restore(
        build.restore_bundle, build.restore_bundle, build.plan
    )
    assert passed.analysis.status is XtGateStatus.PASS
    assert passed.analysis.verdict is XtGateVerdict.RESTORE_CONFIRMED

    messages = list(build.restore_bundle.messages)
    wave = UserWave.from_message(messages[0])
    changed = list(wave.stored_samples)
    changed[0] = -128 if changed[0] == 127 else changed[0] + 1
    messages[0] = UserWave(wave.device_id, wave.number, tuple(changed)).to_message()
    failed = verify_xt_reconstruction_gate_restore(
        build.restore_bundle, DumpFile(tuple(messages)), build.plan
    )
    assert failed.analysis.status is XtGateStatus.FAIL
    assert failed.analysis.verdict is XtGateVerdict.RESTORE_FAILED
