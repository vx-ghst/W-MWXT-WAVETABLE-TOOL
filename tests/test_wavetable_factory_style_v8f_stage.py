from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from v8f_materialization_helpers import build_v8e_context, v8f_context

from w_mwxt_wavetable_tool.wavetable.factory_style import (
    DEFAULT_FACTORY_STYLE_POLICY,
    FACTORY_STYLE_SCHEMA_VERSION,
    FactoryStyleAction,
    FactoryStylePolicy,
    FactoryStyleStatus,
    apply_factory_style,
)
from w_mwxt_wavetable_tool.wavetable.models import WavetableContractError


def test_factory_style_schema_version_is_one() -> None:
    assert FACTORY_STYLE_SCHEMA_VERSION == 1


def test_default_policy_is_enabled_but_request_controlled() -> None:
    assert DEFAULT_FACTORY_STYLE_POLICY.enabled is True
    request, _, _, _, v8e = build_v8e_context(factory_style=False)
    result = apply_factory_style(request, v8e)
    assert result.status is FactoryStyleStatus.COMPLETE
    assert result.applied is False


def test_factory_style_request_activates_shaping() -> None:
    *_, result = v8f_context(factory_style=True)
    assert result.factory_style.applied is True
    assert result.factory_style.primary_variant.changed_positions


def test_disabled_policy_prevents_shaping_even_when_requested() -> None:
    request, _, _, _, v8e = build_v8e_context(factory_style=True)
    result = apply_factory_style(request, v8e, FactoryStylePolicy(enabled=False))
    assert result.applied is False
    assert result.primary_variant.changed_positions == ()


def test_noop_policy_prevents_integer_changes() -> None:
    request, _, _, _, v8e = build_v8e_context(factory_style=True)
    result = apply_factory_style(
        request,
        v8e,
        FactoryStylePolicy(smoothing_passes=0, maximum_sample_delta=0),
    )
    assert result.primary_variant.changed_positions == ()


def test_factory_style_preserves_all_protected_slots_exactly() -> None:
    request, _, _, _, v8e = build_v8e_context(factory_style=True)
    result = apply_factory_style(request, v8e)
    source = {slot.position: slot for slot in v8e.primary_variant.build.slots}
    styled = {slot.position: slot for slot in result.primary_variant.build.slots}
    for decision in result.primary_variant.decisions:
        if decision.protected:
            assert styled[decision.position].stored_samples == source[decision.position].stored_samples
            assert decision.changed is False
            assert decision.action is FactoryStyleAction.PRESERVE_PROTECTED


def test_factory_style_changes_only_transition_slots() -> None:
    request, _, _, _, v8e = build_v8e_context(factory_style=True)
    result = apply_factory_style(request, v8e)
    build = result.primary_variant.build
    for position in result.primary_variant.changed_positions:
        assert build.slots[position].transition is True
        assert build.slots[position].locked is False
        assert build.slots[position].structural is False


def test_factory_style_sample_delta_respects_policy_bound() -> None:
    policy = FactoryStylePolicy(maximum_sample_delta=5)
    request, _, _, _, v8e = build_v8e_context(factory_style=True)
    result = apply_factory_style(request, v8e, policy)
    assert all(item.maximum_sample_delta <= 5 for item in result.primary_variant.decisions)


def test_factory_style_keeps_safe_range() -> None:
    *_, result = v8f_context(factory_style=True)
    assert all(-127 <= sample <= 127 for slot in result.factory_style.primary_variant.build.slots for sample in slot.stored_samples)
    assert all(sample != -128 for slot in result.factory_style.primary_variant.build.slots for sample in slot.stored_samples)


def test_factory_style_keeps_61_slots_and_fixed_tail() -> None:
    request, _, _, _, v8e = build_v8e_context(factory_style=True)
    result = apply_factory_style(request, v8e)
    assert len(result.primary_variant.build.slots) == 61
    assert result.primary_variant.build.fixed_tail == request.fixed_tail


def test_factory_style_recomputes_linked_continuity() -> None:
    *_, result = v8f_context(factory_style=True)
    variant = result.factory_style.primary_variant
    assert variant.continuity.build_sha256 == variant.build.analysis_sha256
    assert len(variant.continuity.transitions) == 60


def test_factory_style_decisions_cover_every_position() -> None:
    *_, result = v8f_context(factory_style=True)
    decisions = result.factory_style.primary_variant.decisions
    assert tuple(item.position for item in decisions) == tuple(range(61))


def test_factory_style_hash_is_deterministic() -> None:
    request, _, _, _, v8e = build_v8e_context(factory_style=True)
    left = apply_factory_style(request, v8e)
    right = apply_factory_style(request, v8e)
    assert left.analysis_sha256 == right.analysis_sha256
    assert left.to_json() == right.to_json()


def test_factory_style_models_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        DEFAULT_FACTORY_STYLE_POLICY.enabled = False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"smoothing_passes": -1},
        {"smoothing_passes": 5},
        {"smoothing_strength": -0.1},
        {"smoothing_strength": 1.1},
        {"neighbor_blend": -0.1},
        {"neighbor_blend": 1.1},
        {"maximum_sample_delta": -1},
        {"maximum_sample_delta": 128},
        {"continuity_tolerance": -0.1},
        {"continuity_tolerance": 1.1},
    ],
)
def test_factory_style_policy_rejects_invalid_values(kwargs) -> None:
    with pytest.raises(WavetableContractError):
        FactoryStylePolicy(**kwargs)


def test_factory_style_rejects_unlinked_request() -> None:
    request, _, _, _, v8e = build_v8e_context(factory_style=True)
    altered = replace(request, sample_count=request.sample_count + 1)
    with pytest.raises(WavetableContractError, match="does not link"):
        apply_factory_style(altered, v8e)


def test_factory_style_pass_through_preserves_build_hash() -> None:
    request, _, _, _, v8e = build_v8e_context(factory_style=False)
    result = apply_factory_style(request, v8e)
    assert result.primary_variant.build.analysis_sha256 == v8e.primary_variant.build.analysis_sha256
