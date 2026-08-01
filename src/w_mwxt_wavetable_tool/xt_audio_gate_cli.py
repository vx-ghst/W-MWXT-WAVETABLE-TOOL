from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from .dump import DumpFile
from .xt.audio_gate import (
    DEFAULT_STEM,
    XtAudioGatePlan,
    XtAudioGateStatus,
    analyze_xt_audio_gate,
    build_xt_audio_gate,
    verify_xt_audio_gate_restore,
    verify_xt_audio_gate_setup,
)

PROGRAM_NAME = "W-MWXT-XT-AUDIO-GATE"


def _read_json(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return data, sha256(raw).hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=(
            "Build, verify, analyze, and restore the CODE V7-A.2 controlled "
            "Microwave XT audio gate."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build the complete controlled audio kit")
    build.add_argument("baseline", type=Path)
    build.add_argument("v7a1_storage_analysis", type=Path)
    build.add_argument("v7a1_restore_analysis", type=Path)
    build.add_argument("--target-wave-start", type=int, default=1247)
    build.add_argument("--target-wavetable", type=int, default=128)
    build.add_argument("--target-sound", default="B128")
    build.add_argument("--seed", type=int, default=0x57A)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--stem", default=DEFAULT_STEM)

    verify_setup = sub.add_parser(
        "verify-setup", help="Verify waves, wavetable, and Sound after setup"
    )
    verify_setup.add_argument("expected_setup", type=Path)
    verify_setup.add_argument("readback", type=Path)
    verify_setup.add_argument("manifest", type=Path)
    verify_setup.add_argument("--output-dir", type=Path, required=True)
    verify_setup.add_argument("--stem", default=f"{DEFAULT_STEM}.setup-analysis")

    analyze = sub.add_parser(
        "analyze", help="Analyze all required mono WAV captures in a directory"
    )
    analyze.add_argument("captures_dir", type=Path)
    analyze.add_argument("manifest", type=Path)
    analyze.add_argument("--output-dir", type=Path, required=True)
    analyze.add_argument("--stem", default=f"{DEFAULT_STEM}.analysis")

    verify_restore = sub.add_parser(
        "verify-restore", help="Verify exact restoration of all five overwritten objects"
    )
    verify_restore.add_argument("expected_restore", type=Path)
    verify_restore.add_argument("readback", type=Path)
    verify_restore.add_argument("manifest", type=Path)
    verify_restore.add_argument("--output-dir", type=Path, required=True)
    verify_restore.add_argument("--stem", default=f"{DEFAULT_STEM}.restore-analysis")
    return parser


def _write_sysex_analysis(analysis, output_dir: Path, stem: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(analysis.to_json(), encoding="utf-8", newline="\n")
    markdown_path.write_text(analysis.to_markdown(), encoding="utf-8", newline="\n")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "build":
            storage_report, storage_hash = _read_json(args.v7a1_storage_analysis)
            restore_report, restore_hash = _read_json(args.v7a1_restore_analysis)
            baseline = DumpFile.from_bytes(args.baseline.read_bytes())
            build = build_xt_audio_gate(
                baseline,
                v7a1_storage_report=storage_report,
                v7a1_restore_report=restore_report,
                v7a1_storage_report_sha256=storage_hash,
                v7a1_restore_report_sha256=restore_hash,
                target_wave_start=args.target_wave_start,
                target_wavetable_display=args.target_wavetable,
                target_sound_location=args.target_sound,
                seed=args.seed,
                stem=args.stem,
            )
            paths = build.write(args.output_dir, stem=args.stem)
            print(
                json.dumps(
                    {
                        "status": "READY" if build.ready_for_transmission else "BLOCKED",
                        "schema_version": build.plan.schema_version,
                        "audio_gate_plan_sha256": build.plan.plan_sha256,
                        "device_id": build.plan.device_id,
                        "target_waves": list(build.plan.target_wave_numbers),
                        "target_wavetable": build.plan.target_wavetable_display,
                        "target_sound": build.plan.target_sound_location,
                        "setup": str(paths.setup),
                        "select_safe": str(paths.select_safe),
                        "select_offset_binary": str(paths.select_offset_binary),
                        "select_negative_full_scale": str(paths.select_negative_full_scale),
                        "restore": str(paths.restore),
                        "manifest_json": str(paths.manifest_json),
                        "manifest_markdown": str(paths.manifest_markdown),
                        "capture_plan_json": str(paths.capture_plan_json),
                        "midi_clips": [
                            str(paths.midi_c2),
                            str(paths.midi_c3),
                            str(paths.midi_c4),
                        ],
                        "required_capture_count": len(
                            [c for c in build.plan.captures if c.required]
                        ),
                        "critical_boundary": (
                            "The kit controls documented Sound parameters and preserves "
                            "reserved bytes from the fresh backup. Audio analysis ranks "
                            "structural hypotheses; it is not bit-exact DSP emulation."
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
            return 0 if build.ready_for_transmission else 2

        plan = XtAudioGatePlan.from_json(args.manifest.read_text(encoding="utf-8-sig"))

        if args.command == "verify-setup":
            expected = DumpFile.from_bytes(args.expected_setup.read_bytes())
            readback = DumpFile.from_bytes(args.readback.read_bytes())
            analysis = verify_xt_audio_gate_setup(expected, readback, plan)
            json_path, markdown_path = _write_sysex_analysis(
                analysis, args.output_dir, args.stem
            )
            print(
                json.dumps(
                    {
                        "status": analysis.status.value,
                        "verdict": analysis.verdict.value,
                        "exact": analysis.exact,
                        "analysis_sha256": analysis.analysis_sha256,
                        "json_report": str(json_path),
                        "markdown_report": str(markdown_path),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0 if analysis.status is XtAudioGateStatus.PASS else 2

        if args.command == "analyze":
            result = analyze_xt_audio_gate(args.captures_dir, plan)
            paths = result.write(args.output_dir, stem=args.stem)
            analysis = result.analysis
            print(
                json.dumps(
                    {
                        "status": analysis.status.value,
                        "verdict": analysis.verdict.value,
                        "safe_reconstruction_status": analysis.safe_reconstruction_status,
                        "negative_full_scale_status": analysis.negative_full_scale_status,
                        "v7_b_allowed_under_safe_range": (
                            analysis.v7_b_allowed_under_safe_range
                        ),
                        "required_capture_count": analysis.required_capture_count,
                        "present_capture_count": analysis.present_capture_count,
                        "missing_captures": list(analysis.missing_captures),
                        "analysis_sha256": analysis.analysis_sha256,
                        "json_report": str(paths.json_report),
                        "markdown_report": str(paths.markdown_report),
                    },
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
            return 0 if analysis.status is XtAudioGateStatus.PASS else 2

        if args.command == "verify-restore":
            expected = DumpFile.from_bytes(args.expected_restore.read_bytes())
            readback = DumpFile.from_bytes(args.readback.read_bytes())
            analysis = verify_xt_audio_gate_restore(expected, readback, plan)
            json_path, markdown_path = _write_sysex_analysis(
                analysis, args.output_dir, args.stem
            )
            print(
                json.dumps(
                    {
                        "status": analysis.status.value,
                        "verdict": analysis.verdict.value,
                        "exact": analysis.exact,
                        "analysis_sha256": analysis.analysis_sha256,
                        "json_report": str(json_path),
                        "markdown_report": str(markdown_path),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0 if analysis.status is XtAudioGateStatus.PASS else 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
