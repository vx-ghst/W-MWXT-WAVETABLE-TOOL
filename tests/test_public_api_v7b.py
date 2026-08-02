from __future__ import annotations

import w_mwxt_wavetable_tool.xt as xt


def test_v7b_public_api_is_exported() -> None:
    for name in (
        "PROJECTION_SCHEMA_VERSION",
        "XtProjectionWeights",
        "XtProjectionMetrics",
        "XtProjectedWave",
        "XtProjectionSet",
        "project_wave_xt_native",
        "project_reconstructed_wave_set_xt_native",
        "project_code_v6_analysis_xt_native",
        "reconstruct_xt_native",
    ):
        assert hasattr(xt, name), name
