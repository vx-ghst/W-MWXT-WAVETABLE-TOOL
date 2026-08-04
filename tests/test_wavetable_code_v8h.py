from dataclasses import replace

from w_mwxt_wavetable_tool import (
    CodeV8HStatus,
    TransitionShapingPolicy,
    build_code_v8g,
    build_code_v8h,
)

from v8h_helpers import v8h_context


def test_factory_off_preserves_direct_v8g_result_byte_identically():
    request, v8b, v8c, v8d, regions = v8h_context(factory_style=False)
    v8g = build_code_v8g(request, v8b, v8c, v8d, regions)
    v8h = build_code_v8h(request, v8b, v8c, v8d, regions)
    assert v8h.status is CodeV8HStatus.COMPLETE
    assert v8h.factory_placement.applied is False
    assert v8h.transition_shaping.applied is False
    by_id = {item.variant_id: item.build.analysis_sha256 for item in v8g.variants}
    assert {item.variant_id: item.build.analysis_sha256 for item in v8h.variants} == by_id


def test_factory_placement_is_consumed_before_interpolation():
    request, v8b, v8c, v8d, regions = v8h_context()
    result = build_code_v8h(request, v8b, v8c, v8d, regions)
    assert result.status is CodeV8HStatus.COMPLETE
    factory_positions = {
        item.candidate_id: item.position
        for item in result.factory_placement.primary_variant.assignments
    }
    keyframe_positions = {
        slot.source_candidate_ids[0]: slot.position
        for slot in result.v8g_analysis.primary_variant.build.slots
        if len(slot.source_candidate_ids) == 1 and not slot.transition
    }
    for candidate_id, position in factory_positions.items():
        assert keyframe_positions[candidate_id] == position


def test_transition_shaping_requires_an_explicit_separate_request():
    request, v8b, v8c, v8d, regions = v8h_context()
    disabled = build_code_v8h(request, v8b, v8c, v8d, regions)
    enabled = build_code_v8h(
        request,
        v8b,
        v8c,
        v8d,
        regions,
        transition_shaping_policy=TransitionShapingPolicy(),
        transition_shaping_requested=True,
    )
    assert disabled.transition_shaping.applied is False
    assert enabled.transition_shaping.applied is True
    for source, shaped in zip(
        disabled.primary_variant.build.slots,
        enabled.primary_variant.build.slots,
    ):
        if source.locked or source.structural:
            assert shaped.stored_samples == source.stored_samples


def test_v8h_boundaries_exclude_later_stages_and_historical_claims():
    request, v8b, v8c, v8d, regions = v8h_context()
    result = build_code_v8h(request, v8b, v8c, v8d, regions)
    boundaries = result.to_dict()["boundaries"]
    assert boundaries["placement_precedes_interpolation"] is True
    assert boundaries["historical_waldorf_reconstruction_claim"] is False
    for name in (
        "consolidates_physical_waves",
        "materializes_wctd",
        "allocates_xt_memory",
        "generates_sysex",
        "opens_midi_port",
        "transmits_midi",
    ):
        assert boundaries[name] is False
