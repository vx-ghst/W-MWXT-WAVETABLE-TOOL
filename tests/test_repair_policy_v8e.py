from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.profiles import OptimizationProfile
from w_mwxt_wavetable_tool.repair import (
    RepairDefect,
    RepairPolicy,
    build_repair_policy_set,
    repair_policy_for_profile,
    replace_repair_policy,
)


@pytest.mark.parametrize("policy", tuple(RepairPolicy))
def test_build_policy_supports_all_four_states(policy: RepairPolicy) -> None:
    result = build_repair_policy_set(default_policy=policy)
    assert all(result.policy_for(defect) is policy for defect in RepairDefect)


def test_explicit_override_wins_over_default() -> None:
    result = build_repair_policy_set(
        default_policy=RepairPolicy.AUTO,
        overrides={RepairDefect.CLIPPING: RepairPolicy.COMPARE},
    )
    assert result.policy_for(RepairDefect.CLIPPING) is RepairPolicy.COMPARE
    assert result.policy_for(RepairDefect.DC_OFFSET) is RepairPolicy.AUTO


def test_experimental_profile_preserves_controlled_defects() -> None:
    result = repair_policy_for_profile(OptimizationProfile.EXPERIMENTAL)
    for defect in (
        RepairDefect.CLIPPING,
        RepairDefect.PHASE_INVERSION,
        RepairDefect.START_END_MISMATCH,
        RepairDefect.PARASITIC_NOISE,
        RepairDefect.SPECTRAL_JUMP,
        RepairDefect.EXCESSIVE_ALIASING,
    ):
        assert result.policy_for(defect) is RepairPolicy.PRESERVE
    assert result.policy_for(RepairDefect.DC_OFFSET) is RepairPolicy.AUTO


@pytest.mark.parametrize(
    "profile",
    tuple(
        profile
        for profile in OptimizationProfile
        if profile is not OptimizationProfile.EXPERIMENTAL
    ),
)
def test_non_experimental_profiles_default_to_auto(profile: OptimizationProfile) -> None:
    result = repair_policy_for_profile(profile)
    assert all(result.policy_for(defect) is RepairPolicy.AUTO for defect in RepairDefect)


def test_explicit_override_wins_over_experimental_preserve() -> None:
    result = repair_policy_for_profile(
        OptimizationProfile.EXPERIMENTAL,
        overrides={RepairDefect.CLIPPING: RepairPolicy.COMPARE},
    )
    assert result.policy_for(RepairDefect.CLIPPING) is RepairPolicy.COMPARE


def test_replace_policy_is_immutable() -> None:
    original = build_repair_policy_set()
    changed = replace_repair_policy(
        original,
        RepairDefect.DC_OFFSET,
        RepairPolicy.IGNORE,
    )
    assert original.policy_for(RepairDefect.DC_OFFSET) is RepairPolicy.AUTO
    assert changed.policy_for(RepairDefect.DC_OFFSET) is RepairPolicy.IGNORE
    assert changed.analysis_sha256 != original.analysis_sha256


def test_mapping_accepts_string_values() -> None:
    result = build_repair_policy_set(
        default_policy="compare",
        overrides={"dc_offset": "ignore"},
    )
    assert result.default_policy is RepairPolicy.COMPARE
    assert result.policy_for(RepairDefect.DC_OFFSET) is RepairPolicy.IGNORE


def test_invalid_policy_value_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_repair_policy_set(default_policy="invalid")


def test_invalid_override_sequence_is_rejected() -> None:
    with pytest.raises(AnalysisError):
        build_repair_policy_set(overrides=[object()])  # type: ignore[list-item]
