from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

CLEAN_TEST_GROUPS = {
    "audio_import_preprocessing": (
        "tests/test_audio_import.py", "tests/test_audio_measurements.py",
        "tests/test_audio_preprocessing.py", "tests/test_audio_mono.py",
        "tests/test_audio_mono_policies.py", "tests/test_analysis_time_domain.py",
        "tests/test_analysis_signal.py", "tests/test_analysis_signal_extensions.py",
        "tests/test_analysis_levels.py", "tests/test_analysis_saturation.py",
        "tests/test_analysis_noise.py",
    ),
    "pitch_periodicity_repitch_cycles": (
        "tests/test_analysis_pitch.py", "tests/test_analysis_periodicity.py",
        "tests/test_analysis_pitch_candidates.py", "tests/test_analysis_repitch.py",
        "tests/test_analysis_cycle_detection.py", "tests/test_analysis_cycle_selection.py",
        "tests/test_analysis_reconstruction.py", "tests/test_analysis_phase_motion.py",
        "tests/test_analysis_beating.py", "tests/test_analysis_frequency_modulation.py",
        "tests/test_cli_pitch_periodicity.py", "tests/test_cli_working_pitch.py",
        "tests/test_cli_cycle_detection.py", "tests/test_cli_cycle_selection.py",
        "tests/test_cli_reconstruction.py", "tests/test_cli_phase_motion.py",
    ),
    "repair_cleaning": (
        "tests/test_repair_models_v8e.py", "tests/test_repair_detectors_v8e.py",
        "tests/test_repair_actions_v8e.py", "tests/test_repair_policy_v8e.py",
        "tests/test_repair_engine_v8e.py", "tests/test_repair_sequence_v8e.py",
    ),
    "resampling_quantization_optimization": (
        "tests/test_resampling_v8d.py", "tests/test_quantization_v8d.py",
        "tests/test_metrics_optimizer_v8d.py", "tests/test_profiles_v8d.py",
        "tests/test_xt_projection.py", "tests/test_xt_projection_cli.py",
        "tests/test_xt_reconstruction_gate.py",
    ),
    "continuity_interpolation_transitions": (
        "tests/test_wavetable_continuity_v8e.py", "tests/test_wavetable_density_v8e.py",
        "tests/test_wavetable_interpolation_v8e.py",
        "tests/test_wavetable_transition_pathologies_v8g.py",
        "tests/test_wavetable_transition_planner_v8g.py",
        "tests/test_transition_shaping_migration_v8h.py",
    ),
}

EXPECTED_REPAIR_DEFECTS = (
    "DC_OFFSET", "CLIPPING", "ZERO_CROSSING", "LOOP_DISCONTINUITY",
    "DERIVATIVE_DISCONTINUITY", "PHASE_INVERSION", "POLARITY_INVERSION",
    "START_END_MISMATCH", "AMPLITUDE_INCONSISTENCY", "CYCLE_LENGTH",
    "PITCH_ESTIMATE", "PARASITIC_NOISE", "FUNDAMENTAL_LOSS", "SPECTRAL_JUMP",
    "INTER_WAVE_LEVEL_MISMATCH", "REDUNDANT_WAVE", "EXCESSIVE_ALIASING",
)
EXPECTED_REPAIR_ACTIONS = (
    "REMOVE_DC", "RECONSTRUCT_CLIPPED_PEAKS", "ROTATE_TO_ZERO_CROSSING",
    "SMOOTH_LOOP_SEAM", "SMOOTH_SEAM_DERIVATIVE", "ALIGN_PHASE_TO_REFERENCE",
    "INVERT_POLARITY", "REDUCE_START_END_MISMATCH", "MATCH_REFERENCE_AMPLITUDE",
    "RESAMPLE_CYCLE_LENGTH", "UPDATE_PITCH_ESTIMATE", "REDUCE_PARASITIC_NOISE",
    "RESTORE_FUNDAMENTAL", "SMOOTH_SPECTRAL_TRANSITION", "MATCH_INTER_WAVE_LEVEL",
    "INTERPOLATE_REDUNDANT_WAVE", "REDUCE_ALIASING",
)
EXPECTED_REPITCH_POLICIES = ("AUTO", "NO_REPITCH", "LOCK")


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build_clean_optimization_inventory(repo: Path, output_path: Path) -> dict[str, Any]:
    repo = repo.resolve()
    import sys
    for item in (repo / "src", repo / "tests"):
        if str(item) not in sys.path:
            sys.path.insert(0, str(item))
    from w_mwxt_wavetable_tool.repair.models import RepairActionKind, RepairDefect
    from w_mwxt_wavetable_tool.repair.engine import _ACTION_ORDER
    from w_mwxt_wavetable_tool.analysis.repitch import WorkingPitchPolicy

    test_rows=[]
    missing=[]
    for group, relatives in CLEAN_TEST_GROUPS.items():
        rows=[]
        for relative in relatives:
            path=repo/relative
            exists=path.is_file()
            rows.append({"path":relative,"exists":exists,"sha256":_hash(path) if exists else None})
            if not exists: missing.append(relative)
        test_rows.append({"group":group,"tests":rows})

    repair_test_text="\n".join(
        path.read_text(encoding="utf-8",errors="replace")
        for path in sorted((repo/"tests").glob("test_repair_*v8e.py"))
    )
    defects=[item.name for item in RepairDefect]
    actions=[item.name for item in RepairActionKind]
    policies=[item.name for item in WorkingPitchPolicy]
    defect_mentions={name:(name in repair_test_text) for name in defects}
    order=[item.name for item in _ACTION_ORDER]

    checks={
        "all_expected_repair_defects_present": set(defects)==set(EXPECTED_REPAIR_DEFECTS),
        "all_repair_defects_in_engine_order": set(order)==set(defects) and len(order)==len(defects),
        "all_repair_defects_mentioned_by_tests": all(defect_mentions.values()),
        "all_expected_repair_actions_present": set(actions)==set(EXPECTED_REPAIR_ACTIONS),
        "repitch_policies_present": set(EXPECTED_REPITCH_POLICIES).issubset(set(policies)),
        "all_declared_test_files_exist": not missing,
    }
    payload={
        "schema_version":1,
        "scope":"cleaning, optimization, repitch, DC offset, repair, resampling, quantization, continuity and transition validation",
        "repair_defects":defects,
        "repair_actions":actions,
        "repair_engine_order":order,
        "repair_defect_test_mentions":defect_mentions,
        "working_pitch_policies":policies,
        "test_groups":test_rows,
        "checks":checks,
        "all_pass":all(checks.values()),
        "hardware_claim":False,
        "production_code_changed":False,
    }
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if not payload["all_pass"]:
        raise RuntimeError(f"Clean/optimization inventory failed: {checks}; missing={missing}")
    return payload
