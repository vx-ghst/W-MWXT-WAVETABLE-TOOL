from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.compliance import (
    CodeV8PreflightAnalysis,
    PreV8DecisionPlan,
    PreV8LinkError,
    PreV8ReadinessStatus,
    PreV8SourceChain,
    assemble_code_v8_preflight,
    assemble_pre_v8_decision_plan,
    assemble_pre_v8_source_chain,
)

from v8f_helpers import decision_components, digest, source_components


def build_source_chain(*, full: bool = True) -> PreV8SourceChain:
    data = source_components(with_v7_chain=full)
    return assemble_pre_v8_source_chain(
        data["audio"],
        data["code_v6"],
        data["projection"],
        xt_trajectory=data.get("trajectory"),
        xt_qc=data.get("qc"),
        xt_hardware_package=data.get("package"),
    )


def build_decision_plan(*, rejected: bool = False, wave_count: int = 4) -> PreV8DecisionPlan:
    data = decision_components(rejected=rejected, wave_count=wave_count)
    return assemble_pre_v8_decision_plan(
        data["code_v6"],
        data["extension"],
        data["behavior"],
        data["regions"],
        data["formants"],
        data["evolution"],
        data["perceptual"],
        data["musical"],
        data["mode"],
        data["profile"],
        data["optimization"],
        data["repair"],
    )


def test_source_chain_verifies_v3_through_v7_links() -> None:
    chain = build_source_chain(full=True)
    assert chain.sample_rate == 16000
    assert chain.sample_count == 128
    assert chain.xt_trajectory_sha256 == digest("trajectory")
    assert chain.xt_qc_sha256 == digest("qc")
    assert chain.xt_hardware_package_sha256 == digest("package")
    assert len(chain.analysis_sha256) == 64


def test_source_chain_accepts_projection_only_v7_link() -> None:
    chain = build_source_chain(full=False)
    assert chain.xt_trajectory_sha256 is None
    assert chain.xt_qc_sha256 is None
    assert chain.xt_hardware_package_sha256 is None


def test_source_chain_serialization_is_deterministic() -> None:
    left = build_source_chain()
    right = build_source_chain()
    assert left == right
    assert left.to_dict() == right.to_dict()
    assert left.analysis_sha256 == right.analysis_sha256


@pytest.mark.parametrize("field", ["sample_rate", "sample_count", "sample_sha256"])
def test_source_chain_rejects_v3_v6_identity_mismatch(field: str) -> None:
    data = source_components()
    if field == "sample_rate":
        data["code_v6"].sample_rate += 1
    elif field == "sample_count":
        data["code_v6"].sample_count += 1
    else:
        data["code_v6"].sample_sha256 = digest("wrong")
    with pytest.raises(PreV8LinkError, match="V3 and V6"):
        assemble_pre_v8_source_chain(
            data["audio"], data["code_v6"], data["projection"]
        )


def test_source_chain_rejects_projection_v6_mismatch() -> None:
    data = source_components()
    data["projection"].source_code_v6_analysis_sha256 = digest("wrong")
    with pytest.raises(PreV8LinkError, match="projection"):
        assemble_pre_v8_source_chain(
            data["audio"], data["code_v6"], data["projection"]
        )


def test_source_chain_rejects_projection_wave_set_mismatch() -> None:
    data = source_components()
    data["projection"].source_reconstructed_wave_set_sha256 = digest("wrong")
    with pytest.raises(PreV8LinkError, match="reconstructed-wave"):
        assemble_pre_v8_source_chain(
            data["audio"], data["code_v6"], data["projection"]
        )


def test_source_chain_rejects_qc_without_trajectory() -> None:
    data = source_components()
    with pytest.raises(PreV8LinkError, match="without a trajectory"):
        assemble_pre_v8_source_chain(
            data["audio"],
            data["code_v6"],
            data["projection"],
            xt_qc=data["qc"],
        )


def test_source_chain_rejects_package_without_qc() -> None:
    data = source_components()
    with pytest.raises(PreV8LinkError, match="without trajectory and QC"):
        assemble_pre_v8_source_chain(
            data["audio"],
            data["code_v6"],
            data["projection"],
            xt_trajectory=data["trajectory"],
            xt_hardware_package=data["package"],
        )


@pytest.mark.parametrize(
    "component,field",
    [
        ("extension", "signal_analysis_sha256"),
        ("behavior", "signal_extension_analysis_sha256"),
        ("regions", "segmentation_analysis_sha256"),
        ("formants", "spectral_analysis_sha256"),
        ("evolution", "harmonic_perceptual_analysis_sha256"),
        ("perceptual", "formant_analysis_sha256"),
        ("musical", "perceptual_feature_sha256"),
        ("mode", "musical_classification_sha256"),
        ("profile", "mode_decision_sha256"),
    ],
)
def test_decision_plan_rejects_broken_component_link(component: str, field: str) -> None:
    data = decision_components()
    setattr(data[component], field, digest("wrong-link"))
    with pytest.raises(PreV8LinkError, match="Invalid pre-V8 link"):
        assemble_pre_v8_decision_plan(
            data["code_v6"],
            data["extension"],
            data["behavior"],
            data["regions"],
            data["formants"],
            data["evolution"],
            data["perceptual"],
            data["musical"],
            data["mode"],
            data["profile"],
            data["optimization"],
            data["repair"],
        )


def test_decision_plan_links_every_v8_0_component() -> None:
    plan = build_decision_plan(wave_count=61)
    assert plan.mode_status == "selected"
    assert plan.selected_mode == "stable_cycle"
    assert plan.selected_profile == "pad"
    assert plan.optimized_wave_count == 61
    assert plan.repaired_wave_count == 61
    assert plan.ready_for_v8 is True
    assert len(plan.analysis_sha256) == 64


def test_decision_plan_preserves_explicit_source_rejection() -> None:
    plan = build_decision_plan(rejected=True)
    assert plan.mode_status == "rejected"
    assert plan.selected_mode is None
    assert plan.ready_for_v8 is False
    assert plan.warnings == ("source rejected",)


def test_decision_plan_rejects_profile_definition_mismatch() -> None:
    data = decision_components()
    data["optimization"].profile = SimpleNamespace(analysis_sha256=digest("other"))
    with pytest.raises(PreV8LinkError, match="profile disagrees"):
        assemble_pre_v8_decision_plan(
            data["code_v6"],
            data["extension"],
            data["behavior"],
            data["regions"],
            data["formants"],
            data["evolution"],
            data["perceptual"],
            data["musical"],
            data["mode"],
            data["profile"],
            data["optimization"],
            data["repair"],
        )


def test_decision_plan_rejects_wave_count_mismatch() -> None:
    data = decision_components(wave_count=4)
    data["repair"].entries = data["repair"].entries[:-1]
    with pytest.raises(PreV8LinkError, match="wave counts must match"):
        assemble_pre_v8_decision_plan(
            data["code_v6"],
            data["extension"],
            data["behavior"],
            data["regions"],
            data["formants"],
            data["evolution"],
            data["perceptual"],
            data["musical"],
            data["mode"],
            data["profile"],
            data["optimization"],
            data["repair"],
        )


def test_ready_preflight_has_zero_debt_and_no_blockers() -> None:
    result = assemble_code_v8_preflight(build_source_chain(), build_decision_plan())
    assert result.status is PreV8ReadinessStatus.READY
    assert result.blockers == ()
    assert result.compliance_closure.zero_required_debt is True
    assert result.compliance_closure.supported_count == 62
    assert result.to_dict()["boundaries"]["transmits_midi"] is False


def test_rejected_source_preflight_is_explicit_not_fallback() -> None:
    result = assemble_code_v8_preflight(
        build_source_chain(), build_decision_plan(rejected=True)
    )
    assert result.status is PreV8ReadinessStatus.REJECTED
    assert len(result.blockers) == 1
    assert "no hidden fallback" in result.blockers[0]


def test_preflight_json_is_deterministic_and_nan_safe() -> None:
    left = assemble_code_v8_preflight(build_source_chain(), build_decision_plan())
    right = assemble_code_v8_preflight(build_source_chain(), build_decision_plan())
    assert left.to_json() == right.to_json()
    assert left.analysis_sha256 == right.analysis_sha256
    assert "NaN" not in left.to_json()
    assert left.to_json().endswith("\n")


def test_preflight_rejects_sample_identity_disagreement() -> None:
    chain = build_source_chain()
    plan = replace(build_decision_plan(), sample_sha256=digest("other-sample"))
    with pytest.raises(PreV8LinkError, match="sample identity"):
        assemble_code_v8_preflight(chain, plan)


def test_preflight_model_rejects_ready_with_blocker() -> None:
    valid = assemble_code_v8_preflight(build_source_chain(), build_decision_plan())
    with pytest.raises(PreV8LinkError, match="ready preflight"):
        CodeV8PreflightAnalysis(
            schema_version=valid.schema_version,
            tool_version=valid.tool_version,
            source_chain=valid.source_chain,
            decision_plan=valid.decision_plan,
            compliance_closure=valid.compliance_closure,
            status=PreV8ReadinessStatus.READY,
            blockers=("unexpected",),
            reason="invalid",
        )


def test_source_chain_model_rejects_invalid_hash() -> None:
    chain = build_source_chain()
    with pytest.raises(PreV8LinkError):
        replace(chain, sample_sha256="invalid")


def test_decision_plan_model_rejects_empty_wave_set() -> None:
    plan = build_decision_plan()
    with pytest.raises(PreV8LinkError):
        replace(plan, optimized_wave_count=0, repaired_wave_count=0)
