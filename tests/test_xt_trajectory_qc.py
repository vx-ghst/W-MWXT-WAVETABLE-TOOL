from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.xt.projection import (
    PROJECTION_SCHEMA_VERSION,
    XtProjectionSet,
    XtProjectionWeights,
    project_wave_xt_native,
    reconstruct_xt_native,
)
from w_mwxt_wavetable_tool.xt.trajectory import (
    XtPhasePathPolicy,
    XtTrajectoryConfig,
    build_xt_wavetable_trajectory_document,
)
from w_mwxt_wavetable_tool.xt.trajectory_qc import (
    XtTrajectoryQcConfig,
    XtTrajectoryQcStatus,
    analyze_xt_trajectory_qc_documents,
    load_and_analyze_xt_trajectory_qc,
)


def _stored_pattern(seed: int, scale: float = 1.0) -> tuple[int, ...]:
    values = []
    for index in range(64):
        raw = ((seed + index * 29 + (index * index * 3)) % 255) - 127
        values.append(int(np.clip(round(raw * scale), -127, 127)))
    return tuple(values)


def _projection_document() -> dict:
    stored_sets = tuple(
        _stored_pattern(seed, scale)
        for seed, scale in (
            (3, 0.65),
            (11, 0.62),
            (39, 0.76),
            (91, 0.92),
            (127, 0.78),
            (201, 0.70),
        )
    )
    waves = []
    for index, stored in enumerate(stored_sets):
        source = tuple(value / 127.0 for value in reconstruct_xt_native(stored))
        waves.append(
            project_wave_xt_native(
                source,
                index=index,
                candidate_index=100 + index,
                source_wave_sha256=f"{index + 1:064x}",
            )
        )
    result = XtProjectionSet(
        schema_version=PROJECTION_SCHEMA_VERSION,
        tool_version="0.6.0",
        source_reconstructed_wave_set_sha256="a" * 64,
        source_code_v6_analysis_sha256=None,
        weights=XtProjectionWeights(),
        waves=tuple(waves),
        decision_reason="test projection",
    )
    return result.to_dict()


def _trajectory_document(projection: dict | None = None) -> dict:
    source = _projection_document() if projection is None else projection
    result = build_xt_wavetable_trajectory_document(
        source,
        config=XtTrajectoryConfig(
            target_slot_count=61,
            phase_path_policy=XtPhasePathPolicy.GLOBAL,
            minimum_intermediates_per_transition=1,
        ),
    )
    return result.to_dict()


def _quick_config(**changes: float | int) -> XtTrajectoryQcConfig:
    values: dict[str, float | int] = {
        "jump_absolute_minimum": 1.0,
        "curvature_absolute_minimum": 1.0,
        "sample_rate": 8_000,
        "preview_frequency_hz": 100.0,
        "sweep_duration_seconds": 0.12,
        "stepped_slot_duration_seconds": 0.005,
        "fade_duration_seconds": 0.001,
    }
    values.update(changes)
    return XtTrajectoryQcConfig(**values)


def test_audits_all_61_slots_and_renders_deterministic_previews() -> None:
    projection = _projection_document()
    trajectory = _trajectory_document(projection)
    first = analyze_xt_trajectory_qc_documents(
        trajectory,
        projection_document=projection,
        config=_quick_config(),
    )
    second = analyze_xt_trajectory_qc_documents(
        trajectory,
        projection_document=projection,
        config=_quick_config(),
    )
    analysis = first.analysis
    assert analysis.status is XtTrajectoryQcStatus.PASS
    assert len(analysis.adjacent_pairs) == 60
    assert len(analysis.curvatures) == 59
    assert analysis.baseline_comparison is not None
    assert len(analysis.previews) == 3
    assert analysis.to_dict() == second.analysis.to_dict()
    assert first.preview_payloads == second.preview_payloads
    for name, payload in first.preview_payloads:
        assert name.endswith(".wav")
        assert payload.startswith(b"RIFF")
        assert sha256(payload).hexdigest() in {item.sha256 for item in analysis.previews}
    assert analysis.to_dict()["boundaries"]["generates_sysex"] is False
    assert analysis.to_dict()["boundaries"]["modifies_trajectory_slots"] is False


def test_review_status_is_explicit_when_thresholds_are_exceeded() -> None:
    trajectory = _trajectory_document()
    result = analyze_xt_trajectory_qc_documents(
        trajectory,
        config=_quick_config(
            jump_absolute_minimum=0.0,
            jump_median_multiplier=0.0,
            jump_mad_multiplier=0.0,
            curvature_absolute_minimum=0.0,
            curvature_median_multiplier=0.0,
            curvature_mad_multiplier=0.0,
        ),
    )
    assert result.analysis.status is XtTrajectoryQcStatus.REVIEW
    assert result.analysis.flagged_jump_count > 0
    assert result.analysis.flagged_curvature_count > 0


def test_projection_hash_link_is_enforced() -> None:
    projection = _projection_document()
    trajectory = _trajectory_document(projection)
    other = copy.deepcopy(projection)
    other["decision_reason"] = "different"
    content = dict(other)
    del content["analysis_sha256"]
    encoded = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    other["analysis_sha256"] = sha256(encoded).hexdigest()
    with pytest.raises(AnalysisError, match="does not match"):
        analyze_xt_trajectory_qc_documents(
            trajectory,
            projection_document=other,
            config=_quick_config(),
        )


def test_trajectory_hash_and_xt_invariants_are_enforced() -> None:
    trajectory = _trajectory_document()
    corrupted = copy.deepcopy(trajectory)
    corrupted["slots"][0]["stored_samples"][0] = -128
    with pytest.raises(AnalysisError, match="mismatch"):
        analyze_xt_trajectory_qc_documents(corrupted, config=_quick_config())


def test_write_is_byte_deterministic(tmp_path: Path) -> None:
    projection = _projection_document()
    build = analyze_xt_trajectory_qc_documents(
        _trajectory_document(projection),
        projection_document=projection,
        config=_quick_config(),
    )
    first = build.write(tmp_path / "first")
    second = build.write(tmp_path / "second")
    assert first[0].read_bytes() == second[0].read_bytes()
    assert first[1].read_bytes() == second[1].read_bytes()
    assert [path.read_bytes() for path in first[2]] == [path.read_bytes() for path in second[2]]


def test_loader_reads_canonical_reports(tmp_path: Path) -> None:
    projection = _projection_document()
    trajectory = _trajectory_document(projection)
    trajectory_path = tmp_path / "trajectory.json"
    projection_path = tmp_path / "projection.json"
    trajectory_path.write_text(json.dumps(trajectory), encoding="utf-8")
    projection_path.write_text(json.dumps(projection), encoding="utf-8")
    result = load_and_analyze_xt_trajectory_qc(
        trajectory_path,
        projection_path=projection_path,
        config=_quick_config(),
    )
    assert result.analysis.source_trajectory_sha256 == trajectory["analysis_sha256"]
    assert result.analysis.source_projection_set_sha256 == projection["analysis_sha256"]
