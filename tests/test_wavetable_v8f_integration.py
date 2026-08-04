from __future__ import annotations

from dataclasses import replace

import pytest

from v8f_materialization_helpers import build_v8e_context, v8f_context

from w_mwxt_wavetable_tool.wavetable.factory_style import FactoryStyleStatus
from w_mwxt_wavetable_tool.wavetable.hardware_gate import CodeV8FStatus, build_code_v8f
from w_mwxt_wavetable_tool.wavetable.models import WavetableContractError
from w_mwxt_wavetable_tool.wavetable.wctd import WctdMaterializationStatus


def test_v8f_default_result_is_ready_for_hardware() -> None:
    *_, result = v8f_context()
    assert result.status is CodeV8FStatus.READY_FOR_HARDWARE
    assert result.factory_style.status is FactoryStyleStatus.COMPLETE
    assert result.wctd_models.status is WctdMaterializationStatus.COMPLETE


def test_v8f_preserves_request_and_v8e_hash_links() -> None:
    request, _, _, _, v8e, result = v8f_context()
    assert result.request_sha256 == request.analysis_sha256
    assert result.v8e_analysis_sha256 == v8e.analysis_sha256
    assert result.factory_style.v8e_analysis_sha256 == v8e.analysis_sha256


def test_v8f_factory_style_flag_is_respected() -> None:
    *_, inactive = v8f_context(factory_style=False)
    *_, active = v8f_context(factory_style=True)
    assert inactive.factory_style.applied is False
    assert active.factory_style.applied is True


def test_v8f_factory_style_never_changes_fixed_tail() -> None:
    request, _, _, _, _, result = v8f_context(factory_style=True)
    assert result.factory_style.primary_variant.build.fixed_tail == request.fixed_tail
    assert tuple(item.reference for item in result.wctd_models.primary_model.fixed_tail_entries) == request.fixed_tail.references


def test_v8f_resolved_model_can_be_hardware_accepted() -> None:
    *_, result = v8f_context(resolved=True, evidence_mode="pass")
    assert result.status is CodeV8FStatus.HARDWARE_ACCEPTED
    assert result.wctd_models.primary_model.binary_ready is True


def test_v8f_without_evidence_cannot_claim_acceptance() -> None:
    *_, result = v8f_context(resolved=True)
    assert result.hardware_accepted is False
    assert result.status is CodeV8FStatus.READY_FOR_HARDWARE


def test_v8f_hash_and_json_are_deterministic() -> None:
    left = v8f_context(factory_style=True, resolved=True)[-1]
    right = v8f_context(factory_style=True, resolved=True)[-1]
    assert left.analysis_sha256 == right.analysis_sha256
    assert left.to_json() == right.to_json()


def test_v8f_primary_model_links_primary_factory_build() -> None:
    *_, result = v8f_context(factory_style=True)
    assert result.wctd_models.primary_model.build_sha256 == result.factory_style.primary_variant.build.analysis_sha256


def test_v8f_retains_ranked_variants() -> None:
    *_, result = v8f_context(requested_variants=3)
    assert len(result.factory_style.variants) == len(result.wctd_models.models)
    assert result.factory_style.primary_variant_id == result.wctd_models.primary_variant_id


def test_v8f_rejects_unlinked_request() -> None:
    request, _, _, _, v8e = build_v8e_context()
    altered = replace(request, sample_count=request.sample_count + 1)
    with pytest.raises(WavetableContractError, match="does not link"):
        build_code_v8f(altered, v8e)


def test_v8f_boundaries_defer_release_and_sysex() -> None:
    *_, result = v8f_context()
    boundaries = result.to_dict()["boundaries"]
    assert boundaries["serializes_complete_wctd_dump"] is False
    assert boundaries["generates_sysex"] is False
    assert boundaries["opens_midi_port"] is False
    assert boundaries["transmits_midi"] is False
    assert boundaries["completes_release"] is False


def test_v8f_uses_61_user_plus_three_fixed_positions() -> None:
    *_, result = v8f_context()
    model = result.wctd_models.primary_model
    assert len(model.user_entries) == 61
    assert len(model.fixed_tail_entries) == 3
    assert len(model.entries) == 64
