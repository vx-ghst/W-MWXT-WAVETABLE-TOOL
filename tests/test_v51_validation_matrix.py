from __future__ import annotations

from pathlib import Path
import json

from w_mwxt_wavetable_tool.validation_v51.core import (
    N_MATRIX,
    build_fixed_position_midi,
    build_sweep_midi,
    direct_profile_route_matrix,
    generate_profile_corpus,
    _build_case_analysis,
    _group_mapping,
)


def test_v51_profile_selector_has_nine_explicit_routes(tmp_path: Path) -> None:
    report = direct_profile_route_matrix(Path(__file__).resolve().parents[1], tmp_path / "profiles.json")
    assert report["route_pass_count"] == report["route_total"] == 9
    assert report["override"]["pass"] is True


def test_v51_n_matrix_consolidates_exactly(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    for n in N_MATRIX:
        _, consolidation, _ = _build_case_analysis(repo, _group_mapping(n), f"test-n-{n}")
        assert consolidation.physical_wave_set is not None
        assert consolidation.mapping is not None
        assert consolidation.physical_wave_set.physical_wave_count == n
        assert consolidation.mapping.physical_wave_count == n
        assert len(consolidation.mapping.logical_to_physical) == 61


def test_v51_mapping_styles_cover_every_position() -> None:
    for style in ("uniform", "early", "late", "center", "asymmetric", "reverse"):
        mapping = _group_mapping(8, style)
        assert len(mapping) == 61
        assert set(mapping) == set(range(8))


def test_v51_midi_is_cc71_and_explicit_notes_only() -> None:
    fixed, fixed_manifest = build_fixed_position_midi((0, 10, 20, 30, 40, 50, 60))
    sweep, sweep_manifest = build_sweep_midi()
    for raw, manifest in ((fixed, fixed_manifest), (sweep, sweep_manifest)):
        assert raw.startswith(b"MThd")
        assert manifest["contains_sysex"] is False
        assert manifest["allowed_cc"] == [71]
        assert b"\xF0" not in raw
        assert bytes((0xB0, 70)) not in raw
        assert bytes((0xB0, 103)) not in raw
        assert bytes((0xB0, 123)) not in raw


def test_v51_corpus_is_deterministic_and_complete(tmp_path: Path) -> None:
    first = generate_profile_corpus(tmp_path / "a", duration=0.5)
    second = generate_profile_corpus(tmp_path / "b", duration=0.5)
    assert first["profile_samples"] == 27
    assert first["ambiguity_samples"] == 5
    assert first["total_samples"] == 32
    assert first["corpus_sha256"] == second["corpus_sha256"]
    first_hashes = [item["sha256"] for item in first["entries"]]
    second_hashes = [item["sha256"] for item in second["entries"]]
    assert first_hashes == second_hashes
