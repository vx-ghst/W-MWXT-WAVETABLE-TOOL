from dataclasses import FrozenInstanceError, replace
import json
import pytest

from v8g_helpers import rejected_v8d, v8g_context

from w_mwxt_wavetable_tool import CodeV8GStatus, build_code_v8g


def test_v8g_builds_61_slots_and_one_decision_per_interval():
    request, v8b, v8c, v8d, regions = v8g_context()
    result = build_code_v8g(request, v8b, v8c, v8d, regions)
    assert result.status is CodeV8GStatus.COMPLETE
    assert len(result.primary_variant.build.slots) == 61
    assert len(result.primary_variant.interval_decisions) == len(
        result.primary_variant.transition_map.intervals
    )


def test_each_interval_uses_exactly_the_selected_method():
    request, v8b, v8c, v8d, regions = v8g_context()
    result = build_code_v8g(request, v8b, v8c, v8d, regions)
    variant = result.primary_variant
    for plan, decision in zip(variant.transition_map.intervals, variant.interval_decisions):
        methods = {
            record.method
            for record in variant.transition_map.records
            if record.position in plan.open_positions
        }
        methods.discard(None)
        assert methods <= {decision.selected_method}


def test_v8g_boundaries_exclude_later_stages():
    request, v8b, v8c, v8d, regions = v8g_context()
    result = build_code_v8g(request, v8b, v8c, v8d, regions)
    boundaries = result.to_dict()["boundaries"]
    for key in (
        "applies_factory_style",
        "consolidates_physical_waves",
        "materializes_wctd",
        "allocates_xt_memory",
        "generates_sysex",
        "opens_midi_port",
        "transmits_midi",
    ):
        assert not boundaries[key]


def test_source_links_are_enforced():
    request, v8b, v8c, v8d, regions = v8g_context()
    with pytest.raises(ValueError):
        build_code_v8g(
            request,
            v8b,
            v8c,
            v8d,
            replace(regions, sample_sha256="e" * 64),
        )


def test_analysis_is_deterministic_frozen_and_json_canonical():
    request, v8b, v8c, v8d, regions = v8g_context()
    first = build_code_v8g(request, v8b, v8c, v8d, regions)
    second = build_code_v8g(request, v8b, v8c, v8d, regions)
    assert first.to_dict() == second.to_dict()
    assert json.loads(first.to_json()) == first.to_dict()
    with pytest.raises(FrozenInstanceError):
        first.reason = "mutated"


def test_rejected_v8d_exposes_no_partial_output():
    request, v8b, v8c, v8d, regions = v8g_context()
    result = build_code_v8g(request, v8b, v8c, rejected_v8d(v8d), regions)
    assert result.status is CodeV8GStatus.REJECTED
    assert result.slot_budget is None
    assert result.variants == ()
    assert result.primary_variant_id is None
    assert result.build_set is None
