from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from w_mwxt_wavetable_tool.constants import (
    PATCH_WAVETABLE_OFFSET,
    DumpType,
)
from w_mwxt_wavetable_tool.dump import DumpFile
from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.models import SoundProgram, UserWave, UserWavetable
from w_mwxt_wavetable_tool.xt.hardware_package import (
    XtHardwarePackageStatus,
    build_xt_hardware_package_documents,
)


def _hash_document(document: dict[str, object]) -> dict[str, object]:
    rendered = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    document["analysis_sha256"] = sha256(rendered).hexdigest()
    return document


def _slot_samples(index: int) -> tuple[int, ...]:
    return tuple(((sample * 3 + index * 5) % 201) - 100 for sample in range(64))


def _trajectory_document() -> dict[str, object]:
    slots = []
    for index in range(61):
        stored = _slot_samples(index)
        reconstructed = stored + tuple(-value for value in reversed(stored))
        slots.append(
            {
                "slot_number": index + 1,
                "kind": "anchor" if index in {0, 60} else "interpolated",
                "stored_samples": list(stored),
                "reconstructed_samples": list(reconstructed),
            }
        )
    return _hash_document(
        {
            "schema_version": 1,
            "slot_count": 61,
            "anchor_count": 2,
            "duplicate_adjacent_slot_pairs": [],
            "source_projection_set_sha256": "a" * 64,
            "boundaries": {"generates_sysex": False},
            "slots": slots,
        }
    )


def _qc_document(trajectory: dict[str, object]) -> dict[str, object]:
    return _hash_document(
        {
            "schema_version": 1,
            "status": "pass",
            "source_trajectory_sha256": trajectory["analysis_sha256"],
            "source_projection_set_sha256": "a" * 64,
            "flagged_jump_count": 0,
            "flagged_curvature_count": 0,
            "boundaries": {
                "modifies_trajectory_slots": False,
                "generates_sysex": False,
            },
        }
    )


def _baseline(*, matching_first_wave: bool = False) -> tuple[DumpFile, str]:
    messages = []
    for offset, number in enumerate(range(1189, 1250)):
        stored = _slot_samples(0) if matching_first_wave and offset == 0 else (-1,) * 64
        messages.append(UserWave(0, number, stored).to_message())
    messages.append(
        UserWavetable(
            device_id=0,
            internal_number=127,
            references=tuple(range(1000, 1061)) + (0x0101, 0x0202, 0x0303),
        ).to_message()
    )
    sound_data = bytearray(256)
    sound_data[240:256] = b"BASELINE        "
    messages.append(SoundProgram(0, 1, 127, bytes(sound_data)).to_message())
    dump = DumpFile(tuple(messages))
    return dump, sha256(dump.to_bytes()).hexdigest()


def _build(*, matching_first_wave: bool = False):
    trajectory = _trajectory_document()
    qc = _qc_document(trajectory)
    baseline, baseline_hash = _baseline(matching_first_wave=matching_first_wave)
    return build_xt_hardware_package_documents(
        trajectory,
        qc,
        baseline,
        baseline_sha256=baseline_hash,
        user_wave_start=1189,
        wavetable_display_number=128,
        sound_destination="B128",
        sound_name="ODIUM KEY V7E",
    )


def test_builds_complete_ordered_package_and_restore() -> None:
    build = _build()
    assert build.analysis.status is XtHardwarePackageStatus.PASS
    assert build.analysis.ready_for_v7_f is True
    assert len(build.package_dump.messages) == 63
    assert len(build.user_waves_dump.messages) == 61
    assert [int(message.dump_type) for message in build.package_dump.messages[:61]] == [
        int(DumpType.USER_WAVE)
    ] * 61
    assert int(build.package_dump.messages[61].dump_type) == int(DumpType.USER_WAVETABLE)
    assert int(build.package_dump.messages[62].dump_type) == int(DumpType.SOUND)
    assert len(build.restore_dump.messages) == 63


def test_wavetable_references_61_targets_and_preserves_tail() -> None:
    build = _build()
    table = UserWavetable.from_message(build.package_dump.messages[61])
    assert table.references[:61] == tuple(range(1189, 1250))
    assert table.references[61:] == (0x0101, 0x0202, 0x0303)


def test_sound_uses_selected_wavetable_and_name() -> None:
    build = _build()
    sound = SoundProgram.from_message(build.package_dump.messages[62])
    assert sound.data[PATCH_WAVETABLE_OFFSET] == 127
    assert sound.data[6] == 48
    assert sound.data[47] == 96
    assert sound.data[48] == 0
    assert sound.data[62] == 127
    assert sound.data[77] == 100
    assert sound.data[108:111] == bytes((0, 0, 64))
    assert sound.name == "ODIUM KEY V7E"
    assert build.analysis.sound_parameter_changes


def test_review_when_generated_payload_already_matches_baseline() -> None:
    build = _build(matching_first_wave=True)
    assert build.analysis.status is XtHardwarePackageStatus.REVIEW
    assert build.analysis.ready_for_v7_f is False
    assert "User Wave 1189" in build.analysis.unchanged_targets


def test_rejects_qc_not_linked_to_trajectory() -> None:
    trajectory = _trajectory_document()
    qc = _qc_document(trajectory)
    qc["source_trajectory_sha256"] = "b" * 64
    del qc["analysis_sha256"]
    _hash_document(qc)
    baseline, baseline_hash = _baseline()
    with pytest.raises(AnalysisError, match="does not match"):
        build_xt_hardware_package_documents(
            trajectory,
            qc,
            baseline,
            baseline_sha256=baseline_hash,
            user_wave_start=1189,
            wavetable_display_number=128,
            sound_destination="B128",
            sound_name="ODIUM KEY V7E",
        )


def test_rejects_forbidden_negative_128() -> None:
    trajectory = _trajectory_document()
    trajectory["slots"][0]["stored_samples"][0] = -128  # type: ignore[index]
    del trajectory["analysis_sha256"]
    _hash_document(trajectory)
    qc = _qc_document(trajectory)
    baseline, baseline_hash = _baseline()
    with pytest.raises(AnalysisError, match="safe range"):
        build_xt_hardware_package_documents(
            trajectory,
            qc,
            baseline,
            baseline_sha256=baseline_hash,
            user_wave_start=1189,
            wavetable_display_number=128,
            sound_destination="B128",
            sound_name="ODIUM KEY V7E",
        )


def test_writes_deterministic_artifacts(tmp_path: Path) -> None:
    first = _build()
    second = _build()
    first_paths = first.write(tmp_path / "first")
    second_paths = second.write(tmp_path / "second")
    for field in first_paths.__dataclass_fields__:
        first_payload = getattr(first_paths, field).read_bytes()
        second_payload = getattr(second_paths, field).read_bytes()
        assert first_payload == second_payload
