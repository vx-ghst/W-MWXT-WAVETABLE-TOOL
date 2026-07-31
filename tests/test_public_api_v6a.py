from __future__ import annotations

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool import analysis


EXPECTED = {
    "WorkingPitchCandidate",
    "WorkingPitchCandidateKind",
    "WorkingPitchCandidates",
    "WorkingPitchDecision",
    "WorkingPitchPlan",
    "WorkingPitchPolicy",
    "analyze_audio_source_working_pitch",
    "generate_working_pitch_candidates",
    "plan_working_pitch",
}


def test_analysis_api_exports_code_v6a_contract() -> None:
    for name in EXPECTED:
        assert hasattr(analysis, name), name


def test_top_level_api_exports_code_v6a_contract() -> None:
    for name in EXPECTED:
        assert hasattr(tool, name), name


def test_analysis_all_contains_code_v6a_contract() -> None:
    assert EXPECTED <= set(analysis.__all__)


def test_package_all_contains_code_v6a_contract() -> None:
    assert EXPECTED <= set(tool.__all__)


def test_code_v6a_does_not_advance_release_version() -> None:
    assert tool.__version__ == "0.5.0"
