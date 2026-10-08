from __future__ import annotations

import os
from pathlib import Path

import pytest

from w_mwxt_wavetable_tool import (
    DumpFile,
    InventoryDumpSource,
    InventorySourceKind,
    InventoryState,
    analyze_xt_memory_inventory,
)


def _candidate_everything_dump(directory: Path) -> tuple[Path, DumpFile] | None:
    for path in sorted(directory.glob("*.syx")):
        try:
            dump = DumpFile.from_path(path)
        except Exception:
            continue
        counts = dump.type_counts
        if counts.get("USER_WAVE") == 250 and counts.get("USER_WAVETABLE") == 32:
            return path, dump
    return None


def test_private_everything_dump_proves_coverage_but_not_safe_free_signature() -> None:
    root_value = os.environ.get("W_MWXT_DUMP_DIR")
    if not root_value:
        pytest.skip("Private dump directory is not mounted.")
    candidate = _candidate_everything_dump(Path(root_value))
    if candidate is None:
        pytest.skip("No private dump containing 250 User Waves and 32 User Wavetables was found.")
    path, dump = candidate
    inventory = analyze_xt_memory_inventory(
        (
            InventoryDumpSource(
                source_id=f"private-{path.stem}",
                source_kind=InventorySourceKind.BACKUP_EVERYTHING,
                dump=dump,
                captured_current_state=True,
            ),
        )
    )
    assert inventory.evidence_status.user_wave_coverage_complete is True
    assert inventory.evidence_status.user_wavetable_coverage_complete is True
    assert inventory.evidence_status.safe_free_enabled is False
    assert inventory.state_counts[InventoryState.SAFE_FREE.value] == 0
    assert inventory.state_counts[InventoryState.UNKNOWN.value] == 0
