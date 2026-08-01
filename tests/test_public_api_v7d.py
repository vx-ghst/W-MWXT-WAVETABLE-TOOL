from __future__ import annotations

import w_mwxt_wavetable_tool.xt as xt


def test_v7d_public_api_is_exported() -> None:
    expected = {
        "TRAJECTORY_QC_DEFAULT_STEM",
        "TRAJECTORY_QC_SCHEMA_VERSION",
        "XtAdjacentSlotAudit",
        "XtBaselineComparison",
        "XtCurvatureAudit",
        "XtPhaseNeighborhoodAudit",
        "XtPreviewArtifact",
        "XtTrajectoryQcAnalysis",
        "XtTrajectoryQcBuild",
        "XtTrajectoryQcConfig",
        "XtTrajectoryQcStatus",
        "analyze_xt_trajectory_qc_documents",
        "load_and_analyze_xt_trajectory_qc",
    }
    assert expected <= set(xt.__all__)
    for name in expected:
        assert hasattr(xt, name)
