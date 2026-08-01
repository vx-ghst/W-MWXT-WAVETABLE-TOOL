from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .dump import DumpFile
from .xt import (
    XtGateStatus,
    XtReconstructionGatePlan,
    analyze_xt_reconstruction_gate,
    build_xt_reconstruction_gate,
    parse_observation_document,
    verify_xt_reconstruction_gate_restore,
)

PROGRAM_NAME = "W-MWXT-XT-GATE"
DEFAULT_STEM = "CODE_V7_A1_XT_RECONSTRUCTION_GATE"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=(
            "Build and analyze the CODE V7-A.1 Microwave XT documented "
            "64-to-128 reconstruction gate."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser(
        "build",
        help=(
            "Build offset-binary WAVD probes and an exact restore bundle from "
            "a pre-write backup"
        ),
    )
    build_parser.add_argument("baseline", type=Path)
    build_parser.add_argument("--target-wave-start", type=int, default=1247)
    build_parser.add_argument("--seed", type=int, default=0x57A)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--stem", default=DEFAULT_STEM)

    analyze_parser = sub.add_parser(
        "analyze",
        help=(
            "Verify the 64 offset-binary stored samples and optionally "
            "characterize the -128 negation edge"
        ),
    )
    analyze_parser.add_argument("expected_probe", type=Path)
    analyze_parser.add_argument("readback", type=Path)
    analyze_parser.add_argument("manifest", type=Path)
    analyze_parser.add_argument("--observations", type=Path)
    analyze_parser.add_argument("--exact-tolerance", type=float, default=0.0)
    analyze_parser.add_argument("--output-dir", type=Path, required=True)
    analyze_parser.add_argument("--stem", default=DEFAULT_STEM)

    restore_parser = sub.add_parser(
        "verify-restore",
        help="Verify that the exact pre-write User Wave payloads were restored",
    )
    restore_parser.add_argument("expected_restore", type=Path)
    restore_parser.add_argument("readback", type=Path)
    restore_parser.add_argument("manifest", type=Path)
    restore_parser.add_argument("--output-dir", type=Path, required=True)
    restore_parser.add_argument(
        "--stem", default="CODE_V7_A1_XT_RECONSTRUCTION_GATE_RESTORE"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "build":
            baseline = DumpFile.from_bytes(args.baseline.read_bytes())
            build = build_xt_reconstruction_gate(
                baseline,
                target_wave_start=args.target_wave_start,
                seed=args.seed,
            )
            paths = build.write(args.output_dir, stem=args.stem)
            print(
                json.dumps(
                    {
                        "status": (
                            "READY" if build.ready_for_transmission else "BLOCKED"
                        ),
                        "schema_version": build.plan.schema_version,
                        "gate_plan_sha256": build.plan.plan_sha256,
                        "device_id": build.plan.device_id,
                        "target_wave_start": build.plan.target_wave_start,
                        "target_wave_end": (
                            build.plan.target_wave_start
                            + len(build.plan.probes)
                            - 1
                        ),
                        "wire_sample_encoding": "offset_binary_msb_flipped",
                        "documented_reconstruction_law": (
                            "second_half[n] = -first_half[63 - n], n=0..63"
                        ),
                        "safe_optimizer_sample_range": [-127, 127],
                        "probe_package": str(paths.probe_package),
                        "restore_bundle": str(paths.restore_bundle),
                        "manifest_json": str(paths.manifest_json),
                        "manifest_markdown": str(paths.manifest_markdown),
                        "observation_template_json": str(
                            paths.observation_template_json
                        ),
                        "critical_boundary": (
                            "The manual establishes offset-binary coding and the "
                            "reverse-negate 64-to-128 law. WAVD read-back validates "
                            "storage; only the -128 negation edge remains hardware-gated."
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0 if build.ready_for_transmission else 2

        if args.command == "analyze":
            expected = DumpFile.from_bytes(args.expected_probe.read_bytes())
            readback = DumpFile.from_bytes(args.readback.read_bytes())
            plan = XtReconstructionGatePlan.from_json(
                args.manifest.read_text(encoding="utf-8")
            )
            observed_cycles = None
            observation_method = None
            if args.observations is not None:
                observed_cycles, observation_method, plan_sha = (
                    parse_observation_document(
                        args.observations.read_text(encoding="utf-8")
                    )
                )
                if plan_sha is not None and plan_sha != plan.plan_sha256:
                    raise ValueError(
                        "observation document gate_plan_sha256 does not match manifest"
                    )
            result = analyze_xt_reconstruction_gate(
                expected,
                readback,
                plan,
                observed_cycles=observed_cycles,
                observation_method=observation_method,
                exact_tolerance=args.exact_tolerance,
            )
            paths = result.write(args.output_dir, stem=args.stem)
            print(
                json.dumps(
                    {
                        "status": result.analysis.status.value,
                        "verdict": result.analysis.verdict.value,
                        "storage_passed": result.analysis.storage_passed,
                        "observation_complete": (
                            result.analysis.observation_complete
                        ),
                        "negative_full_scale_status": (
                            result.analysis.negative_full_scale_status
                        ),
                        "v7_b_allowed_under_safe_range": (
                            result.analysis.v7_b_allowed_under_safe_range
                        ),
                        "architecture_decision": (
                            result.analysis.architecture_decision
                        ),
                        "analysis_sha256": result.analysis.analysis_sha256,
                        "json_report": str(paths.json_report),
                        "markdown_report": str(paths.markdown_report),
                    },
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0 if result.analysis.status is XtGateStatus.PASS else 2

        if args.command == "verify-restore":
            expected_restore = DumpFile.from_bytes(args.expected_restore.read_bytes())
            readback = DumpFile.from_bytes(args.readback.read_bytes())
            plan = XtReconstructionGatePlan.from_json(
                args.manifest.read_text(encoding="utf-8")
            )
            result = verify_xt_reconstruction_gate_restore(
                expected_restore, readback, plan
            )
            paths = result.write(args.output_dir, stem=args.stem)
            print(
                json.dumps(
                    {
                        "status": result.analysis.status.value,
                        "verdict": result.analysis.verdict.value,
                        "storage_passed": result.analysis.storage_passed,
                        "analysis_sha256": result.analysis.analysis_sha256,
                        "json_report": str(paths.json_report),
                        "markdown_report": str(paths.markdown_report),
                    },
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0 if result.analysis.status is XtGateStatus.PASS else 2
    except Exception as exc:  # CLI boundary: exact actionable failure.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
