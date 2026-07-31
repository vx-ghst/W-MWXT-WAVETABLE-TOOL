from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .dump import DumpFile
from .hardware_test import build_hardware_test_from_backup
from .hardware_validation import (
    HardwareValidationStatus,
    compare_hardware_readback,
    prepare_hardware_validation,
)
from .identity import IdentityReply
from .audio import InvalidSamplePolicy, MonoPolicy, import_audio

PROGRAM_NAME = "W-MWXT-WAVETABLE-TOOL"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="Inspect, validate, and verify Waldorf Microwave XT SysEx data.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Print a JSON summary of a dump")
    inspect_parser.add_argument("file", type=Path)

    validate_parser = sub.add_parser(
        "validate", help="Validate framing, protocol fields, lengths, and checksums"
    )
    validate_parser.add_argument("files", nargs="+", type=Path)

    roundtrip_parser = sub.add_parser(
        "roundtrip",
        help="Decode, re-encode, and compare a dump byte for byte",
    )
    roundtrip_parser.add_argument("file", type=Path)
    roundtrip_parser.add_argument("--output", type=Path)

    identity_parser = sub.add_parser(
        "identity", help="Decode a Waldorf Universal Device Identity reply"
    )
    identity_parser.add_argument(
        "hex_bytes",
        help="Example: 'F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7'",
    )

    audio_parser = sub.add_parser(
        "audio-inspect",
        help="Import WAV, AIFF, or FLAC and print a deterministic mono JSON report",
    )
    audio_parser.add_argument("file", type=Path)
    audio_parser.add_argument(
        "--mono-policy",
        choices=[policy.value for policy in MonoPolicy],
        default=MonoPolicy.AUTO.value,
    )
    audio_parser.add_argument(
        "--invalid-sample-policy",
        choices=[policy.value for policy in InvalidSamplePolicy],
        default=InvalidSamplePolicy.REJECT.value,
    )
    audio_parser.add_argument("--report", type=Path)


    build_test_parser = sub.add_parser(
        "hardware-build-test",
        help=(
            "Build and preflight a 61-WAVD manual hardware test package from a backup"
        ),
    )
    build_test_parser.add_argument("baseline", type=Path)
    build_test_parser.add_argument("--source-wave-start", type=int, required=True)
    build_test_parser.add_argument("--source-wavetable", type=int, required=True)
    build_test_parser.add_argument("--source-sound", required=True)
    build_test_parser.add_argument("--target-wave-start", type=int, required=True)
    build_test_parser.add_argument("--target-wavetable", type=int, required=True)
    build_test_parser.add_argument("--target-sound", required=True)
    build_test_parser.add_argument("--sound-name", default="V2C READBACK")
    build_test_parser.add_argument(
        "--stem", default="CODE_V2_C_HARDWARE_TEST"
    )
    build_test_parser.add_argument("--output-dir", type=Path, required=True)

    preflight_parser = sub.add_parser(
        "hardware-preflight",
        help=(
            "Validate a manual-write package against a pre-write backup and "
            "create an exact restore bundle"
        ),
    )
    preflight_parser.add_argument("package", type=Path)
    preflight_parser.add_argument("baseline", type=Path)
    preflight_parser.add_argument("--output-dir", type=Path, required=True)
    preflight_parser.add_argument(
        "--stem", default="CODE_V2_C_HARDWARE_TEST"
    )
    preflight_parser.add_argument(
        "--allow-non-acceptance-shape",
        action="store_true",
        help="Allow a package with a User Wave count other than 61",
    )

    compare_parser = sub.add_parser(
        "hardware-compare",
        help=(
            "Compare an expected package or restore bundle against a read-back dump"
        ),
    )
    compare_parser.add_argument("expected", type=Path)
    compare_parser.add_argument("readback", type=Path)
    compare_parser.add_argument("--output-dir", type=Path, required=True)
    compare_parser.add_argument("--stem", default="CODE_V2_C_READBACK")
    compare_parser.add_argument(
        "--allow-non-acceptance-shape",
        action="store_true",
        help="Allow an expected package with a User Wave count other than 61",
    )
    compare_parser.add_argument(
        "--restore-bundle",
        action="store_true",
        help=(
            "Compare a restore bundle whose Sound and Wavetable may not reference "
            "the other messages in the bundle"
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            raw = args.file.read_bytes()
            dump = DumpFile.from_bytes(raw)
            print(json.dumps(dump.summary(source_bytes=raw), indent=2, ensure_ascii=False))
            return 0

        if args.command == "validate":
            failed = False
            for path in args.files:
                try:
                    raw = path.read_bytes()
                    dump = DumpFile.from_bytes(raw)
                    issues = dump.validate()
                    if issues:
                        failed = True
                        print(f"FAIL {path}: {len(issues)} issue(s)")
                        for issue in issues:
                            print(f"  - {issue}")
                    else:
                        print(f"OK   {path}: {len(dump)} messages, {len(raw)} bytes")
                except Exception as exc:  # CLI boundary: show the exact failure.
                    failed = True
                    print(f"FAIL {path}: {exc}")
            return 1 if failed else 0

        if args.command == "roundtrip":
            raw = args.file.read_bytes()
            dump = DumpFile.from_bytes(raw)
            encoded = dump.to_bytes()
            identical = encoded == raw
            if args.output is not None:
                args.output.write_bytes(encoded)
            print("IDENTICAL" if identical else "DIFFERENT")
            print(f"messages={len(dump)} bytes={len(raw)}")
            return 0 if identical else 2

        if args.command == "identity":
            raw = bytes.fromhex(args.hex_bytes)
            identity = IdentityReply.from_bytes(raw)
            print(
                json.dumps(
                    {
                        "manufacturer_id": f"0x{identity.manufacturer_id:02X}",
                        "family_code": f"0x{identity.family_code:04X}",
                        "member_code": f"0x{identity.member_code:04X}",
                        "version": identity.version,
                        "xt_10_voice_non_expandable": (
                            identity.is_xt_10_voice_non_expandable
                        ),
                    },
                    indent=2,
                )
            )
            return 0

        if args.command == "audio-inspect":
            source = import_audio(
                args.file,
                mono_policy=args.mono_policy,
                invalid_sample_policy=args.invalid_sample_policy,
            )
            rendered = json.dumps(
                source.to_summary(), indent=2, ensure_ascii=False, sort_keys=True
            )
            print(rendered)
            if args.report is not None:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(rendered + "\n", encoding="utf-8", newline="\n")
            return 0


        if args.command == "hardware-build-test":
            baseline = DumpFile.from_bytes(args.baseline.read_bytes())
            build = build_hardware_test_from_backup(
                baseline,
                source_wave_start=args.source_wave_start,
                source_wavetable_display=args.source_wavetable,
                source_sound=args.source_sound,
                target_wave_start=args.target_wave_start,
                target_wavetable_display=args.target_wavetable,
                target_sound=args.target_sound,
                sound_name=args.sound_name,
                package_name=args.stem,
            )
            paths = build.write(args.output_dir, stem=args.stem)
            print(
                json.dumps(
                    {
                        "status": (
                            "READY" if build.ready_for_transmission else "BLOCKED"
                        ),
                        "message_count": len(build.package_result.dump.messages),
                        "user_wave_range": (
                            build.preparation.report.profile.wave_range
                        ),
                        "wavetable_display_number": (
                            build.preparation.report.profile.wavetable_display_number
                        ),
                        "sound_destination": (
                            build.preparation.report.profile.sound_location
                        ),
                        "package": str(paths.package.sysex),
                        "package_manifest_json": str(paths.package.json_manifest),
                        "package_manifest_markdown": str(
                            paths.package.markdown_manifest
                        ),
                        "restore_bundle": str(
                            paths.preflight.restore_bundle
                        ),
                        "preflight_json": str(paths.preflight.json_report),
                        "preflight_markdown": str(
                            paths.preflight.markdown_report
                        ),
                        "unchanged_payload_targets": list(
                            build.preparation.report.unchanged_payload_targets
                        ),
                        "adjustments": list(build.adjustments),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0 if build.ready_for_transmission else 2

        if args.command == "hardware-preflight":
            required_wave_count = (
                None if args.allow_non_acceptance_shape else 61
            )
            package = DumpFile.from_bytes(args.package.read_bytes())
            baseline = DumpFile.from_bytes(args.baseline.read_bytes())
            preparation = prepare_hardware_validation(
                package,
                baseline,
                required_wave_count=required_wave_count,
            )
            paths = preparation.write(args.output_dir, stem=args.stem)
            print(
                json.dumps(
                    {
                        "status": (
                            "READY"
                            if preparation.report.ready_for_transmission
                            else "BLOCKED"
                        ),
                        "message_count": preparation.report.profile.message_count,
                        "user_wave_range": preparation.report.profile.wave_range,
                        "wavetable_display_number": (
                            preparation.report.profile.wavetable_display_number
                        ),
                        "sound_destination": (
                            preparation.report.profile.sound_location
                        ),
                        "restore_bundle": str(paths.restore_bundle),
                        "json_report": str(paths.json_report),
                        "markdown_report": str(paths.markdown_report),
                        "unchanged_payload_targets": list(
                            preparation.report.unchanged_payload_targets
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0 if preparation.report.ready_for_transmission else 2

        if args.command == "hardware-compare":
            required_wave_count = (
                None if args.allow_non_acceptance_shape else 61
            )
            expected = DumpFile.from_bytes(args.expected.read_bytes())
            readback = DumpFile.from_bytes(args.readback.read_bytes())
            result = compare_hardware_readback(
                expected,
                readback,
                required_wave_count=required_wave_count,
                require_package_links=not args.restore_bundle,
            )
            paths = result.write(args.output_dir, stem=args.stem)
            print(
                json.dumps(
                    {
                        "status": result.report.status.value,
                        "exact_count": result.report.exact_count,
                        "message_count": result.report.profile.message_count,
                        "status_counts": result.report.status_counts,
                        "json_report": str(paths.json_report),
                        "markdown_report": str(paths.markdown_report),
                        "extracted_targets": str(paths.extracted_targets),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return (
                0
                if result.report.status is HardwareValidationStatus.PASS_EXACT
                else 2
            )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
