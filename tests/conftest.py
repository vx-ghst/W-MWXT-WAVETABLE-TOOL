from __future__ import annotations

import os
from pathlib import Path

import pytest


REFERENCE_FILENAMES = (
    "WALDORF_MWXT_ALL_SOUNDS.syx",
    "WALDORF_MWXT_ALL_WAVETABLES_AND_WAVES.syx",
    "WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22.syx",
    "WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22_B.syx",
)


def reference_dump_dir() -> Path:
    configured = os.environ.get("W_MWXT_DUMP_DIR")
    if configured:
        return Path(configured)
    container_default = Path("/mnt/data")
    if container_default.exists():
        return container_default
    return Path(__file__).resolve().parents[1] / "reference_dumps"


@pytest.fixture(scope="session")
def dump_paths() -> dict[str, Path]:
    base = reference_dump_dir()
    paths = {name: base / name for name in REFERENCE_FILENAMES}
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        pytest.skip(
            "Reference dumps unavailable. Set W_MWXT_DUMP_DIR to their directory. Missing: "
            + ", ".join(missing)
        )
    return paths
