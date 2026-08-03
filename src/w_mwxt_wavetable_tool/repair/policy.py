from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..errors import AnalysisError
from ..profiles import OptimizationProfile
from .models import (
    RepairDefect,
    RepairPolicy,
    RepairPolicyRule,
    RepairPolicySet,
)


_EXPERIMENTAL_PRESERVE = (
    RepairDefect.CLIPPING,
    RepairDefect.PHASE_INVERSION,
    RepairDefect.START_END_MISMATCH,
    RepairDefect.PARASITIC_NOISE,
    RepairDefect.SPECTRAL_JUMP,
    RepairDefect.EXCESSIVE_ALIASING,
)


def _coerce_overrides(
    overrides: Mapping[RepairDefect | str, RepairPolicy | str]
    | Sequence[RepairPolicyRule]
    | None,
) -> tuple[RepairPolicyRule, ...]:
    if overrides is None:
        return ()
    if isinstance(overrides, Mapping):
        converted = {
            RepairDefect(defect): RepairPolicy(policy)
            for defect, policy in overrides.items()
        }
        return tuple(
            RepairPolicyRule(defect, converted[defect])
            for defect in RepairDefect
            if defect in converted
        )
    rules = tuple(overrides)
    if any(not isinstance(rule, RepairPolicyRule) for rule in rules):
        raise AnalysisError("repair policy override sequences require RepairPolicyRule values")
    by_defect = {rule.defect: rule.policy for rule in rules}
    if len(by_defect) != len(rules):
        raise AnalysisError("repair policy overrides must be unique by defect")
    return tuple(
        RepairPolicyRule(defect, by_defect[defect])
        for defect in RepairDefect
        if defect in by_defect
    )


def build_repair_policy_set(
    *,
    default_policy: RepairPolicy | str = RepairPolicy.AUTO,
    overrides: Mapping[RepairDefect | str, RepairPolicy | str]
    | Sequence[RepairPolicyRule]
    | None = None,
    reason: str = "Explicit deterministic Auto Repair policy set.",
) -> RepairPolicySet:
    return RepairPolicySet(
        schema_version=1,
        default_policy=RepairPolicy(default_policy),
        overrides=_coerce_overrides(overrides),
        reason=reason,
    )


def repair_policy_for_profile(
    profile: OptimizationProfile | str,
    *,
    default_policy: RepairPolicy | str = RepairPolicy.AUTO,
    overrides: Mapping[RepairDefect | str, RepairPolicy | str]
    | Sequence[RepairPolicyRule]
    | None = None,
) -> RepairPolicySet:
    selected_profile = OptimizationProfile(profile)
    merged: dict[RepairDefect, RepairPolicy] = {}
    if selected_profile is OptimizationProfile.EXPERIMENTAL:
        merged.update(
            {defect: RepairPolicy.PRESERVE for defect in _EXPERIMENTAL_PRESERVE}
        )
    for rule in _coerce_overrides(overrides):
        merged[rule.defect] = rule.policy
    reason = (
        "Experimental profile explicitly preserves controlled defects while hard "
        "numeric safety remains mandatory."
        if selected_profile is OptimizationProfile.EXPERIMENTAL
        else f"Profile {selected_profile.value} uses the requested repair policies."
    )
    return build_repair_policy_set(
        default_policy=default_policy,
        overrides=merged,
        reason=reason,
    )


def replace_repair_policy(
    policy_set: RepairPolicySet,
    defect: RepairDefect | str,
    policy: RepairPolicy | str,
    *,
    reason: str | None = None,
) -> RepairPolicySet:
    selected_defect = RepairDefect(defect)
    selected_policy = RepairPolicy(policy)
    merged = {
        item.defect: item.policy
        for item in policy_set.overrides
    }
    merged[selected_defect] = selected_policy
    return build_repair_policy_set(
        default_policy=policy_set.default_policy,
        overrides=merged,
        reason=policy_set.reason if reason is None else reason,
    )


__all__ = [
    "build_repair_policy_set",
    "repair_policy_for_profile",
    "replace_repair_policy",
]
