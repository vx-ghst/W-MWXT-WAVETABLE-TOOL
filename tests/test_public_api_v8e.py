from __future__ import annotations

from dataclasses import fields

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool.analysis.code_v5 import CodeV5Analysis
from w_mwxt_wavetable_tool.analysis.code_v6 import CodeV6Analysis
from w_mwxt_wavetable_tool.repair import RepairDefect
from w_mwxt_wavetable_tool.xt.projection import XtProjectionMetrics


PUBLIC_NAMES = (
    "AutoRepairResult",
    "AutoRepairSequenceEntry",
    "AutoRepairSequenceResult",
    "RepairActionKind",
    "RepairActionRecord",
    "RepairActionStatus",
    "RepairApplication",
    "RepairComparison",
    "RepairContext",
    "RepairDefect",
    "RepairFinding",
    "RepairPolicy",
    "RepairPolicyRule",
    "RepairPolicySet",
    "RepairSeverity",
    "RepairThresholds",
    "RepairWaveMetrics",
    "apply_repair_action",
    "auto_repair_wave",
    "auto_repair_wave_sequence",
    "build_repair_policy_set",
    "detect_wave_defects",
    "measure_repair_wave",
    "repair_policy_for_profile",
    "replace_repair_policy",
)


def test_all_repair_names_are_exported_from_package_root() -> None:
    for name in PUBLIC_NAMES:
        assert hasattr(tool, name), name
        assert name in tool.__all__


def test_package_root_and_repair_enum_are_identical() -> None:
    assert tool.RepairDefect is RepairDefect


def test_code_v5_schema_fields_remain_unchanged() -> None:
    assert tuple(field.name for field in fields(CodeV5Analysis)) == (
        "schema_version",
        "tool_version",
        "sample_rate",
        "sample_count",
        "sample_sha256",
        "signal_analysis",
        "spectral_analysis",
        "harmonic_perceptual_analysis",
        "source_classification",
        "engineering_decision",
    )


def test_code_v6_schema_fields_remain_unchanged() -> None:
    assert tuple(field.name for field in fields(CodeV6Analysis)) == (
        "schema_version",
        "tool_version",
        "sample_rate",
        "sample_count",
        "sample_sha256",
        "code_v5_analysis",
        "working_pitch_plan",
        "segmentation_analysis",
        "cycle_discovery_analysis",
        "selected_cycle_set",
        "reconstructed_wave_set",
    )


def test_v7_projection_metrics_schema_remains_unchanged() -> None:
    assert tuple(field.name for field in fields(XtProjectionMetrics)) == (
        "source_rms",
        "reconstructed_rms",
        "source_peak",
        "reconstructed_peak",
        "time_rmse",
        "time_nrmse",
        "maximum_absolute_error",
        "correlation",
        "spectral_rmse",
        "spectral_similarity",
        "h1_error",
        "h2_error",
        "h3_error",
        "low_band_error",
        "mid_band_error",
        "high_band_error",
        "seam_value_error",
        "seam_slope_error",
        "objective_score",
    )


def test_version_remains_0_7_0_until_v8_release_gate() -> None:
    assert tool.__version__ == "0.7.0"
