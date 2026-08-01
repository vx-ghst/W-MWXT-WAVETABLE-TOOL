from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .errors import AnalysisError
from .xt.trajectory import (
    DEFAULT_STEM,
    XtInterpolationCurve,
    XtPhasePathPolicy,
    XtTrajectoryConfig,
    load_and_build_xt_wavetable_trajectory,
)

PROGRAM_NAME = "W-MWXT-XT-TRAJECTORY"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=(
            "Build a deterministic 61-position Microwave XT trajectory from a "
            "CODE V7-B projection report without generating SysEx."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Build the XT-native editable-position trajectory")
    build.add_argument("input", type=Path)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--stem", default=DEFAULT_STEM)
    build.add_argument("--target-slots", type=int, default=61)
    build.add_argument(
        "--phase-policy",
        choices=[policy.value for policy in XtPhasePathPolicy],
        default=XtPhasePathPolicy.GLOBAL.value,
    )
    build.add_argument(
        "--interpolation-curve",
        choices=[curve.value for curve in XtInterpolationCurve],
        default=XtInterpolationCurve.LINEAR.value,
    )
    build.add_argument("--local-fidelity-weight", type=float, default=0.35)
    build.add_argument("--transition-weight", type=float, default=0.65)
    build.add_argument("--transition-time-weight", type=float, default=0.70)
    build.add_argument("--transition-spectral-weight", type=float, default=0.30)
    build.add_argument("--max-objective-increase", type=float, default=0.02)
    build.add_argument("--minimum-intermediates", type=int, default=1)
    build.add_argument("--spacing-power", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        config = XtTrajectoryConfig(
            target_slot_count=args.target_slots,
            phase_path_policy=XtPhasePathPolicy(args.phase_policy),
            interpolation_curve=XtInterpolationCurve(args.interpolation_curve),
            local_fidelity_weight=args.local_fidelity_weight,
            transition_weight=args.transition_weight,
            transition_time_weight=args.transition_time_weight,
            transition_spectral_weight=args.transition_spectral_weight,
            max_objective_increase=args.max_objective_increase,
            minimum_intermediates_per_transition=args.minimum_intermediates,
            spacing_power=args.spacing_power,
        )
        result = load_and_build_xt_wavetable_trajectory(args.input, config=config)
        json_path, markdown_path = result.write(args.output_dir, stem=args.stem)
        summary = {
            "status": "pass",
            "analysis_sha256": result.analysis_sha256,
            "source_projection_set_sha256": result.source_projection_set_sha256,
            "anchor_count": result.anchor_count,
            "interpolated_slot_count": result.interpolated_slot_count,
            "slot_count": len(result.slots),
            "anchor_slot_numbers": list(result.anchor_slot_numbers),
            "phase_change_count": result.phase_change_count,
            "duplicate_adjacent_slot_pair_count": len(result.duplicate_adjacent_slot_pairs),
            "adjacent_distance_summary": result.adjacent_distance_summary,
            "json_report": str(json_path),
            "markdown_report": str(markdown_path),
            "generates_sysex": False,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (AnalysisError, OSError, ValueError) as exc:
        print(f"{PROGRAM_NAME}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
