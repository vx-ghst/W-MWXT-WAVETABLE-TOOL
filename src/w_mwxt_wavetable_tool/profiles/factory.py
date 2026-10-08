from __future__ import annotations

from .models import OptimizationProfile, ProfileDefinition
from .weights import weights_for_profile


_ALWAYS_FORBIDDEN = (
    "non_finite",
    "overflow",
    "unsafe_negative_128",
    "unreported_clipping",
)

_PRIORITIES: dict[OptimizationProfile, tuple[str, ...]] = {
    OptimizationProfile.BASS_SUB: (
        "preserve fundamental",
        "preserve H2 and H3",
        "preserve low-frequency power",
        "avoid phase cancellation",
        "maintain inter-wave amplitude",
    ),
    OptimizationProfile.LEAD: (
        "preserve harmonic identity",
        "preserve useful midrange and brightness",
        "control aliasing",
    ),
    OptimizationProfile.PAD: (
        "preserve perceptual balance",
        "favor smooth phase and seams",
        "avoid level dips",
    ),
    OptimizationProfile.BELL_FM: (
        "preserve inharmonic spectral detail",
        "control high-frequency aliasing",
        "retain attack-independent brightness",
    ),
    OptimizationProfile.VOCAL_CHOIR: (
        "preserve midrange spectral envelope",
        "preserve perceptual identity",
        "avoid harsh reconstruction",
    ),
    OptimizationProfile.TEXTURE: (
        "preserve spectral density",
        "preserve audible complexity",
        "control aliasing without flattening texture",
    ),
    OptimizationProfile.DRONE: (
        "preserve fundamental and low spectrum",
        "preserve phase stability",
        "maintain amplitude",
    ),
    OptimizationProfile.PERCUSSIVE: (
        "preserve waveform timing",
        "control seam and ringing",
        "retain useful upper spectrum",
    ),
    OptimizationProfile.EXPERIMENTAL: (
        "preserve controlled aliasing, asymmetry, and saturation",
        "preserve controlled phase error, roughness, and abrupt transitions",
        "retain hard numeric and serialization safety boundaries",
    ),
}


def profile_definition(profile: OptimizationProfile) -> ProfileDefinition:
    selected = OptimizationProfile(profile)
    preserved = (
        (
            "aliasing",
            "asymmetry",
            "saturation",
            "phase_error",
            "roughness",
            "abrupt_transitions",
        )
        if selected is OptimizationProfile.EXPERIMENTAL
        else ()
    )
    reason = (
        "The experimental profile may preserve named controlled defects, but never "
        "non-finite values, overflow, -128 output, or unreported clipping."
        if selected is OptimizationProfile.EXPERIMENTAL
        else "The profile applies explicit normalized weights and forbids unsafe numeric output."
    )
    return ProfileDefinition(
        schema_version=1,
        profile=selected,
        weights=weights_for_profile(selected),
        preserve_controlled_defects=preserved,
        forbidden_defects=_ALWAYS_FORBIDDEN,
        priorities=_PRIORITIES[selected],
        reason=reason,
    )


def all_profile_definitions() -> tuple[ProfileDefinition, ...]:
    return tuple(profile_definition(profile) for profile in OptimizationProfile)
