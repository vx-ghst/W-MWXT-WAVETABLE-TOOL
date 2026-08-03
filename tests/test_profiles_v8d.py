from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.decision.models import ConversionMode, MusicalClass
from w_mwxt_wavetable_tool.decision.profile_selector import select_optimization_profile
from w_mwxt_wavetable_tool.profiles import (
    PROFILE_METRIC_NAMES,
    OptimizationProfile,
    ProfileWeights,
    all_profile_definitions,
    profile_definition,
)


def _classification(selected: MusicalClass):
    scores = tuple(
        SimpleNamespace(musical_class=item, score=1.0 if item is selected else 0.0)
        for item in MusicalClass
    )
    return SimpleNamespace(
        analysis_sha256="1" * 64,
        scores=scores,
        selected_classes=(selected,),
    )


def _mode(mode: ConversionMode | None):
    return SimpleNamespace(analysis_sha256="2" * 64, selected_mode=mode)


def test_nine_profile_definitions_are_canonical_and_hashed() -> None:
    definitions = all_profile_definitions()
    assert tuple(item.profile for item in definitions) == tuple(OptimizationProfile)
    assert len(definitions) == 9
    assert len({item.profile_sha256 for item in definitions}) == 9
    for item in definitions:
        assert math.isclose(sum(item.weights.weight_map.values()), 1.0, abs_tol=1e-12)
        assert tuple(item.weights.weight_map) == PROFILE_METRIC_NAMES


def test_experimental_preserves_only_named_controlled_defects() -> None:
    definition = profile_definition(OptimizationProfile.EXPERIMENTAL)
    assert definition.preserve_controlled_defects == (
        "aliasing",
        "asymmetry",
        "saturation",
        "phase_error",
        "roughness",
        "abrupt_transitions",
    )
    assert "overflow" in definition.forbidden_defects
    assert "unsafe_negative_128" in definition.forbidden_defects


@pytest.mark.parametrize("profile", [item for item in OptimizationProfile if item is not OptimizationProfile.EXPERIMENTAL])
def test_non_experimental_profiles_do_not_preserve_defects(profile: OptimizationProfile) -> None:
    assert profile_definition(profile).preserve_controlled_defects == ()


def test_profile_weights_reject_non_normalized_vector() -> None:
    with pytest.raises(ValueError, match="sum exactly"):
        ProfileWeights(**{name: 0.1 for name in PROFILE_METRIC_NAMES})


@pytest.mark.parametrize(
    ("musical_class", "expected"),
    [
        (MusicalClass.SUB, OptimizationProfile.BASS_SUB),
        (MusicalClass.LEAD, OptimizationProfile.LEAD),
        (MusicalClass.PAD, OptimizationProfile.PAD),
        (MusicalClass.BELL, OptimizationProfile.BELL_FM),
        (MusicalClass.VOCAL, OptimizationProfile.VOCAL_CHOIR),
        (MusicalClass.TEXTURE, OptimizationProfile.TEXTURE),
        (MusicalClass.DRONE, OptimizationProfile.DRONE),
        (MusicalClass.PERCUSSION, OptimizationProfile.PERCUSSIVE),
        (MusicalClass.FX, OptimizationProfile.EXPERIMENTAL),
    ],
)
def test_profile_selector_maps_canonical_roles(musical_class: MusicalClass, expected: OptimizationProfile) -> None:
    result = select_optimization_profile(
        _classification(musical_class),
        _mode(ConversionMode.STABLE_CYCLE),
        mode_prior_cap=0.0,
    )
    assert result.selected_profile is expected
    assert math.isclose(sum(result.score_map.values()), 1.0, abs_tol=1e-12)


def test_mode_prior_is_bounded_and_does_not_override_strong_sub_class() -> None:
    result = select_optimization_profile(
        _classification(MusicalClass.SUB),
        _mode(ConversionMode.SPECTRAL_RECONSTRUCTION),
        mode_prior_cap=0.20,
    )
    assert result.selected_profile is OptimizationProfile.BASS_SUB
    assert "mode_prior_cap=0.200000" in result.evidence


def test_profile_override_preserves_automatic_evidence() -> None:
    result = select_optimization_profile(
        _classification(MusicalClass.SUB),
        _mode(ConversionMode.STABLE_CYCLE),
        requested_override=OptimizationProfile.EXPERIMENTAL,
    )
    assert result.selected_profile is OptimizationProfile.EXPERIMENTAL
    assert result.requested_override is OptimizationProfile.EXPERIMENTAL
    assert any("automatic bass_sub" in item for item in result.warnings)
    assert any("automatic_profile=bass_sub" == item for item in result.evidence)


@pytest.mark.parametrize("invalid", [-0.1, 0.251, float("nan")])
def test_mode_prior_cap_is_strict(invalid: float) -> None:
    with pytest.raises(ValueError, match="mode_prior_cap"):
        select_optimization_profile(
            _classification(MusicalClass.LEAD),
            _mode(ConversionMode.STABLE_CYCLE),
            mode_prior_cap=invalid,
        )
