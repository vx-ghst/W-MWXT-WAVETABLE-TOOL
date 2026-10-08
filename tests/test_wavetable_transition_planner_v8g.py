from v8e_transition_helpers import ALL_INTERPOLATION_METHODS, smooth_candidates

from w_mwxt_wavetable_tool import (
    GenerationMethod,
    InterpolationPolicy,
    evaluate_interval_interpolation_method,
    select_interval_interpolation_method,
    solve_perceptual_progress_plan,
)


def test_interval_decision_is_deterministic():
    left, right = smooth_candidates(2)
    first = select_interval_interpolation_method(left, right, ALL_INTERPOLATION_METHODS)
    second = select_interval_interpolation_method(left, right, ALL_INTERPOLATION_METHODS)
    assert first.to_dict() == second.to_dict()


def test_one_selected_method_has_one_matching_oracle():
    left, right = smooth_candidates(2)
    decision = select_interval_interpolation_method(left, right, ALL_INTERPOLATION_METHODS)
    assert sum(item.method is decision.selected_method for item in decision.oracles) == 1
    assert decision.selected_progress_plan.method is decision.selected_method


def test_nonadaptive_policy_uses_first_enabled_method_for_whole_interval():
    left, right = smooth_candidates(2)
    policy = InterpolationPolicy(adaptive_method_selection=False)
    decision = select_interval_interpolation_method(
        left, right, ALL_INTERPOLATION_METHODS, policy
    )
    assert decision.selected_method is policy.method_priority[0]
    assert len(decision.oracles) == 1


def test_all_interpolation_families_receive_quantitative_oracles():
    left, right = smooth_candidates(2)
    for method in ALL_INTERPOLATION_METHODS:
        oracle = evaluate_interval_interpolation_method(left, right, method)
        assert 0.0 <= oracle.aggregate_score <= 1.0
        assert 0.0 <= oracle.spacing_regularity_score <= 1.0
        assert 0.0 <= oracle.harmonic_path_score <= 1.0
        assert oracle.evidence


def test_perceptual_solver_never_worsens_its_measured_path():
    left, right = smooth_candidates(2)
    plan = solve_perceptual_progress_plan(
        left,
        right,
        GenerationMethod.PERCEPTUAL_INTERPOLATION,
        (0.25, 0.5, 0.75),
    )
    assert plan.solved_max_error <= plan.direct_max_error
    assert plan.improvement == round(plan.direct_max_error - plan.solved_max_error, 12)


def test_progress_targets_are_preserved_as_exact_mapping_keys():
    left, right = smooth_candidates(2)
    decision = select_interval_interpolation_method(
        left, right, ALL_INTERPOLATION_METHODS, target_fractions=(0.2, 0.6, 0.8)
    )
    assert decision.selected_progress_plan.target_fractions == (0.2, 0.6, 0.8)
