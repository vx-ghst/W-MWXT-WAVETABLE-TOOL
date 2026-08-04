from __future__ import annotations


def test_profiles_public_api() -> None:
    import w_mwxt_wavetable_tool.profiles as profiles

    assert len(profiles.all_profile_definitions()) == 9
    assert callable(profiles.evaluate_bass_working_pitches)
    assert callable(profiles.analyze_bass_sequence_consistency)
    assert callable(profiles.profile_definition)


def test_xt_public_api() -> None:
    import w_mwxt_wavetable_tool.xt as xt

    required = (
        "compare_quantization_algorithms",
        "compare_resampling_algorithms",
        "generate_symmetry_candidates",
        "analyze_xt_aliasing_risk",
        "measure_xt_wave_metrics",
        "optimize_xt_wave",
        "optimize_xt_wave_set",
        "evaluate_cycle_xt_compatibility",
    )
    assert all(callable(getattr(xt, name)) for name in required)


def test_decision_profile_selector_public_api() -> None:
    import w_mwxt_wavetable_tool.decision as decision

    assert callable(decision.select_optimization_profile)
