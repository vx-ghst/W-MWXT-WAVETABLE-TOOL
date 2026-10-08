from __future__ import annotations

import dataclasses

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    CandidateDeduplicationAnalysis,
    CandidateStructureClass,
    DuplicateKind,
    IntervalClass,
    WavetableContractError,
    analyze_candidate_structure,
    analyze_wavetable_candidates,
)

from v8b_helpers import candidate, request, sine, square


def test_endpoints_are_structural_when_eligible():
    result = analyze_candidate_structure(request((
        candidate("a", sine(), source_index=0),
        candidate("b", sine(), source_index=1),
        candidate("c", sine(), source_index=2),
    )))
    assert result.candidates[0].structural_candidate
    assert result.candidates[-1].structural_candidate


def test_breakpoint_interval_has_kinds_and_strength():
    result = analyze_candidate_structure(request((
        candidate("a", sine(120, 1), source_index=0),
        candidate("b", square(120, 7), source_index=1),
    )))
    interval = result.intervals[0]
    if interval.interval_class is IntervalClass.BREAKPOINT:
        assert interval.breakpoint_kinds
    else:
        assert interval.breakpoint_kinds == ()
    assert 0.0 <= interval.transition_strength <= 1.0


def test_candidate_evidence_contains_indices_and_scores():
    result = analyze_candidate_structure(request((candidate("a", sine(), source_index=0),)))
    evidence = result.candidates[0].evidence
    assert any(item.startswith("inventory-index=") for item in evidence)
    assert any(item.startswith("source-order-index=") for item in evidence)
    assert any(item.startswith("structural-score=") for item in evidence)


def test_group_partition_and_candidate_order_match_inventory():
    samples = sine(100, 2)
    result = analyze_wavetable_candidates(request((
        candidate("c", square(), source_index=2),
        candidate("a", samples, source_index=0),
        candidate("b", samples, source_index=1),
    )))
    members = tuple(member for group in result.deduplication.groups for member in group.member_candidate_ids)
    assert set(members) == {"a", "b", "c"}
    assert tuple(item.candidate_id for item in result.deduplication.candidates) == result.structure.source_order_candidate_ids


def test_representative_candidate_is_not_redundant():
    samples = sine(100, 2)
    result = analyze_wavetable_candidates(request((
        candidate("a", samples, source_index=0),
        candidate("b", samples, source_index=1),
    )))
    representative = result.deduplication.groups[0].representative_candidate_id
    item = next(entry for entry in result.deduplication.candidates if entry.candidate_id == representative)
    assert not item.redundant
    assert item.duplicate_kind is DuplicateKind.DISTINCT


def test_candidate_dedup_model_rejects_invalid_removable_state():
    with pytest.raises(WavetableContractError, match="removable"):
        CandidateDeduplicationAnalysis(
            schema_version=1,
            candidate_id="a",
            group_id="g",
            representative_candidate_id="a",
            duplicate_kind=DuplicateKind.DISTINCT,
            redundant=False,
            protected=False,
            removable=True,
            reason="Invalid test state.",
        )


def test_structure_class_boolean_contract_is_consistent():
    result = analyze_candidate_structure(request((
        candidate("a", sine(), source_index=0),
        candidate("b", square(), source_index=1),
    )))
    for item in result.candidates:
        assert item.structural_candidate == (item.structure_class in {
            CandidateStructureClass.STRUCTURAL,
            CandidateStructureClass.BREAKPOINT,
            CandidateStructureClass.EXTREME,
        })
        assert item.stable_candidate == (item.structure_class is CandidateStructureClass.STABLE)
        assert item.transition_candidate == (item.structure_class is CandidateStructureClass.TRANSITION)
        assert item.breakpoint_candidate == (item.structure_class is CandidateStructureClass.BREAKPOINT)


def test_all_aggregate_models_are_frozen():
    result = analyze_wavetable_candidates(request((candidate("a", sine(), source_index=0),)))
    for model in (result, result.structure, result.deduplication, result.structure.candidates[0], result.deduplication.groups[0]):
        with pytest.raises(dataclasses.FrozenInstanceError):
            model.reason = "changed"  # type: ignore[misc]


def test_analysis_does_not_mutate_request_or_candidates():
    item = candidate("a", sine(), source_index=0)
    req = request((item,))
    request_hash = req.analysis_sha256
    candidate_hash = item.candidate_sha256
    analyze_wavetable_candidates(req)
    assert req.analysis_sha256 == request_hash
    assert item.candidate_sha256 == candidate_hash
