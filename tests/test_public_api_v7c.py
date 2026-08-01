from __future__ import annotations

import w_mwxt_wavetable_tool.xt as xt


def test_v7c_public_api_is_exported() -> None:
    expected = {
        "TRAJECTORY_DEFAULT_STEM",
        "DEFAULT_TARGET_SLOT_COUNT",
        "TRAJECTORY_SCHEMA_VERSION",
        "XtInterpolationCurve",
        "XtPhasePathPolicy",
        "XtTrajectoryAnchor",
        "XtTrajectoryConfig",
        "XtTrajectorySlot",
        "XtTrajectorySlotKind",
        "XtTrajectoryTransition",
        "XtWavetableTrajectory",
        "build_xt_wavetable_trajectory_document",
        "load_and_build_xt_wavetable_trajectory",
    }
    assert expected.issubset(set(xt.__all__))
    for name in expected:
        assert hasattr(xt, name)
