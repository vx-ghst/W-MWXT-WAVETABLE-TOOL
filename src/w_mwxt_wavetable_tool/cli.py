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
from .analysis import (
    analyze_audio_source_pitch_periodicity,
    analyze_audio_source_signal,
    analyze_audio_source_spectral,
    analyze_harmonic_perceptual,
    classify_source,
)
from .project import SourceValidationPolicy, open_project, save_project

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


    signal_parser = sub.add_parser(
        "signal-analyze",
        help="Import audio and print deterministic CODE V4 time-domain measurements",
    )
    signal_parser.add_argument("file", type=Path)
    signal_parser.add_argument(
        "--mono-policy",
        choices=[policy.value for policy in MonoPolicy],
        default=MonoPolicy.AUTO.value,
    )
    signal_parser.add_argument(
        "--invalid-sample-policy",
        choices=[policy.value for policy in InvalidSamplePolicy],
        default=InvalidSamplePolicy.REJECT.value,
    )
    signal_parser.add_argument("--frame-size", type=int, default=2048)
    signal_parser.add_argument("--hop-size", type=int, default=512)
    signal_parser.add_argument("--pitch-frame-size", type=int, default=4096)
    signal_parser.add_argument("--pitch-hop-size", type=int, default=1024)
    signal_parser.add_argument("--minimum-frequency", type=float, default=40.0)
    signal_parser.add_argument("--maximum-frequency", type=float, default=2000.0)
    signal_parser.add_argument("--pitch-confidence", type=float, default=0.60)
    signal_parser.add_argument("--reference-a4", type=float, default=440.0)
    signal_parser.add_argument(
        "--phase-discontinuity-degrees", type=float, default=60.0
    )
    signal_parser.add_argument("--stable-pitch-cents", type=float, default=15.0)
    signal_parser.add_argument(
        "--glide-slope-cents-per-second", type=float, default=25.0
    )
    signal_parser.add_argument("--stepped-pitch-cents", type=float, default=100.0)
    signal_parser.add_argument("--noise-lower-quantile", type=float, default=0.20)
    signal_parser.add_argument("--transient-frame-size", type=int, default=1024)
    signal_parser.add_argument("--transient-hop-size", type=int, default=256)
    signal_parser.add_argument("--transient-sensitivity", type=float, default=6.0)
    signal_parser.add_argument("--minimum-onset-strength", type=float, default=1.0)
    signal_parser.add_argument("--change-energy-db", type=float, default=6.0)
    signal_parser.add_argument("--change-spectral-flux", type=float, default=0.35)
    signal_parser.add_argument("--minimum-event-separation-ms", type=float, default=20.0)
    signal_parser.add_argument("--report", type=Path)

    spectral_parser = sub.add_parser(
        "spectral-analyze",
        help="Import audio and print deterministic CODE V5 spectral measurements",
    )
    spectral_parser.add_argument("file", type=Path)
    spectral_parser.add_argument(
        "--mono-policy",
        choices=[policy.value for policy in MonoPolicy],
        default=MonoPolicy.AUTO.value,
    )
    spectral_parser.add_argument(
        "--invalid-sample-policy",
        choices=[policy.value for policy in InvalidSamplePolicy],
        default=InvalidSamplePolicy.REJECT.value,
    )
    spectral_parser.add_argument("--frame-size", type=int, default=4096)
    spectral_parser.add_argument("--hop-size", type=int, default=1024)
    spectral_parser.add_argument("--fft-size", type=int)
    spectral_parser.add_argument("--active-rms-threshold", type=float, default=1.0e-8)
    spectral_parser.add_argument("--low-band-max", type=float, default=250.0)
    spectral_parser.add_argument("--mid-band-max", type=float, default=4000.0)
    spectral_parser.add_argument("--keep-dc", action="store_true")
    spectral_parser.add_argument("--report", type=Path)

    perceptual_parser = sub.add_parser(
        "perceptual-analyze",
        help=(
            "Import audio and print deterministic CODE V5 harmonic and "
            "perceptual measurements"
        ),
    )
    perceptual_parser.add_argument("file", type=Path)
    perceptual_parser.add_argument(
        "--mono-policy",
        choices=[policy.value for policy in MonoPolicy],
        default=MonoPolicy.AUTO.value,
    )
    perceptual_parser.add_argument(
        "--invalid-sample-policy",
        choices=[policy.value for policy in InvalidSamplePolicy],
        default=InvalidSamplePolicy.REJECT.value,
    )
    perceptual_parser.add_argument("--pitch-frame-size", type=int, default=4096)
    perceptual_parser.add_argument("--pitch-hop-size", type=int, default=1024)
    perceptual_parser.add_argument("--minimum-frequency", type=float, default=40.0)
    perceptual_parser.add_argument("--maximum-frequency", type=float, default=2000.0)
    perceptual_parser.add_argument("--pitch-confidence", type=float, default=0.60)
    perceptual_parser.add_argument("--reference-a4", type=float, default=440.0)
    perceptual_parser.add_argument("--spectral-frame-size", type=int, default=4096)
    perceptual_parser.add_argument("--spectral-hop-size", type=int, default=1024)
    perceptual_parser.add_argument("--fft-size", type=int)
    perceptual_parser.add_argument(
        "--active-rms-threshold", type=float, default=1.0e-8
    )
    perceptual_parser.add_argument("--low-band-max", type=float, default=250.0)
    perceptual_parser.add_argument("--mid-band-max", type=float, default=4000.0)
    perceptual_parser.add_argument("--keep-dc", action="store_true")
    perceptual_parser.add_argument("--maximum-harmonics", type=int, default=64)
    perceptual_parser.add_argument(
        "--harmonic-window-cents", type=float, default=35.0
    )
    perceptual_parser.add_argument(
        "--minimum-harmonic-power-ratio", type=float, default=1.0e-6
    )
    perceptual_parser.add_argument("--bark-band-count", type=int, default=24)
    perceptual_parser.add_argument("--report", type=Path)

    classification_parser = sub.add_parser(
        "classify-audio",
        help="Import audio and print deterministic CODE V5 source classification",
    )
    classification_parser.add_argument("file", type=Path)
    classification_parser.add_argument(
        "--mono-policy",
        choices=[policy.value for policy in MonoPolicy],
        default=MonoPolicy.AUTO.value,
    )
    classification_parser.add_argument(
        "--invalid-sample-policy",
        choices=[policy.value for policy in InvalidSamplePolicy],
        default=InvalidSamplePolicy.REJECT.value,
    )
    classification_parser.add_argument("--report", type=Path)


    project_create_parser = sub.add_parser(
        "project-create",
        help="Import audio and save a deterministic minimal project",
    )
    project_create_parser.add_argument("source", type=Path)
    project_create_parser.add_argument("project", type=Path)
    project_create_parser.add_argument("--name")
    project_create_parser.add_argument(
        "--mono-policy",
        choices=[policy.value for policy in MonoPolicy],
        default=MonoPolicy.AUTO.value,
    )
    project_create_parser.add_argument(
        "--invalid-sample-policy",
        choices=[policy.value for policy in InvalidSamplePolicy],
        default=InvalidSamplePolicy.REJECT.value,
    )
    project_create_parser.add_argument("--overwrite", action="store_true")

    project_open_parser = sub.add_parser(
        "project-open",
        help="Open, verify, and report a deterministic minimal project",
    )
    project_open_parser.add_argument("project", type=Path)
    project_open_parser.add_argument(
        "--source-policy",
        choices=[policy.value for policy in SourceValidationPolicy],
        default=SourceValidationPolicy.REQUIRE_UNCHANGED.value,
    )
    project_open_parser.add_argument("--report", type=Path)

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


        if args.command == "signal-analyze":
            source = import_audio(
                args.file,
                mono_policy=args.mono_policy,
                invalid_sample_policy=args.invalid_sample_policy,
            )
            signal_analysis = analyze_audio_source_signal(
                source,
                time_frame_size=args.frame_size,
                time_hop_size=args.hop_size,
                pitch_frame_size=args.pitch_frame_size,
                pitch_hop_size=args.pitch_hop_size,
                minimum_frequency_hz=args.minimum_frequency,
                maximum_frequency_hz=args.maximum_frequency,
                confidence_threshold=args.pitch_confidence,
                reference_a4_hz=args.reference_a4,
                phase_discontinuity_threshold_degrees=(
                    args.phase_discontinuity_degrees
                ),
                stable_pitch_threshold_cents=args.stable_pitch_cents,
                glide_slope_threshold_cents_per_second=(
                    args.glide_slope_cents_per_second
                ),
                stepped_pitch_threshold_cents=args.stepped_pitch_cents,
                noise_lower_quantile=args.noise_lower_quantile,
                transient_frame_size=args.transient_frame_size,
                transient_hop_size=args.transient_hop_size,
                transient_sensitivity=args.transient_sensitivity,
                minimum_onset_strength=args.minimum_onset_strength,
                change_energy_threshold_db=args.change_energy_db,
                change_spectral_flux_threshold=args.change_spectral_flux,
                minimum_event_separation_ms=args.minimum_event_separation_ms,
            )
            rendered = json.dumps(
                {
                    "audio": source.to_summary(),
                    **signal_analysis.to_dict(),
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            print(rendered)
            if args.report is not None:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(rendered + "\n", encoding="utf-8", newline="\n")
            return 0


        if args.command == "spectral-analyze":
            source = import_audio(
                args.file,
                mono_policy=args.mono_policy,
                invalid_sample_policy=args.invalid_sample_policy,
            )
            spectral_analysis = analyze_audio_source_spectral(
                source,
                frame_size=args.frame_size,
                hop_size=args.hop_size,
                fft_size=args.fft_size,
                remove_dc=not args.keep_dc,
                active_rms_threshold=args.active_rms_threshold,
                low_band_max_hz=args.low_band_max,
                mid_band_max_hz=args.mid_band_max,
            )
            rendered = json.dumps(
                {
                    "audio": source.to_summary(),
                    "spectral_analysis": spectral_analysis.to_dict(),
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            print(rendered)
            if args.report is not None:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(rendered + "\n", encoding="utf-8", newline="\n")
            return 0


        if args.command == "perceptual-analyze":
            source = import_audio(
                args.file,
                mono_policy=args.mono_policy,
                invalid_sample_policy=args.invalid_sample_policy,
            )
            pitch_analysis = analyze_audio_source_pitch_periodicity(
                source,
                frame_size=args.pitch_frame_size,
                hop_size=args.pitch_hop_size,
                minimum_frequency_hz=args.minimum_frequency,
                maximum_frequency_hz=args.maximum_frequency,
                confidence_threshold=args.pitch_confidence,
                reference_a4_hz=args.reference_a4,
            )
            spectral_analysis = analyze_audio_source_spectral(
                source,
                frame_size=args.spectral_frame_size,
                hop_size=args.spectral_hop_size,
                fft_size=args.fft_size,
                remove_dc=not args.keep_dc,
                active_rms_threshold=args.active_rms_threshold,
                low_band_max_hz=args.low_band_max,
                mid_band_max_hz=args.mid_band_max,
            )
            harmonic_perceptual_analysis = analyze_harmonic_perceptual(
                spectral_analysis,
                fundamental_frequency_hz=pitch_analysis.frequency_hz,
                maximum_harmonics=args.maximum_harmonics,
                harmonic_window_cents=args.harmonic_window_cents,
                minimum_harmonic_power_ratio=(
                    args.minimum_harmonic_power_ratio
                ),
                bark_band_count=args.bark_band_count,
            )
            rendered = json.dumps(
                {
                    "audio": source.to_summary(),
                    "pitch_periodicity_analysis": pitch_analysis.to_dict(),
                    "spectral_analysis": spectral_analysis.to_dict(),
                    "harmonic_perceptual_analysis": (
                        harmonic_perceptual_analysis.to_dict()
                    ),
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            print(rendered)
            if args.report is not None:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(rendered + "\n", encoding="utf-8", newline="\n")
            return 0


        if args.command == "classify-audio":
            source = import_audio(
                args.file,
                mono_policy=args.mono_policy,
                invalid_sample_policy=args.invalid_sample_policy,
            )
            signal_analysis = analyze_audio_source_signal(source)
            spectral_analysis = analyze_audio_source_spectral(source)
            harmonic_perceptual_analysis = analyze_harmonic_perceptual(
                spectral_analysis,
                fundamental_frequency_hz=(
                    signal_analysis.pitch_periodicity_analysis.frequency_hz
                ),
            )
            source_classification = classify_source(
                signal_analysis,
                spectral_analysis,
                harmonic_perceptual_analysis,
            )
            rendered = json.dumps(
                {
                    "audio": source.to_summary(),
                    "signal_analysis": signal_analysis.to_dict(),
                    "spectral_analysis": spectral_analysis.to_dict(),
                    "harmonic_perceptual_analysis": (
                        harmonic_perceptual_analysis.to_dict()
                    ),
                    "source_classification": source_classification.to_dict(),
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            print(rendered)
            if args.report is not None:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(rendered + "\n", encoding="utf-8", newline="\n")
            return 0


        if args.command == "project-create":
            source = import_audio(
                args.source,
                mono_policy=args.mono_policy,
                invalid_sample_policy=args.invalid_sample_policy,
            )
            result = save_project(
                source,
                args.project,
                project_name=args.name,
                overwrite=args.overwrite,
                tool_version=__version__,
            )
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
            return 0

        if args.command == "project-open":
            project = open_project(
                args.project,
                source_policy=args.source_policy,
            )
            rendered = json.dumps(
                project.to_summary(), indent=2, ensure_ascii=False, sort_keys=True
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
