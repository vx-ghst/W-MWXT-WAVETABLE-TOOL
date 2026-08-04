from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from v8e_transition_helpers import (
    relaxed_continuity_thresholds,
    smooth_candidates,
    transition_context,
)

from w_mwxt_wavetable_tool.wavetable import (
    ContinuityStatus,
    ContinuityThresholds,
    WavetableContractError,
    analyze_slot_continuity,
    analyze_wavetable_continuity,
)


def test_complete_build_produces_sixty_continuity_transitions():
    _, _, _, _, result = transition_context(2)
    report = result.primary_variant.continuity
    assert len(report.transitions) == 60
    assert tuple(item.left_position for item in report.transitions) == tuple(range(60))


def test_continuity_counts_partition_all_transitions():
    _, _, _, _, result = transition_context(2)
    report = result.primary_variant.continuity
    assert report.pass_count + report.warning_count + report.failure_count == 60


def test_one_keyframe_edge_hold_build_has_perfect_continuity():
    _, _, _, _, result = transition_context(1, relaxed=False)
    report = result.primary_variant.continuity
    assert report.status is ContinuityStatus.PASS
    assert report.pass_count == 60
    assert report.warning_count == 0
    assert report.failure_count == 0
    assert report.mean_continuity_score == 1.0
    assert report.minimum_continuity_score == 1.0


def test_continuity_report_links_to_exact_build_hash():
    _, _, _, _, result = transition_context(2)
    variant = result.primary_variant
    assert variant.continuity.build_sha256 == variant.build.analysis_sha256


def test_continuity_report_is_deterministic():
    _, _, _, _, first = transition_context(2)
    _, _, _, _, second = transition_context(2)
    assert first.primary_variant.continuity == second.primary_variant.continuity
    assert (
        first.primary_variant.continuity.analysis_sha256
        == second.primary_variant.continuity.analysis_sha256
    )


def test_identical_adjacent_slots_pass_strict_thresholds():
    _, _, _, _, result = transition_context(1, relaxed=False)
    build = result.primary_variant.build
    analysis = analyze_slot_continuity(build.slots[0], build.slots[1])
    assert analysis.status is ContinuityStatus.PASS
    assert not analysis.issues
    assert analysis.continuity_score == 1.0


def test_severe_discontinuity_fails_tight_thresholds():
    _, _, _, _, result = transition_context(2)
    build = result.primary_variant.build
    left = replace(build.slots[0], position=0)
    right = replace(build.slots[60], position=1)
    thresholds = ContinuityThresholds(
        warning_perceptual_distance=0.001,
        failure_perceptual_distance=0.002,
        warning_spectral_distance=0.001,
        failure_spectral_distance=0.002,
        warning_level_delta=0.001,
        failure_level_delta=0.002,
        warning_fundamental_delta=0.001,
        failure_fundamental_delta=0.002,
        warning_maximum_sample_distance=0.001,
        failure_maximum_sample_distance=0.002,
        failure_correlation_floor=0.99,
    )
    analysis = analyze_slot_continuity(left, right, thresholds)
    assert analysis.status is ContinuityStatus.FAIL
    assert analysis.issues


def test_intentional_break_downgrades_failure_to_warning():
    _, _, _, _, result = transition_context(2)
    build = result.primary_variant.build
    left = replace(build.slots[0], position=0)
    right = replace(build.slots[60], position=1)
    thresholds = ContinuityThresholds(
        warning_perceptual_distance=0.001,
        failure_perceptual_distance=0.002,
        warning_spectral_distance=0.001,
        failure_spectral_distance=0.002,
        warning_level_delta=0.001,
        failure_level_delta=0.002,
        warning_fundamental_delta=0.001,
        failure_fundamental_delta=0.002,
        warning_maximum_sample_distance=0.001,
        failure_maximum_sample_distance=0.002,
        failure_correlation_floor=0.99,
    )
    analysis = analyze_slot_continuity(
        left,
        right,
        thresholds,
        intentional_break=True,
    )
    assert analysis.status is ContinuityStatus.WARNING
    assert analysis.intentional_break
    assert analysis.issues


def test_relaxed_thresholds_never_create_failure_for_safe_samples():
    _, _, _, _, result = transition_context(2)
    report = analyze_wavetable_continuity(
        result.primary_variant.build,
        relaxed_continuity_thresholds(),
    )
    assert report.failure_count == 0
    assert report.status is not ContinuityStatus.FAIL


def test_continuity_scores_are_bounded():
    _, _, _, _, result = transition_context(2)
    report = result.primary_variant.continuity
    assert 0.0 <= report.mean_continuity_score <= 1.0
    assert 0.0 <= report.minimum_continuity_score <= 1.0
    assert all(0.0 <= item.continuity_score <= 1.0 for item in report.transitions)


def test_continuity_models_are_frozen():
    _, _, _, _, result = transition_context(2)
    report = result.primary_variant.continuity
    with pytest.raises(FrozenInstanceError):
        report.status = ContinuityStatus.FAIL
    with pytest.raises(FrozenInstanceError):
        report.transitions[0].continuity_score = 0.0


def test_slot_continuity_rejects_non_adjacent_positions():
    _, _, _, _, result = transition_context(1)
    build = result.primary_variant.build
    with pytest.raises(WavetableContractError):
        analyze_slot_continuity(build.slots[0], build.slots[2])


def test_report_rejects_rejected_build():
    _, _, _, _, result = transition_context(1)
    build = result.primary_variant.build
    rejected = replace(
        build,
        status=type(build.status).REJECTED,
        slots=(),
        blockers=("synthetic blocker",),
    )
    with pytest.raises(WavetableContractError):
        analyze_wavetable_continuity(rejected)


@pytest.mark.parametrize(
    "kwargs",
    (
        {
            "warning_perceptual_distance": 0.5,
            "failure_perceptual_distance": 0.5,
        },
        {
            "warning_spectral_distance": 0.7,
            "failure_spectral_distance": 0.6,
        },
        {
            "warning_level_delta": -0.1,
        },
        {
            "failure_correlation_floor": -1.1,
        },
    ),
)
def test_continuity_thresholds_reject_invalid_values(kwargs):
    with pytest.raises(WavetableContractError):
        ContinuityThresholds(**kwargs)
