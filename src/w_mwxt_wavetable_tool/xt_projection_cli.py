from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .errors import AnalysisError
from .xt.projection import (
    DEFAULT_STEM,
    XtProjectionWeights,
    load_and_project_code_v6_json,
)

PROGRAM_NAME = "W-MWXT-XT-PROJECT"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=(
            "Project CODE V6 reconstructed 128-point waves into the Microwave XT "
            "64-point reverse-negate domain without generating SysEx."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    project = sub.add_parser("project", help="Project a CODE V6 or reconstructed-wave-set JSON document")
    project.add_argument("input", type=Path)
    project.add_argument("--output-dir", type=Path, required=True)
    project.add_argument("--stem", default=DEFAULT_STEM)
    project.add_argument("--time-weight", type=float, default=0.45)
    project.add_argument("--spectral-weight", type=float, default=0.25)
    project.add_argument("--seam-weight", type=float, default=0.10)
    project.add_argument("--h1-weight", type=float, default=0.06)
    project.add_argument("--h2-weight", type=float, default=0.05)
    project.add_argument("--h3-weight", type=float, default=0.04)
    project.add_argument("--bands-weight", type=float, default=0.05)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        weights = XtProjectionWeights(
            time=args.time_weight,
            spectral=args.spectral_weight,
            seam=args.seam_weight,
            h1=args.h1_weight,
            h2=args.h2_weight,
            h3=args.h3_weight,
            bands=args.bands_weight,
        )
        result = load_and_project_code_v6_json(args.input, weights=weights)
        json_path, markdown_path = result.write(args.output_dir, stem=args.stem)
        summary = {
            "status": "pass",
            "analysis_sha256": result.analysis_sha256,
            "source_reconstructed_wave_set_sha256": result.source_reconstructed_wave_set_sha256,
            "wave_count": result.wave_count,
            "quantization_range": [-127, 127],
            "phase_search_count_per_wave": 128,
            "objective_summary": result.objective_summary,
            "time_nrmse_summary": result.time_nrmse_summary,
            "spectral_similarity_summary": result.spectral_similarity_summary,
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
