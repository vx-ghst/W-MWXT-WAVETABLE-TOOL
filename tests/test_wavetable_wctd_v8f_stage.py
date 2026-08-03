from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from v8f_materialization_helpers import allocation_map, build_v8e_context

from w_mwxt_wavetable_tool.wavetable.factory_style import apply_factory_style
from w_mwxt_wavetable_tool.wavetable.models import INTERPOLATED_WAVE_REFERENCE, WavetableContractError
from w_mwxt_wavetable_tool.wavetable.wctd import (
    WCTD_MODEL_SCHEMA_VERSION,
    WctdMaterializationStatus,
    WctdReferenceKind,
    materialize_wctd_models,
    materialize_wctd_reference_model,
)


def _factory(factory_style: bool = False):
    request, _, _, _, v8e = build_v8e_context(factory_style=factory_style)
    return request, apply_factory_style(request, v8e)


def test_wctd_schema_version_is_one() -> None:
    assert WCTD_MODEL_SCHEMA_VERSION == 1


def test_logical_wctd_model_has_exactly_64_entries() -> None:
    _, factory = _factory()
    result = materialize_wctd_models(factory)
    assert result.status is WctdMaterializationStatus.COMPLETE
    assert len(result.primary_model.entries) == 64
    assert tuple(item.position for item in result.primary_model.entries) == tuple(range(64))


def test_logical_model_has_61_user_and_three_tail_entries() -> None:
    _, factory = _factory()
    model = materialize_wctd_models(factory).primary_model
    assert len(model.user_entries) == 61
    assert len(model.fixed_tail_entries) == 3
    assert all(item.kind is WctdReferenceKind.USER_SLOT for item in model.user_entries)
    assert all(item.kind is WctdReferenceKind.FIXED_TAIL for item in model.fixed_tail_entries)


def test_unallocated_user_references_are_explicitly_unresolved() -> None:
    _, factory = _factory()
    model = materialize_wctd_models(factory).primary_model
    assert model.binary_ready is False
    assert model.unresolved_user_positions == tuple(range(61))
    assert all(item.reference == INTERPOLATED_WAVE_REFERENCE for item in model.user_entries)
    assert all(item.resolved is False for item in model.user_entries)


def test_fixed_tail_references_are_preserved_exactly() -> None:
    request, factory = _factory()
    model = materialize_wctd_models(factory).primary_model
    assert tuple(item.reference for item in model.fixed_tail_entries) == request.fixed_tail.references
    assert all(item.resolved for item in model.fixed_tail_entries)
    assert model.source_wctd_sha256 == request.fixed_tail.source_wctd_sha256


def test_resolved_allocation_makes_model_binary_ready() -> None:
    _, factory = _factory()
    allocations = allocation_map(factory)
    model = materialize_wctd_models(factory, allocations).primary_model
    assert model.binary_ready is True
    assert model.unresolved_user_positions == ()
    assert tuple(item.reference for item in model.user_entries) == tuple(range(1000, 1061))


def test_reference_payload_contains_128_bytes() -> None:
    _, factory = _factory()
    model = materialize_wctd_models(factory, allocation_map(factory)).primary_model
    assert len(model.reference_payload()) == 128


def test_reference_payload_hash_is_deterministic() -> None:
    _, factory = _factory()
    allocations = allocation_map(factory)
    left = materialize_wctd_models(factory, allocations).primary_model
    right = materialize_wctd_models(factory, allocations).primary_model
    assert left.reference_payload_sha256 == right.reference_payload_sha256
    assert left.analysis_sha256 == right.analysis_sha256


def test_every_user_entry_links_to_exact_build_slot() -> None:
    _, factory = _factory(factory_style=True)
    model = materialize_wctd_models(factory).primary_model
    build = factory.primary_variant.build
    for entry, slot in zip(model.user_entries, build.slots):
        assert entry.slot_sha256 == slot.slot_sha256
        assert entry.source_candidate_ids == slot.source_candidate_ids


def test_wctd_set_preserves_variant_count() -> None:
    request, _, _, _, v8e = build_v8e_context(requested_variants=3)
    factory = apply_factory_style(request, v8e)
    result = materialize_wctd_models(factory)
    assert len(result.models) == len(factory.variants)
    assert result.primary_variant_id == factory.primary_variant_id


def test_wctd_models_are_frozen() -> None:
    _, factory = _factory()
    model = materialize_wctd_models(factory).primary_model
    with pytest.raises(FrozenInstanceError):
        model.binary_ready = True


@pytest.mark.parametrize(
    "references",
    [
        (),
        tuple(range(60)),
        tuple(range(62)),
        tuple([1000] * 61),
        tuple(range(60)) + (0xFFFF,),
        tuple(range(60)) + (-1,),
        tuple(range(60)) + (0x10000,),
    ],
)
def test_invalid_user_allocations_are_rejected(references) -> None:
    _, factory = _factory()
    with pytest.raises(WavetableContractError):
        materialize_wctd_reference_model(factory.primary_variant.build, references)


def test_unknown_allocation_variant_is_rejected() -> None:
    _, factory = _factory()
    with pytest.raises(WavetableContractError, match="unknown variants"):
        materialize_wctd_models(factory, {"unknown": tuple(range(1000, 1061))})


def test_wctd_json_declares_no_sysex_or_memory_allocation() -> None:
    _, factory = _factory()
    data = materialize_wctd_models(factory).primary_model.to_dict()
    assert data["boundaries"]["serializes_complete_wctd_dump"] is False
    assert data["boundaries"]["generates_sysex"] is False
    assert data["boundaries"]["allocates_xt_memory"] is False


def test_wctd_rejects_incomplete_build() -> None:
    _, factory = _factory()
    build = replace(
        factory.primary_variant.build,
        status=factory.primary_variant.build.status.REJECTED,
        slots=(),
        blockers=("synthetic",),
        reason="Synthetic rejected build.",
    )
    with pytest.raises(WavetableContractError):
        materialize_wctd_reference_model(build)
