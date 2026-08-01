from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from w_mwxt_wavetable_tool.constants import DumpType
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.errors import HardwareValidationError
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
    verify_xt_reconstruction_gate_restore,
)


def _baseline(start: int = 1247) -> DumpFile:
    messages = tuple(
        UserWave(
            0,
            start + index,
            tuple(((sample * 13 + index * 29) % 255) - 127 for sample in range(64)),
        ).to_message()
        for index in range(3)
    )
    return DumpFile(messages)


def test_probe_set_is_deterministic_and_targets_three_consecutive_waves() -> None:
    first = generate_xt_gate_probes(target_wave_start=1247)
    second = generate_xt_gate_probes(target_wave_start=1247)
    assert first == second
    assert tuple(probe.target_wave_number for probe in first) == (1247, 1248, 1249)
    assert tuple(probe.pattern for probe in first) == tuple(XtGatePattern)
    assert all(len(probe.stored_samples) == 64 for probe in first)


def test_offset_binary_probe_contains_the_documented_golden_vector() -> None:
    probes = generate_xt_gate_probes(target_wave_start=1247)
    golden = next(
        probe for probe in probes if probe.pattern is XtGatePattern.OFFSET_BINARY_GOLDEN
    )
    assert golden.stored_samples[:7] == (-128, -127, -1, 0, 1, 126, 127)
    raw = UserWave(0, golden.target_wave_number, golden.stored_samples).payload
    assert raw[:14] == bytes(
        (0x00, 0x00, 0x00, 0x01, 0x07, 0x0F, 0x08, 0x00, 0x08, 0x01, 0x0F, 0x0E, 0x0F, 0x0F)
    )


def test_build_creates_schema_2_probe_restore_and_hashed_manifest() -> None:
    baseline = _baseline()
    build = build_xt_reconstruction_gate(baseline)
    assert build.ready_for_transmission is True
    assert len(build.probe_package.messages) == 3
    assert len(build.restore_bundle.messages) == 3
    assert build.plan.schema_version == 2
    rendered = build.plan.to_dict()
    assert rendered["wire_sample_encoding"] == "offset_binary_msb_flipped"
    assert rendered["safe_optimizer_sample_range"] == [-127, 127]
    assert "second_half[n]" in rendered["documented_reconstruction_law"]
    assert XtReconstructionGatePlan.from_json(build.plan.to_json()) == build.plan


def test_schema_1_manifest_is_rejected() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    data = build.plan.to_dict()
    data["schema_version"] = 1
    data.pop("plan_sha256")
    with pytest.raises(HardwareValidationError, match="schema 2"):
        XtReconstructionGatePlan.from_json(json.dumps(data))


def test_exact_readback_passes_documented_law_with_edge_reservation() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    result = analyze_xt_reconstruction_gate(
        build.probe_package,
        DumpFile.from_bytes(build.probe_package.to_bytes()),
        build.plan,
    )
    assert result.analysis.status is XtGateStatus.PASS
    assert result.analysis.storage_passed is True
    assert result.analysis.verdict is (
        XtGateVerdict.DOCUMENTED_RECONSTRUCTION_STORAGE_CONFIRMED_EDGE_UNRESOLVED
    )
    assert result.analysis.negative_full_scale_status == "pending_hardware_characterization"
    assert result.analysis.v7_b_allowed_under_safe_range is True


def test_changed_readback_fails_before_reconstruction_analysis() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    first = UserWave.from_message(build.probe_package.messages[0])
    changed = replace(
        first,
        stored_samples=(first.stored_samples[0] + 1,) + first.stored_samples[1:],
    ).to_message()
    readback = DumpFile((changed,) + build.probe_package.messages[1:])
    result = analyze_xt_reconstruction_gate(
        build.probe_package, readback, build.plan
    )
    assert result.analysis.status is XtGateStatus.FAIL
    assert result.analysis.verdict is XtGateVerdict.READBACK_FAILED
    assert result.analysis.v7_b_allowed_under_safe_range is False


def test_unique_wrap_observation_characterizes_negative_full_scale() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    observed = {
        probe.target_wave_number: reconstruct_probe(
            probe,
            XtReconstructionHypothesis.REVERSE_NEGATE_WRAP_I8,
        )
        for probe in build.plan.probes
    }
    result = analyze_xt_reconstruction_gate(
        build.probe_package,
        build.probe_package,
        build.plan,
        observed_cycles=observed,
        observation_method="independent digital phase-aligned capture",
    )
    assert result.analysis.status is XtGateStatus.PASS
    assert result.analysis.verdict is (
        XtGateVerdict.DOCUMENTED_RECONSTRUCTION_AND_EDGE_WRAP_I8_CONFIRMED
    )
    assert result.analysis.negative_full_scale_status == "wrap_i8_to_-128"
    assert result.analysis.matched_hypotheses == (
        XtReconstructionHypothesis.REVERSE_NEGATE_WRAP_I8,
    )


def test_unmatched_observation_is_inconclusive_and_blocks_v7_b() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    observed = {
        probe.target_wave_number: (0,) * 128 for probe in build.plan.probes
    }
    result = analyze_xt_reconstruction_gate(
        build.probe_package,
        build.probe_package,
        build.plan,
        observed_cycles=observed,
    )
    assert result.analysis.status is XtGateStatus.INCONCLUSIVE
    assert result.analysis.verdict is (
        XtGateVerdict.DOCUMENTED_RECONSTRUCTION_OBSERVATION_CONFLICT
    )
    assert result.analysis.v7_b_allowed_under_safe_range is False


def test_restore_verification_passes_and_detects_failure() -> None:
    build = build_xt_reconstruction_gate(_baseline())
    passed = verify_xt_reconstruction_gate_restore(
        build.restore_bundle, build.restore_bundle, build.plan
    )
    assert passed.analysis.verdict is XtGateVerdict.RESTORE_CONFIRMED

    first = UserWave.from_message(build.restore_bundle.messages[0])
    changed_value = -127 if first.stored_samples[0] == 127 else first.stored_samples[0] + 1
    changed = replace(
        first,
        stored_samples=(changed_value,) + first.stored_samples[1:],
    ).to_message()
    failed = verify_xt_reconstruction_gate_restore(
        build.restore_bundle,
        DumpFile((changed,) + build.restore_bundle.messages[1:]),
        build.plan,
    )
    assert failed.analysis.verdict is XtGateVerdict.RESTORE_FAILED


def test_build_write_outputs_are_reopenable(tmp_path: Path) -> None:
    build = build_xt_reconstruction_gate(_baseline())
    paths = build.write(tmp_path)
    assert DumpFile.from_bytes(paths.probe_package.read_bytes()).to_bytes() == (
        build.probe_package.to_bytes()
    )
    assert DumpFile.from_bytes(paths.restore_bundle.read_bytes()).to_bytes() == (
        build.restore_bundle.to_bytes()
    )
    assert XtReconstructionGatePlan.from_json(
        paths.manifest_json.read_text(encoding="utf-8")
    ) == build.plan
    observation = json.loads(paths.observation_template_json.read_text(encoding="utf-8"))
    assert observation["schema_version"] == 2
