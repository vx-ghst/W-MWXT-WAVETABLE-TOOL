from __future__ import annotations

import dataclasses
import json

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    DeduplicationThresholds,
    DuplicateKind,
    WavetableContractError,
    analyze_candidate_deduplication,
    analyze_candidate_structure,
    analyze_wavetable_candidates,
)

from v8b_helpers import candidate, request, required_chronology, required_lock, sine, square


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": 2},
        {"near_perceptual_distance": -0.1},
        {"near_spectral_distance": 1.1},
        {"minimum_absolute_correlation": 2.0},
        {"near_perceptual_distance": 0.01, "polarity_perceptual_distance": 0.02},
    ],
)
def test_deduplication_thresholds_reject_invalid_configuration(kwargs):
    with pytest.raises(WavetableContractError):
        DeduplicationThresholds(**kwargs)


def test_exact_duplicates_form_one_group():
    samples = sine(100, 2)
    req = request((
        candidate("a", samples, source_index=0),
        candidate("b", samples, source_index=1),
        candidate("c", square(100, 17), source_index=2),
    ))
    result = analyze_wavetable_candidates(req)
    assert result.distinct_wave_count == 2
    duplicate_group = next(group for group in result.deduplication.groups if len(group.member_candidate_ids) == 2)
    assert duplicate_group.strongest_duplicate_kind is DuplicateKind.EXACT
    assert len(result.deduplication.duplicate_pairs) == 1
    assert result.deduplication.duplicate_pairs[0].duplicate_kind is DuplicateKind.EXACT


def test_polarity_equivalents_are_grouped():
    samples = sine(100, 3)
    req = request((
        candidate("positive", samples, source_index=0),
        candidate("negative", tuple(-value for value in samples), source_index=1),
    ))
    result = analyze_wavetable_candidates(req)
    assert result.distinct_wave_count == 1
    assert result.deduplication.duplicate_pairs[0].duplicate_kind is DuplicateKind.POLARITY_EQUIVALENT


def test_distinct_waves_remain_separate():
    req = request((
        candidate("sine", sine(100, 1), source_index=0),
        candidate("square", square(100, 13), source_index=1),
    ))
    result = analyze_wavetable_candidates(req)
    assert result.distinct_wave_count == 2
    assert result.redundant_candidate_ids == ()
    assert result.deduplication.duplicate_pairs == ()


def test_near_duplicates_are_detected_with_permissive_thresholds():
    base = sine(100, 2)
    near = tuple(max(-127, min(127, value + (1 if index % 13 == 0 else 0))) for index, value in enumerate(base))
    thresholds = DeduplicationThresholds(
        near_perceptual_distance=0.20,
        near_spectral_distance=0.20,
        near_feature_distance=0.20,
        minimum_absolute_correlation=0.80,
        polarity_perceptual_distance=0.02,
    )
    req = request((candidate("a", base, source_index=0), candidate("b", near, source_index=1)))
    structure = analyze_candidate_structure(req)
    result = analyze_candidate_deduplication(req, structure, thresholds)
    assert result.distinct_wave_count == 1
    assert result.duplicate_pairs[0].duplicate_kind is DuplicateKind.NEAR


def test_required_lock_protects_redundant_candidate():
    samples = sine(100, 2)
    req = request((
        candidate("a", samples, source_index=0),
        candidate("b", samples, source_index=1),
    ), locks=(required_lock(10, "b"),))
    result = analyze_wavetable_candidates(req)
    assert result.deduplication.groups[0].representative_candidate_id == "b"
    assert result.deduplication.protected_redundant_candidate_ids == ()
    assert result.deduplication.removable_candidate_ids == ("a",)


def test_required_chronology_protects_both_members():
    samples = sine(100, 2)
    req = request((
        candidate("a", samples, source_index=0),
        candidate("b", samples, source_index=1),
    ), chronology=(required_chronology("a", "b"),))
    result = analyze_wavetable_candidates(req)
    group = result.deduplication.groups[0]
    assert set(group.protected_candidate_ids) == {"a", "b"}
    assert group.removable_candidate_ids == ()


def test_representative_prefers_required_candidate():
    samples = sine(100, 2)
    req = request((
        candidate("a", samples, source_index=0, usefulness=0.95),
        candidate("b", samples, source_index=1, usefulness=0.10),
    ), locks=(required_lock(10, "b"),))
    result = analyze_wavetable_candidates(req)
    assert result.deduplication.groups[0].representative_candidate_id == "b"


def test_unprotected_representative_prefers_higher_scores():
    samples = sine(100, 2)
    req = request((
        candidate("low", samples, source_index=0, seed=0.0, usefulness=0.10),
        candidate("high", samples, source_index=1, seed=0.40, usefulness=0.95),
    ))
    result = analyze_wavetable_candidates(req)
    assert result.deduplication.groups[0].representative_candidate_id == "high"
    assert result.deduplication.removable_candidate_ids == ("low",)


def test_complete_link_grouping_prevents_transitive_chain():
    base = sine(100, 2)
    b = tuple(max(-127, min(127, value + (2 if index % 7 == 0 else 0))) for index, value in enumerate(base))
    c = tuple(max(-127, min(127, value + (4 if index % 7 == 0 else 0))) for index, value in enumerate(base))
    from w_mwxt_wavetable_tool.wavetable import compare_wave_shapes
    ab = compare_wave_shapes(base, b).perceptual_distance
    bc = compare_wave_shapes(b, c).perceptual_distance
    ac = compare_wave_shapes(base, c).perceptual_distance
    threshold = (max(ab, bc) + ac) / 2.0
    assert max(ab, bc) < threshold < ac
    thresholds = DeduplicationThresholds(
        near_perceptual_distance=threshold,
        near_spectral_distance=1.0,
        near_feature_distance=1.0,
        minimum_absolute_correlation=0.0,
        polarity_perceptual_distance=0.0,
    )
    req = request((
        candidate("a", base, source_index=0),
        candidate("b", b, source_index=1),
        candidate("c", c, source_index=2),
    ))
    result = analyze_candidate_deduplication(req, analyze_candidate_structure(req), thresholds)
    assert result.distinct_wave_count == 2
    assert sorted(len(group.member_candidate_ids) for group in result.groups) == [1, 2]


def test_deduplication_serialization_is_deterministic_and_non_destructive():
    samples = sine(100, 2)
    req = request((candidate("a", samples, source_index=0), candidate("b", samples, source_index=1)))
    first = analyze_wavetable_candidates(req)
    second = analyze_wavetable_candidates(req)
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256
    payload = json.loads(first.to_json())
    assert payload["analysis_sha256"] == first.analysis_sha256
    assert payload["boundaries"] == {
        "selects_final_keyframes": False,
        "builds_61_position_table": False,
        "orders_final_table": False,
        "interpolates_transitions": False,
        "materializes_wctd": False,
        "generates_sysex": False,
        "opens_midi_port": False,
        "transmits_midi": False,
    }
    assert first.deduplication.to_dict()["boundaries"]["removes_candidates"] is False


def test_aggregate_hash_links_structure_and_deduplication():
    req = request((candidate("a", sine(), source_index=0), candidate("b", square(), source_index=1)))
    result = analyze_wavetable_candidates(req)
    assert result.request_sha256 == req.analysis_sha256
    assert result.structure.request_sha256 == req.analysis_sha256
    assert result.deduplication.request_sha256 == req.analysis_sha256
    assert result.deduplication.structure_analysis_sha256 == result.structure.analysis_sha256


def test_wrong_types_and_broken_link_are_rejected():
    req = request((candidate("a", sine(), source_index=0),))
    structure = analyze_candidate_structure(req)
    with pytest.raises(WavetableContractError, match="request"):
        analyze_candidate_deduplication(object(), structure)  # type: ignore[arg-type]
    with pytest.raises(WavetableContractError, match="structure"):
        analyze_candidate_deduplication(req, object())  # type: ignore[arg-type]
    other = request((candidate("other", square(), source_index=0),))
    with pytest.raises(WavetableContractError, match="does not link"):
        analyze_candidate_deduplication(other, structure)


def test_models_are_frozen():
    result = analyze_wavetable_candidates(request((candidate("a", sine(), source_index=0),)))
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reason = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("kind", list(DuplicateKind))
def test_duplicate_kind_values_are_stable(kind):
    assert kind.value in {"exact", "polarity_equivalent", "near", "distinct"}


def test_more_than_61_distinct_groups_emits_warning():
    items = []
    for index in range(62):
        samples = tuple(((sample_index * (index + 3) + index * 17) % 255) - 127 for sample_index in range(64))
        items.append(candidate(f"c-{index:02d}", samples, source_index=index))
    thresholds = DeduplicationThresholds(
        near_perceptual_distance=0.0,
        near_spectral_distance=0.0,
        near_feature_distance=0.0,
        minimum_absolute_correlation=1.0,
        polarity_perceptual_distance=0.0,
    )
    req = request(tuple(items))
    result = analyze_candidate_deduplication(req, analyze_candidate_structure(req), thresholds)
    assert result.distinct_wave_count == 62
    assert any("exceeds 61" in warning for warning in result.warnings)
