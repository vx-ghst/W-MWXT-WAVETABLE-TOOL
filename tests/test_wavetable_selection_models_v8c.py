from __future__ import annotations

import dataclasses
import json

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    CandidateSelectionDecision,
    CandidateStructureClass,
    CodeV8CAnalysis,
    KeyframeSelectionPolicy,
    KeyframeSelectionScore,
    KeyframeSelectionStatus,
    SelectionEvidenceKind,
    WAVETABLE_SELECTION_SCHEMA_VERSION,
    WavetableContractError,
)
from v8c_selection_helpers import candidate, selection_for, sine


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": 2},
        {"maximum_keyframes": 0},
        {"maximum_keyframes": 62},
        {"requested_keyframe_count": 0},
        {"requested_keyframe_count": 62},
        {"exact_search_candidate_limit": 0},
        {"exact_search_combination_limit": 0},
        {"utility_weight": -0.1, "diversity_weight": 0.81},
        {"utility_weight": 0.5},
    ],
)
def test_policy_rejects_invalid_values(kwargs):
    with pytest.raises(WavetableContractError):
        KeyframeSelectionPolicy(**kwargs)


def test_default_policy_is_exact_61_capacity_and_hashable():
    policy = KeyframeSelectionPolicy()
    assert policy.maximum_keyframes == 61
    assert policy.requested_keyframe_count is None
    assert len(policy.analysis_sha256) == 64
    assert policy.to_dict()["preserve_source_endpoints"] is True


@pytest.mark.parametrize("status", list(KeyframeSelectionStatus))
def test_status_values_are_stable(status):
    assert status.value in {"complete", "rejected"}


@pytest.mark.parametrize("kind", list(SelectionEvidenceKind))
def test_evidence_kind_values_are_stable(kind):
    assert kind.value in {
        "required_lock",
        "required_chronology",
        "source_endpoint",
        "breakpoint",
        "feature_extreme",
        "structural",
        "group_representative",
        "protected_redundant",
        "utility",
        "diversity",
        "temporal_coverage",
        "omitted_redundant",
        "omitted_capacity",
    }


def test_selection_models_are_frozen_and_deterministic():
    _, _, result = selection_for((candidate("a", sine(), source_index=0),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reason = "changed"  # type: ignore[misc]
    assert json.loads(result.to_json())["analysis_sha256"] == result.analysis_sha256
    assert result == result


def test_selection_boundaries_are_explicit():
    _, _, result = selection_for((candidate("a", sine(), source_index=0),))
    boundaries = result.selection.to_dict()["boundaries"]
    assert boundaries == {
        "selects_final_keyframes": True,
        "assigns_user_positions": False,
        "orders_final_table": False,
        "solves_chronology": False,
        "generates_variants": False,
        "interpolates_transitions": False,
        "materializes_wctd": False,
        "generates_sysex": False,
        "opens_midi_port": False,
        "transmits_midi": False,
    }


def test_candidate_decision_rejects_inconsistent_selected_rank():
    with pytest.raises(WavetableContractError, match="selected"):
        CandidateSelectionDecision(
            schema_version=1,
            candidate_id="a",
            group_id="g",
            source_order_index=0,
            selected=True,
            essential=False,
            forced=False,
            source_endpoint=False,
            group_representative=True,
            protected=False,
            removable=False,
            structure_class=CandidateStructureClass.STRUCTURAL,
            utility_score=0.5,
            structural_priority=0.5,
            selected_source_order_rank=None,
            evidence_kinds=(SelectionEvidenceKind.STRUCTURAL,),
            evidence=("evidence",),
            reason="reason",
        )


def test_selection_score_rejects_empty_and_non_finite_values():
    with pytest.raises(WavetableContractError):
        KeyframeSelectionScore(
            schema_version=1,
            selected_candidate_ids=(),
            objective_score=0.5,
            utility_score=0.5,
            diversity_score=0.5,
            temporal_coverage_score=0.5,
            structural_coverage_score=0.5,
            group_coverage_score=0.5,
        )
    with pytest.raises(WavetableContractError):
        KeyframeSelectionScore(
            schema_version=1,
            selected_candidate_ids=("a",),
            objective_score=float("nan"),
            utility_score=0.5,
            diversity_score=0.5,
            temporal_coverage_score=0.5,
            structural_coverage_score=0.5,
            group_coverage_score=0.5,
        )


def test_schema_version_is_stable():
    assert WAVETABLE_SELECTION_SCHEMA_VERSION == 1


def test_code_v8c_type_and_links_are_exposed():
    req, v8b, result = selection_for((candidate("a", sine(), source_index=0),))
    assert isinstance(result, CodeV8CAnalysis)
    assert result.request_sha256 == req.analysis_sha256
    assert result.v8b_analysis_sha256 == v8b.analysis_sha256
    assert result.selection.request_sha256 == req.analysis_sha256
