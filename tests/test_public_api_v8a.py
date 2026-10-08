from __future__ import annotations

import w_mwxt_wavetable_tool as root
import w_mwxt_wavetable_tool.wavetable as wavetable


PUBLIC_NAMES = (
    "DEFAULT_INTERPOLATION_METHODS",
    "FIXED_TAIL_POSITIONS",
    "USER_POSITION_COUNT",
    "WCTD_POSITION_COUNT",
    "ChronologyConstraint",
    "ConstraintStrength",
    "FixedTailContract",
    "GenerationMethod",
    "PositionLock",
    "ProgressionCurve",
    "WaveBuildMetrics",
    "WaveOrigin",
    "WaveRole",
    "WavetableBuild",
    "WavetableBuildPolicy",
    "WavetableBuildRequest",
    "WavetableBuildSet",
    "WavetableBuildStatus",
    "WavetableCandidate",
    "WavetableContractError",
    "WavetableSlot",
    "create_wavetable_build_request",
    "default_wavetable_build_policy",
    "reconstruct_xt_cycle",
    "stored_samples_sha256",
    "validate_candidate_inventory",
)


def test_wavetable_package_exports_complete_v8a_surface() -> None:
    for name in PUBLIC_NAMES:
        assert name in wavetable.__all__
        assert hasattr(wavetable, name)


def test_root_package_reexports_complete_v8a_surface() -> None:
    for name in PUBLIC_NAMES:
        assert hasattr(root, name)


def test_v8a_public_surface_contains_no_midi_transmission_callable() -> None:
    lowered = {name.lower() for name in wavetable.__all__}
    assert not any("transmit" in name for name in lowered)
    assert not any("midi" in name for name in lowered)
