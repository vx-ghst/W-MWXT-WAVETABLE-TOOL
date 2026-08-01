from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .errors import (
    AnalysisError,
    HardwareValidationError,
    PackageBuildError,
    ProtocolError,
)
from .xt.hardware_package import (
    DEFAULT_STEM,
    XtHardwarePackageStatus,
    load_and_build_xt_hardware_package,
)

PROGRAM_NAME = "W-MWXT-XT-PACKAGE"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=(
            "Build a deterministic CODE V7-E Microwave XT hardware package and exact "
            "restore bundle without opening MIDI ports or transmitting SysEx."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Build the dry-run hardware package")
    build.add_argument("trajectory", type=Path)
    build.add_argument("qc_report", type=Path)
    build.add_argument("baseline", type=Path)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--wave-start", type=int, required=True)
    build.add_argument("--wavetable", type=int, required=True)
    build.add_argument("--sound", required=True)
    build.add_argument(
        "--template-sound",
        help="Baseline Sound used as the synthesis template; defaults to --sound.",
    )
    build.add_argument("--sound-name", required=True)
    build.add_argument("--stem", default=DEFAULT_STEM)
    build.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 3 when one or more generated payloads already match the baseline.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        package = load_and_build_xt_hardware_package(
            args.trajectory,
            args.qc_report,
            args.baseline,
            user_wave_start=args.wave_start,
            wavetable_display_number=args.wavetable,
            sound_destination=args.sound,
            template_sound_destination=args.template_sound,
            sound_name=args.sound_name,
            stem=args.stem,
        )
        paths = package.write(args.output_dir)
        analysis = package.analysis
        summary = {
            "status": analysis.status.value,
            "analysis_sha256": analysis.analysis_sha256,
            "source_trajectory_sha256": analysis.source_trajectory_sha256,
            "source_qc_sha256": analysis.source_qc_sha256,
            "source_projection_set_sha256": analysis.source_projection_set_sha256,
            "baseline_sha256": analysis.baseline_sha256,
            "device_id": analysis.device_id,
            "user_wave_range": [analysis.user_wave_start, analysis.user_wave_end],
            "wavetable_display_number": analysis.wavetable_display_number,
            "sound_destination": analysis.sound_destination,
            "template_sound_destination": analysis.template_sound_destination,
            "sound_name": analysis.sound_name,
            "message_count": analysis.message_count,
            "package_sha256": analysis.package_sha256,
            "restore_bundle_sha256": analysis.restore_bundle_sha256,
            "unchanged_target_count": len(analysis.unchanged_targets),
            "ready_for_v7_f": analysis.ready_for_v7_f,
            "package_sysex": str(paths.package_sysex),
            "user_waves_sysex": str(paths.user_waves_sysex),
            "user_wavetable_sysex": str(paths.user_wavetable_sysex),
            "sound_sysex": str(paths.sound_sysex),
            "restore_sysex": str(paths.restore_sysex),
            "analysis_json": str(paths.analysis_json),
            "analysis_markdown": str(paths.analysis_markdown),
            "sha256_index": str(paths.sha256_index),
            "generates_sysex": True,
            "transmits_midi": False,
            "writes_hardware": False,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
        if args.strict and analysis.status is XtHardwarePackageStatus.REVIEW:
            return 3
        return 0
    except (
        AnalysisError,
        HardwareValidationError,
        PackageBuildError,
        ProtocolError,
        OSError,
        ValueError,
    ) as exc:
        print(f"{PROGRAM_NAME}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
