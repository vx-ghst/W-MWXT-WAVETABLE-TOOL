import math

from w_mwxt_wavetable_tool import (
    OptimizationProfile,
    build_factory_placement,
    placement_profile_policy,
    plan_adaptive_slot_budget,
)

from v8h_helpers import v8h_context


def test_every_music_profile_has_normalized_visible_placement_weights():
    hashes = set()
    for profile in OptimizationProfile:
        policy = placement_profile_policy(profile)
        hashes.add(policy.analysis_sha256)
        assert math.isclose(sum(policy.feature_weights.values()), 1.0, abs_tol=1e-9)
        assert math.isclose(
            sum(
                (
                    policy.generic_ordering_weight,
                    policy.trajectory_weight,
                    policy.adjacency_weight,
                    policy.source_fidelity_weight,
                    policy.zone_count_weight,
                )
            ),
            1.0,
            abs_tol=1e-9,
        )
        assert math.isclose(sum(policy.zone_keyframe_fractions), 1.0, abs_tol=1e-9)
        assert tuple(item.zone.value for item in policy.targets) == (
            "stable_playable",
            "main_evolution",
            "extreme",
        )
    assert len(hashes) == len(tuple(OptimizationProfile))


def test_bass_pad_and_experimental_profiles_change_factory_evidence():
    analyses = {}
    for profile in ("bass_sub", "pad", "experimental"):
        request, v8b, v8c, v8d, regions = v8h_context(profile=profile)
        analyses[profile] = build_factory_placement(
            request, v8b, v8c, v8d, plan_adaptive_slot_budget(regions)
        )
    assert len({item.policy.analysis_sha256 for item in analyses.values()}) == 3
    assert len({item.primary_variant.objective_score for item in analyses.values()}) == 3
    assert analyses["bass_sub"].policy.bass_stability_weight > analyses["experimental"].policy.bass_stability_weight
    assert analyses["experimental"].policy.zone_keyframe_fractions[2] > analyses["bass_sub"].policy.zone_keyframe_fractions[2]
