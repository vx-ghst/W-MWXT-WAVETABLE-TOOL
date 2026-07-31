from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .dump import DumpFile
from .identity import IdentityReply

PROGRAM_NAME = "W-MWXT-WAVETABLE-TOOL"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="Inspect and validate Waldorf Microwave XT SysEx data.",
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
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
