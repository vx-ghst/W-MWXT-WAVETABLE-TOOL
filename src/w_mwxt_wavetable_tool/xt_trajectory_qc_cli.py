from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .errors import AnalysisError
from .xt.trajectory_qc import (
    DEFAULT_STEM,
    XtTrajectoryQcConfig,
    XtTrajectoryQcStatus,
    load_and_analyze_xt_trajectory_qc,
)

PROGRAM_NAME = "W-MWXT-XT-QC"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=(
            "Audit a CODE V7-C 61-slot XT trajectory and render deterministic "
            "mathematical audition WAV files without generating SysEx."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="Audit the trajectory and render deterministic previews")
    audit.add_argument("trajectory", type=Path)
    audit.add_argument("--projection-report", type=Path)
    audit.add_argument("--output-dir", type=Path, required=True)
    audit.add_argument("--stem", default=DEFAULT_STEM)
    audit.add_argument("--time-weight", type=float, default=0.70)
    audit.add_argument("--spectral-weight", type=float, default=0.30)
    audit.add_argument("--jump-absolute-minimum", type=float, default=0.020)
    audit.add_argument("--jump-median-multiplier", type=float, default=2.50)
    audit.add_argument("--jump-mad-multiplier", type=float, default=6.00)
    audit.add_argument("--curvature-absolute-minimum", type=float, default=0.015)
    audit.add_argument("--curvature-median-multiplier", type=float, default=3.00)
    audit.add_argument("--curvature-mad-multiplier", type=float, default=6.00)
    audit.add_argument("--sample-rate", type=int, default=48_000)
    audit.add_argument("--preview-frequency", type=float, default=110.0)
    audit.add_argument("--sweep-duration", type=float, default=12.0)
    audit.add_argument("--slot-duration", type=float, default=0.10)
    audit.add_argument("--transition-fraction", type=float, default=0.20)
    audit.add_argument("--fade-duration", type=float, default=0.02)
    audit.add_argument("--preview-peak", type=float, default=0.80)
    audit.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 3 when the deterministic QC status is review.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        config = XtTrajectoryQcConfig(
            time_weight=args.time_weight,
            spectral_weight=args.spectral_weight,
            jump_absolute_minimum=args.jump_absolute_minimum,
            jump_median_multiplier=args.jump_median_multiplier,
            jump_mad_multiplier=args.jump_mad_multiplier,
            curvature_absolute_minimum=args.curvature_absolute_minimum,
            curvature_median_multiplier=args.curvature_median_multiplier,
            curvature_mad_multiplier=args.curvature_mad_multiplier,
            sample_rate=args.sample_rate,
            preview_frequency_hz=args.preview_frequency,
            sweep_duration_seconds=args.sweep_duration,
            stepped_slot_duration_seconds=args.slot_duration,
            transition_fraction=args.transition_fraction,
            fade_duration_seconds=args.fade_duration,
            preview_peak=args.preview_peak,
        )
        build = load_and_analyze_xt_trajectory_qc(
            args.trajectory,
            projection_path=args.projection_report,
            config=config,
        )
        json_path, markdown_path, preview_paths = build.write(
            args.output_dir,
            stem=args.stem,
        )
        analysis = build.analysis
        summary = {
            "status": analysis.status.value,
            "analysis_sha256": analysis.analysis_sha256,
            "source_trajectory_sha256": analysis.source_trajectory_sha256,
            "source_projection_set_sha256": analysis.source_projection_set_sha256,
            "adjacent_pair_count": len(analysis.adjacent_pairs),
            "curvature_point_count": len(analysis.curvatures),
            "phase_changed_anchor_count": len(analysis.phase_neighborhoods),
            "flagged_jump_count": analysis.flagged_jump_count,
            "flagged_curvature_count": analysis.flagged_curvature_count,
            "maximum_adjacent_distance": analysis.maximum_adjacent_distance,
            "mean_adjacent_distance": analysis.mean_adjacent_distance,
            "maximum_curvature": analysis.maximum_curvature,
            "baseline_comparison_included": analysis.baseline_comparison is not None,
            "json_report": str(json_path),
            "markdown_report": str(markdown_path),
            "preview_files": [str(path) for path in preview_paths],
            "modifies_trajectory_slots": False,
            "generates_sysex": False,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
        if args.strict and analysis.status is XtTrajectoryQcStatus.REVIEW:
            return 3
        return 0
    except (AnalysisError, OSError, ValueError) as exc:
        print(f"{PROGRAM_NAME}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
