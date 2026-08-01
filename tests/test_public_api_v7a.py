from __future__ import annotations

import w_mwxt_wavetable_tool.xt as xt


def test_code_v7_a_public_subpackage_contract() -> None:
    expected = {
        "XtGateAnalysis",
        "XtGateBuild",
        "XtGatePattern",
        "XtGateProbe",
        "XtGateStatus",
        "XtGateVerdict",
        "XtReconstructionGatePlan",
        "XtReconstructionHypothesis",
        "analyze_xt_reconstruction_gate",
        "build_xt_reconstruction_gate",
        "generate_xt_gate_probes",
        "parse_observation_document",
        "reconstruct_probe",
        "verify_xt_reconstruction_gate_restore",
    }
    assert expected <= set(xt.__all__)
    for name in expected:
        assert getattr(xt, name) is not None
