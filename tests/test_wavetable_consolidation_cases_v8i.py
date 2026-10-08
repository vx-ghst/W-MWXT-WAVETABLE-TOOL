from __future__ import annotations

from v8i_helpers import distinct_build, identical_build, near_pair_build, polarity_pair_build
from w_mwxt_wavetable_tool import (
    ConsolidationMatchKind,
    ConsolidationPolicy,
    consolidate_wavetable_build,
)


def test_sixty_one_identical_logical_positions_become_one_physical_wave() -> None:
    result = consolidate_wavetable_build(identical_build())
    assert result.physical_wave_set is not None
    assert result.mapping is not None
    assert result.physical_wave_set.physical_wave_count == 1
    assert result.mapping.logical_to_physical == (0,) * 61
    assert result.mapping.physical_to_logical == (tuple(range(61)),)


def test_sixty_one_distinct_logical_positions_remain_sixty_one_physical_waves() -> None:
    result = consolidate_wavetable_build(distinct_build())
    assert result.physical_wave_set is not None
    assert result.mapping is not None
    assert result.physical_wave_set.physical_wave_count == 61
    assert result.mapping.logical_to_physical == tuple(range(61))


def test_near_duplicates_are_disabled_by_default_and_opt_in_with_strict_gates() -> None:
    build = near_pair_build()
    default = consolidate_wavetable_build(build)
    enabled = consolidate_wavetable_build(
        build,
        ConsolidationPolicy(
            allow_near_duplicates=True,
            near_perceptual_distance=0.10,
            near_spectral_distance=0.10,
            near_feature_distance=0.10,
            near_maximum_sample_distance=0.10,
            minimum_absolute_correlation=0.95,
            maximum_usefulness_delta=0.10,
            maximum_continuity_degradation=1.0,
        ),
    )
    assert default.mapping is not None and enabled.mapping is not None
    assert default.mapping.logical_to_physical[10] != default.mapping.logical_to_physical[11]
    assert enabled.mapping.logical_to_physical[10] == enabled.mapping.logical_to_physical[11]
    assert enabled.report is not None
    assert enabled.report.decisions[11].match_kind is ConsolidationMatchKind.NEAR


def test_protected_near_pair_never_merges() -> None:
    result = consolidate_wavetable_build(
        near_pair_build(protected=True),
        ConsolidationPolicy(
            allow_near_duplicates=True,
            near_perceptual_distance=0.10,
            near_spectral_distance=0.10,
            near_feature_distance=0.10,
            near_maximum_sample_distance=0.10,
            minimum_absolute_correlation=0.95,
            maximum_usefulness_delta=0.10,
            maximum_continuity_degradation=1.0,
        ),
    )
    assert result.mapping is not None
    assert result.mapping.logical_to_physical[10] != result.mapping.logical_to_physical[11]


def test_polarity_equivalence_is_diagnostic_only_by_default() -> None:
    result = consolidate_wavetable_build(polarity_pair_build())
    assert result.mapping is not None
    assert result.final_usefulness is not None
    assert result.mapping.logical_to_physical[20] != result.mapping.logical_to_physical[21]
    assert (20, 21) in result.final_usefulness.polarity_equivalent_pairs
