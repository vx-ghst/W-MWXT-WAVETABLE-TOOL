from __future__ import annotations

import w_mwxt_wavetable_tool as root
import w_mwxt_wavetable_tool.wavetable as wavetable


EXPECTED_V8B_EXPORTS = {
    "DEFAULT_DEDUPLICATION_THRESHOLDS",
    "DEFAULT_USEFULNESS_THRESHOLDS",
    "WAVETABLE_DEDUPLICATION_SCHEMA_VERSION",
    "WAVETABLE_METRICS_SCHEMA_VERSION",
    "WAVETABLE_USEFULNESS_SCHEMA_VERSION",
    "BreakpointKind",
    "CandidateDeduplicationAnalysis",
    "CandidateStructureClass",
    "CandidateUsefulnessAnalysis",
    "CodeV8BAnalysis",
    "DeduplicationThresholds",
    "DuplicateGroupAnalysis",
    "DuplicateKind",
    "DuplicatePairAnalysis",
    "IntervalClass",
    "UsefulnessThresholds",
    "WavePairDistance",
    "WaveShapeMetrics",
    "WavetableDeduplicationAnalysis",
    "WavetableIntervalAnalysis",
    "WavetableStructureAnalysis",
    "analyze_candidate_deduplication",
    "analyze_candidate_structure",
    "analyze_wave_shape",
    "analyze_wavetable_candidates",
    "compare_wave_shapes",
}


def test_wavetable_package_exports_complete_v8b_surface():
    assert EXPECTED_V8B_EXPORTS.issubset(set(wavetable.__all__))
    for name in EXPECTED_V8B_EXPORTS:
        assert getattr(wavetable, name) is not None


def test_root_package_exports_complete_v8b_surface():
    assert EXPECTED_V8B_EXPORTS.issubset(set(root.__all__))
    for name in EXPECTED_V8B_EXPORTS:
        assert getattr(root, name) is getattr(wavetable, name)


def test_v8a_exports_remain_present():
    for name in (
        "WavetableCandidate",
        "WavetableBuildRequest",
        "WavetableBuild",
        "WavetableBuildSet",
        "create_wavetable_build_request",
        "reconstruct_xt_cycle",
    ):
        assert name in wavetable.__all__
        assert hasattr(root, name)
