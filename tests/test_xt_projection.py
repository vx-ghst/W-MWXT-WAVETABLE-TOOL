from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np
import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.xt.projection import (
    SOURCE_SAMPLE_COUNT,
    XT_SAMPLE_MAX,
    XtProjectionWeights,
    load_and_project_code_v6_json,
    project_code_v6_document_xt_native,
    project_reconstructed_wave_set_xt_native,
    project_wave_xt_native,
    reconstruct_xt_native,
)


def _canonical_sha256(payload: dict) -> str:
    from hashlib import sha256

    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


def _representable_source(seed: int = 17) -> tuple[float, ...]:
    stored = tuple(((seed + index * 19) % 255) - 127 for index in range(64))
    return tuple(value / 127.0 for value in reconstruct_xt_native(stored))


def test_reconstruct_xt_native_uses_documented_reverse_negate_and_safe_range() -> None:
    stored = tuple(range(-32, 32))
    reconstructed = reconstruct_xt_native(stored)
    assert reconstructed[:64] == stored
    assert reconstructed[64:] == tuple(-value for value in reversed(stored))
    assert -128 not in reconstructed


def test_exact_representable_wave_projects_with_zero_error() -> None:
    source = _representable_source()
    result = project_wave_xt_native(source)
    assert result.selected_metrics.time_rmse == pytest.approx(0.0, abs=1e-15)
    assert result.selected_metrics.spectral_similarity == pytest.approx(1.0, abs=1e-15)
    assert result.selected_metrics.correlation == pytest.approx(1.0, abs=1e-15)
    assert min(result.stored_samples) >= -127
    assert max(result.stored_samples) <= 127
    assert -128 not in result.stored_samples
    assert len(result.phase_evaluations) == 128


def test_phase_search_recovers_a_rotated_representable_wave() -> None:
    base = np.asarray(_representable_source(33), dtype=np.float64)
    source = np.roll(base, 23)
    result = project_wave_xt_native(tuple(source))
    assert result.selected_metrics.time_rmse == pytest.approx(0.0, abs=1e-15)
    assert result.selected_phase_rotation_samples in range(128)
    assert np.allclose(result.reconstructed_aligned, source, rtol=0.0, atol=1e-15)


def test_pairwise_quantization_is_nearest_safe_int8_optimum() -> None:
    source = np.zeros(128, dtype=np.float64)
    source[0] = 0.5
    source[127] = -0.25
    result = project_wave_xt_native(tuple(source))
    phase = result.selected_phase_rotation_samples
    rotated = np.roll(source, -phase)
    expected = math.floor(abs((rotated[0] - rotated[127]) * 0.5 * 127.0) + 0.5)
    expected = int(math.copysign(expected, (rotated[0] - rotated[127]) * 0.5))
    assert result.stored_samples[0] == expected


def test_projection_is_deterministic() -> None:
    source = tuple(0.7 * math.sin(2.0 * math.pi * index / 128.0) + 0.15 * math.sin(6.0 * math.pi * index / 128.0) for index in range(128))
    first = project_wave_xt_native(source)
    second = project_wave_xt_native(source)
    assert first.to_dict() == second.to_dict()
    assert first.projection_sha256 == second.projection_sha256


def test_projection_rejects_invalid_samples_and_weights() -> None:
    with pytest.raises(AnalysisError, match="exactly 128"):
        project_wave_xt_native((0.0,) * 127)
    bad = [0.0] * 128
    bad[10] = float("nan")
    with pytest.raises(AnalysisError, match="NaN"):
        project_wave_xt_native(bad)
    too_hot = [0.0] * 128
    too_hot[0] = 1.1
    with pytest.raises(AnalysisError, match="implicit clipping"):
        project_wave_xt_native(too_hot)
    with pytest.raises(AnalysisError, match="silent reconstructed"):
        project_wave_xt_native([0.0] * 128)
    with pytest.raises(AnalysisError, match="sum exactly"):
        XtProjectionWeights(time=0.5)


@dataclass
class _FakeWave:
    index: int
    candidate_index: int
    samples: tuple[float, ...]

    @property
    def wave_sha256(self) -> str:
        from hashlib import sha256
        return sha256(np.asarray(self.samples, dtype="<f8").tobytes()).hexdigest()


@dataclass
class _FakeWaveSet:
    waves: tuple[_FakeWave, ...]
    target_sample_count: int = 128
    analysis_sha256: str = "a" * 64


def test_reconstructed_wave_set_integration() -> None:
    source = _FakeWaveSet(
        waves=(
            _FakeWave(0, 11, _representable_source(5)),
            _FakeWave(1, 12, _representable_source(7)),
        )
    )
    result = project_reconstructed_wave_set_xt_native(source)
    assert result.wave_count == 2
    assert result.source_reconstructed_wave_set_sha256 == "a" * 64
    assert result.waves[0].candidate_index == 11
    assert result.waves[1].candidate_index == 12
    assert result.to_dict()["boundaries"]["generates_sysex"] is False


def _document() -> dict:
    samples = list(_representable_source(9))
    wave_content = {
        "index": 0,
        "candidate_index": 3,
        "samples": samples,
    }
    wave = dict(wave_content)
    wave["wave_sha256"] = _canonical_sha256(wave_content)
    set_content = {
        "schema_version": 1,
        "tool_version": "0.6.0",
        "target_sample_count": 128,
        "waves": [wave],
    }
    document = dict(set_content)
    document["analysis_sha256"] = _canonical_sha256(set_content)
    return document


def test_json_document_hashes_are_verified_and_written(tmp_path: Path) -> None:
    document = _document()
    source = tmp_path / "reconstructed.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    result = load_and_project_code_v6_json(source)
    json_path, markdown_path = result.write(tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["analysis_sha256"] == result.analysis_sha256
    assert "SysEx generation: `no`" in markdown_path.read_text(encoding="utf-8")
    corrupted = dict(document)
    corrupted["target_sample_count"] = 64
    source.write_text(json.dumps(corrupted), encoding="utf-8")
    with pytest.raises(AnalysisError, match="mismatch"):
        load_and_project_code_v6_json(source)


def test_full_code_v6_document_link_is_preserved() -> None:
    reconstructed = _document()
    content = {"schema_version": 1, "reconstructed_wave_set": reconstructed}
    document = dict(content)
    document["analysis_sha256"] = _canonical_sha256(content)
    result = project_code_v6_document_xt_native(document)
    assert result.source_code_v6_analysis_sha256 == document["analysis_sha256"]
    assert result.source_reconstructed_wave_set_sha256 == reconstructed["analysis_sha256"]


def test_spectral_score_distinguishes_nonrepresentable_wave() -> None:
    source = tuple(
        0.75 * math.sin(2.0 * math.pi * index / 128.0 + 0.2)
        + 0.2 * math.cos(8.0 * math.pi * index / 128.0 + 0.7)
        for index in range(128)
    )
    result = project_wave_xt_native(source)
    assert result.selected_metrics.objective_score >= 0.0
    assert 0.0 <= result.selected_metrics.spectral_similarity <= 1.0
    assert result.selected_metrics.time_nrmse >= 0.0
    assert result.phase_evaluations[result.selected_phase_rotation_samples].metrics.objective_score == pytest.approx(
        result.selected_metrics.objective_score
    )
