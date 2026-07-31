from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from w_mwxt_wavetable_tool.dump import DumpFile

FILENAMES = (
    "WALDORF_MWXT_ALL_SOUNDS.syx",
    "WALDORF_MWXT_ALL_WAVETABLES_AND_WAVES.syx",
    "WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22.syx",
    "WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22_B.syx",
)


def analyze(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    dump = DumpFile.from_bytes(raw)
    length_counts = Counter(len(message.to_bytes()) for message in dump)
    summary = dump.summary(source_bytes=raw)
    summary["filename"] = path.name
    summary["message_length_counts"] = {
        str(length): count for length, count in sorted(length_counts.items())
    }
    return summary


def markdown(report: dict[str, object]) -> str:
    lines = [
        "# W-MWXT-WAVETABLE-TOOL CODE V1 reference validation",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Overall result",
        "",
        f"- Files validated: **{report['file_count']}**",
        f"- Exact round trips: **{report['all_roundtrips_identical']}**",
        f"- Valid checksums and structures: **{report['all_valid']}**",
        f"- Everything backups identical: **{report['everything_backups_identical']}**",
        "",
        "## File details",
        "",
    ]
    for item in report["files"]:
        lines.extend(
            [
                f"### `{item['filename']}`",
                "",
                f"- Size: `{item['bytes']}` bytes",
                f"- SHA-256: `{item['sha256']}`",
                f"- Messages: `{item['message_count']}`",
                f"- Device IDs: `{item['device_ids']}`",
                f"- Types: `{json.dumps(item['type_counts'], sort_keys=True)}`",
                f"- Message lengths: `{json.dumps(item['message_length_counts'], sort_keys=True)}`",
                f"- Strict round trip: `{item['roundtrip_identical']}`",
                f"- Validation issues: `{len(item['validation_issues'])}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Reference hardware identity",
            "",
            "`F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7`",
            "",
            "- Waldorf Microwave XT",
            "- 10 voices, non-expandable mainboard (`03 00`)",
            "- OS `2.33`",
            "- Device ID used by the dumps: `00`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump_dir", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path, required=True)
    parser.add_argument("--markdown", dest="markdown_path", type=Path, required=True)
    args = parser.parse_args()

    files = [analyze(args.dump_dir / name) for name in FILENAMES]
    raw_a = (args.dump_dir / FILENAMES[2]).read_bytes()
    raw_b = (args.dump_dir / FILENAMES[3]).read_bytes()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "all_roundtrips_identical": all(item["roundtrip_identical"] for item in files),
        "all_valid": all(not item["validation_issues"] for item in files),
        "everything_backups_identical": raw_a == raw_b,
        "files": files,
    }
    args.json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    args.markdown_path.write_text(markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
