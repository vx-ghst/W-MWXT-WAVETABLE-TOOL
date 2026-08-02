from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.analysis import cycle_selection
from w_mwxt_wavetable_tool.analysis.cycle_detection import (
    CycleCandidate,
    CycleCandidateStatus,
    CycleDiscoveryAnalysis,
)
from w_mwxt_wavetable_tool.analysis.cycle_selection import (
    CycleSelectionDecision,
    CycleSelectionPolicy,
    RankedCycleCandidate,
    SelectedCycleSet,
    analyze_audio_source_cycle_selection,
    select_representative_cycles,
)


def make_candidate(
    index: int,
    *,
    segment_index: int = 0,
    start_sample: int | None = None,
    score: float = 0.90,
    status: CycleCandidateStatus = CycleCandidateStatus.ACCEPTED,
) -> CycleCandidate:
    start = index * 100 if start_sample is None else start_sample
    reasons = () if status is CycleCandidateStatus.ACCEPTED else ("seam_below_gate",)
    return CycleCandidate(
        index=index,
        segment_index=segment_index,
        local_index=sum(
            1
            for candidate_index in range(index)
            if (candidate_index % 2 if segment_index in {0, 1} else segment_index)
            == segment_index
        ),
        start_sample=start,
        end_sample=start + 8,
        sample_rate=1000,
        source_segment_sha256=("b" if segment_index == 0 else "c") * 64,
        expected_source_period_samples=8.0,
        cycle_length_samples=8,
        period_error_samples=0.0,
        period_error_ratio=0.0,
        waveform_rms=0.7,
        peak_amplitude=1.0,
        periodicity_score=score,
        seam_value_error=0.0,
        seam_slope_error=0.0,
        seam_score=score,
        energy_consistency_score=score,
        spectral_consistency_score=score,
        composite_score=score,
        status=status,
        rejection_reasons=reasons,
    )


def make_analysis(
    *,
    candidates: tuple[CycleCandidate, ...] | None = None,
    pitch_available: bool = True,
) -> CycleDiscoveryAnalysis:
    if candidates is None:
        candidates = tuple(
            make_candidate(
                index,
                segment_index=index % 2,
                score=0.96 - index * 0.01,
            )
            for index in range(8)
        )
    local_counts: dict[int, int] = {}
    normalized_candidates = []
    for candidate in candidates:
        local_index = local_counts.get(candidate.segment_index, 0)
        local_counts[candidate.segment_index] = local_index + 1
        normalized_candidates.append(replace(candidate, local_index=local_index))
    candidates = tuple(normalized_candidates)
    used_segments = tuple(sorted({candidate.segment_index for candidate in candidates}))
    hashes = tuple(("b" if index == 0 else "c") * 64 for index in used_segments)
    return CycleDiscoveryAnalysis(
        schema_version=1,
        tool_version="0.7.0",
        sample_rate=1000,
        sample_count=2000,
        sample_sha256="a" * 64,
        segmentation_analysis_sha256="d" * 64,
        working_pitch_plan_sha256="e" * 64,
        working_frequency_hz=125.0 if pitch_available else None,
        working_period_samples=8.0 if pitch_available else None,
        source_period_samples=8.0 if pitch_available else None,
        repitch_ratio=1.0 if pitch_available else None,
        repitch_required=False,
        period_search_radius_ratio=0.125,
        boundary_search_radius_samples=4,
        maximum_cycles_per_segment=64,
        minimum_periodicity_score=0.75,
        minimum_seam_score=0.45,
        minimum_energy_consistency_score=0.50,
        minimum_spectral_consistency_score=0.70,
        usable_segment_indices=used_segments,
        usable_segment_sha256=hashes,
        analyzed_segment_indices=used_segments if candidates else (),
        skipped_segment_indices=(),
        candidates=candidates,
        decision_reason="fixture",
    )


def result(**kwargs) -> SelectedCycleSet:
    return select_representative_cycles(make_analysis(), **kwargs)


def test_default_identity_and_hash_link() -> None:
    analysis = make_analysis()
    selected = select_representative_cycles(analysis)
    assert selected.schema_version == 1
    assert selected.tool_version == "0.7.0"
    assert selected.sample_sha256 == analysis.sample_sha256
    assert selected.cycle_discovery_analysis_sha256 == analysis.analysis_sha256


def test_default_policy_is_auto() -> None:
    assert result().policy is CycleSelectionPolicy.AUTO


def test_default_top_n_is_sixteen() -> None:
    assert result().top_n == 16


def test_auto_ranks_only_accepted_candidates() -> None:
    candidates = (
        make_candidate(0),
        make_candidate(1, status=CycleCandidateStatus.REJECTED),
    )
    selected = select_representative_cycles(make_analysis(candidates=candidates))
    assert [entry.candidate_index for entry in selected.ranked_candidates] == [0]


def test_force_places_candidate_at_rank_one() -> None:
    selected = result(policy="force", forced_candidate_index=5)
    assert selected.ranked_candidates[0].candidate_index == 5
    assert selected.ranked_candidates[0].forced is True
    assert selected.ranked_candidates[0].selected is True


def test_force_policy_requires_index() -> None:
    with pytest.raises(ValueError, match="requires forced_candidate_index"):
        result(policy="force")


def test_auto_policy_rejects_forced_index() -> None:
    with pytest.raises(ValueError, match="only valid with force"):
        result(forced_candidate_index=0)


def test_rejected_forced_candidate_is_blocked_by_default() -> None:
    candidates = (
        make_candidate(0),
        make_candidate(1, status=CycleCandidateStatus.REJECTED),
    )
    with pytest.raises(ValueError, match="allow_rejected"):
        select_representative_cycles(
            make_analysis(candidates=candidates),
            policy="force",
            forced_candidate_index=1,
        )


def test_rejected_forced_candidate_can_be_explicitly_allowed() -> None:
    candidates = (
        make_candidate(0),
        make_candidate(1, status=CycleCandidateStatus.REJECTED),
    )
    selected = select_representative_cycles(
        make_analysis(candidates=candidates),
        policy="force",
        forced_candidate_index=1,
        allow_rejected_forced_candidate=True,
    )
    assert selected.selected_candidate_indices[0] == 1


def test_invalid_forced_index_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside the candidate range"):
        result(policy="force", forced_candidate_index=999)


def test_top_n_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="between 1 and 61"):
        result(top_n=0)


def test_top_n_above_xt_user_wave_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="between 1 and 61"):
        result(top_n=62)


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to one"):
        result(quality_weight=0.5, temporal_novelty_weight=0.2, segment_novelty_weight=0.1)


def test_negative_temporal_separation_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        result(minimum_temporal_separation_periods=-1.0)


def test_selection_is_deterministic() -> None:
    first = result(top_n=4)
    second = result(top_n=4)
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.ranking_sha256 == second.ranking_sha256


def test_analysis_hash_changes_with_top_n() -> None:
    assert result(top_n=2).analysis_sha256 != result(top_n=3).analysis_sha256


def test_analysis_hash_changes_with_weights() -> None:
    first = result()
    second = result(
        quality_weight=0.6,
        temporal_novelty_weight=0.3,
        segment_novelty_weight=0.1,
    )
    assert first.analysis_sha256 != second.analysis_sha256


def test_hashes_are_lowercase_sha256() -> None:
    selected = result()
    digests = (selected.analysis_sha256, *selected.ranking_sha256)
    assert all(len(value) == 64 and value == value.lower() for value in digests)
    assert all(int(value, 16) >= 0 for value in digests)


def test_to_dict_links_ranking_and_selection_hashes() -> None:
    payload = result(top_n=3).to_dict()
    assert payload["ranking_sha256"] == [
        entry["ranking_sha256"] for entry in payload["ranked_candidates"]
    ]
    selected_entries = [entry for entry in payload["ranked_candidates"] if entry["selected"]]
    assert payload["selected_candidate_sha256"] == [
        entry["candidate_sha256"] for entry in selected_entries
    ]


def test_ranking_positions_are_contiguous() -> None:
    assert [entry.rank for entry in result().ranked_candidates] == list(range(1, 9))


def test_ranked_candidate_indexes_are_unique() -> None:
    indexes = [entry.candidate_index for entry in result().ranked_candidates]
    assert len(indexes) == len(set(indexes))


def test_selected_order_follows_ranking_order() -> None:
    selected = result(top_n=4)
    assert selected.selected_candidate_indices == tuple(
        entry.candidate_index for entry in selected.ranked_candidates if entry.selected
    )


def test_selected_count_never_exceeds_top_n() -> None:
    selected = result(top_n=3)
    assert selected.selected_count <= 3


def test_selected_candidate_hashes_link_to_ranking() -> None:
    selected = result(top_n=3)
    assert selected.selected_candidate_sha256 == tuple(
        entry.candidate_sha256 for entry in selected.ranked_candidates if entry.selected
    )


def test_selected_ranking_hashes_link_to_ranking() -> None:
    selected = result(top_n=3)
    assert selected.selected_ranking_sha256 == tuple(
        entry.ranking_sha256 for entry in selected.ranked_candidates if entry.selected
    )


def test_representative_segments_are_sorted_unique() -> None:
    selected = result(top_n=4)
    expected = tuple(
        sorted(
            {
                entry.segment_index
                for entry in selected.ranked_candidates
                if entry.selected
            }
        )
    )
    assert selected.representative_segment_indices == expected


def test_rejected_candidates_are_absent_from_auto_ranking() -> None:
    candidates = tuple(
        make_candidate(
            index,
            status=(
                CycleCandidateStatus.REJECTED
                if index % 2
                else CycleCandidateStatus.ACCEPTED
            ),
        )
        for index in range(4)
    )
    selected = select_representative_cycles(make_analysis(candidates=candidates))
    assert [entry.candidate_index for entry in selected.ranked_candidates] == [0, 2]


def test_forced_rejected_candidate_is_present_when_override_is_allowed() -> None:
    candidates = (
        make_candidate(0),
        make_candidate(1, status=CycleCandidateStatus.REJECTED),
    )
    selected = select_representative_cycles(
        make_analysis(candidates=candidates),
        policy="force",
        forced_candidate_index=1,
        allow_rejected_forced_candidate=True,
    )
    assert selected.ranked_candidates[0].candidate_index == 1


def test_no_candidates_returns_no_candidates_decision() -> None:
    selected = select_representative_cycles(make_analysis(candidates=()))
    assert selected.decision is CycleSelectionDecision.NO_CANDIDATES
    assert selected.selected_count == 0


def test_pitch_unavailable_returns_pitch_unavailable_decision() -> None:
    selected = select_representative_cycles(
        make_analysis(candidates=(), pitch_available=False)
    )
    assert selected.decision is CycleSelectionDecision.PITCH_UNAVAILABLE


def test_no_accepted_candidates_returns_explicit_decision() -> None:
    candidates = tuple(
        make_candidate(index, status=CycleCandidateStatus.REJECTED)
        for index in range(2)
    )
    selected = select_representative_cycles(make_analysis(candidates=candidates))
    assert selected.decision is CycleSelectionDecision.NO_ACCEPTED_CANDIDATES


def test_first_representative_score_uses_default_formula() -> None:
    selected = result(top_n=1)
    entry = selected.ranked_candidates[0]
    assert entry.temporal_novelty_score == 1.0
    assert entry.segment_novelty_score == 1.0
    assert entry.representative_score == pytest.approx(
        0.7 * entry.quality_score + 0.2 + 0.1
    )


def test_later_temporal_novelty_scores_remain_ratios() -> None:
    entries = result().ranked_candidates[1:]
    assert entries
    assert all(0.0 <= entry.temporal_novelty_score <= 1.0 for entry in entries)


def test_tie_breaker_prefers_lower_candidate_index() -> None:
    candidates = (
        make_candidate(0, score=0.9, start_sample=0),
        make_candidate(1, score=0.9, start_sample=0),
    )
    selected = select_representative_cycles(make_analysis(candidates=candidates))
    assert selected.ranked_candidates[0].candidate_index == 0


def test_segment_novelty_rewards_unrepresented_segment() -> None:
    candidates = (
        make_candidate(0, segment_index=0, score=0.9, start_sample=0),
        make_candidate(1, segment_index=0, score=0.9, start_sample=100),
        make_candidate(2, segment_index=1, score=0.9, start_sample=100),
    )
    selected = select_representative_cycles(make_analysis(candidates=candidates))
    assert selected.ranked_candidates[1].candidate_index == 2


def test_temporal_novelty_rewards_distant_candidate() -> None:
    candidates = (
        make_candidate(0, score=0.9, start_sample=0),
        make_candidate(1, score=0.9, start_sample=10),
        make_candidate(2, score=0.9, start_sample=1000),
    )
    selected = select_representative_cycles(make_analysis(candidates=candidates))
    assert selected.ranked_candidates[1].candidate_index == 2


def test_temporal_separation_can_reduce_selected_count() -> None:
    candidates = tuple(
        make_candidate(index, start_sample=index * 8)
        for index in range(5)
    )
    selected = select_representative_cycles(
        make_analysis(candidates=candidates),
        top_n=5,
        minimum_temporal_separation_periods=3.0,
    )
    assert selected.selected_count < 5


def test_zero_temporal_separation_fills_top_n() -> None:
    selected = result(top_n=5, minimum_temporal_separation_periods=0.0)
    assert selected.selected_count == 5


def test_forced_candidate_remains_selected_inside_separation_radius() -> None:
    candidates = (
        make_candidate(0, start_sample=0),
        make_candidate(1, start_sample=1),
    )
    selected = select_representative_cycles(
        make_analysis(candidates=candidates),
        policy="force",
        forced_candidate_index=1,
        top_n=1,
        minimum_temporal_separation_periods=10.0,
    )
    assert selected.selected_candidate_indices == (1,)


def test_models_are_frozen() -> None:
    selected = result()
    with pytest.raises(FrozenInstanceError):
        selected.top_n = 1
    with pytest.raises(FrozenInstanceError):
        selected.ranked_candidates[0].selected = False


def test_ranking_hash_changes_with_selected_flag() -> None:
    entry = result().ranked_candidates[0]
    assert replace(entry, selected=not entry.selected).ranking_sha256 != entry.ranking_sha256


def test_wrapper_delegates_to_cycle_discovery(monkeypatch) -> None:
    analysis = make_analysis()
    source = SimpleNamespace()
    monkeypatch.setattr(
        cycle_selection,
        "analyze_audio_source_cycles",
        lambda *args, **kwargs: analysis,
    )
    selected = analyze_audio_source_cycle_selection(source, top_n=2)
    assert selected.cycle_discovery_analysis_sha256 == analysis.analysis_sha256


def test_model_rejects_tampered_selected_hash() -> None:
    selected = result(top_n=2)
    with pytest.raises(ValueError, match="selected candidate hashes"):
        replace(selected, selected_candidate_sha256=("f" * 64,))


def test_model_rejects_noncontiguous_ranks() -> None:
    selected = result(top_n=2)
    entries = (replace(selected.ranked_candidates[0], rank=2),) + selected.ranked_candidates[1:]
    with pytest.raises(ValueError, match="contiguous"):
        replace(selected, ranked_candidates=entries)


def test_model_rejects_invalid_force_contract() -> None:
    selected = result(top_n=2)
    with pytest.raises(ValueError, match="force policy"):
        replace(
            selected,
            policy=CycleSelectionPolicy.FORCE,
            forced_candidate_index=0,
        )


def test_model_rejects_nonselected_decision_with_selected_cycles() -> None:
    selected = result(top_n=2)
    with pytest.raises(ValueError, match="non-selected"):
        replace(selected, decision=CycleSelectionDecision.NO_CANDIDATES)


def test_model_rejects_inconsistent_representative_segments() -> None:
    selected = result(top_n=2)
    with pytest.raises(ValueError, match="representative segment"):
        replace(selected, representative_segment_indices=(99,))


def test_decision_reason_is_always_explainable() -> None:
    assert result().decision_reason.strip()
