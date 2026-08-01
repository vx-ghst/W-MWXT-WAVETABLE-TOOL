from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import (
    CycleSelectionDecision,
    ReconstructionDecision,
    ReconstructionStrategy,
    ReconstructedWave,
    reconstruct_selected_cycles,
)


def _sample_hash(samples: np.ndarray) -> str:
    return sha256(samples.astype("<f8", copy=False).tobytes(order="C")).hexdigest()


def _digest(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _chain(
    *,
    selected_count: int = 1,
    decision: CycleSelectionDecision = CycleSelectionDecision.SELECTED,
    metrics: tuple[float, float, float, float] = (0.95, 0.90, 0.85, 0.95),
):
    sample_rate = 48000
    cycle_length = 64
    total_cycles = max(8, selected_count + 2)
    phase = np.arange(cycle_length, dtype=np.float64) / cycle_length
    base = 0.65 * np.sin(2.0 * np.pi * phase) + 0.20 * np.sin(4.0 * np.pi * phase)
    samples = np.tile(base, total_cycles).astype(np.float64)
    candidates = []
    entries = []
    periodicity, seam, energy, spectral = metrics
    for index in range(selected_count):
        start = index * cycle_length
        end = start + cycle_length
        candidate_hash = _digest(f"candidate-{index}")
        ranking_hash = _digest(f"ranking-{index}")
        candidates.append(
            SimpleNamespace(
                index=index,
                segment_index=index % 2,
                start_sample=start,
                end_sample=end,
                candidate_sha256=candidate_hash,
                periodicity_score=periodicity,
                seam_score=seam,
                energy_consistency_score=energy,
                spectral_consistency_score=spectral,
            )
        )
        entries.append(
            SimpleNamespace(
                selected=decision is CycleSelectionDecision.SELECTED,
                candidate_index=index,
                candidate_sha256=candidate_hash,
                ranking_sha256=ranking_hash,
            )
        )
    sample_sha = _sample_hash(samples)
    cycles = SimpleNamespace(
        sample_rate=sample_rate,
        sample_count=int(samples.size),
        sample_sha256=sample_sha,
        candidates=tuple(candidates),
        analysis_sha256=_digest("cycles"),
    )
    selected = SimpleNamespace(
        sample_sha256=sample_sha,
        cycle_discovery_analysis_sha256=cycles.analysis_sha256,
        ranked_candidates=tuple(entries),
        decision=decision,
        analysis_sha256=_digest("selected"),
    )
    return samples, cycles, selected


@pytest.mark.parametrize(
    ("strategy", "target_count"),
    [
        (strategy, target_count)
        for strategy in ReconstructionStrategy
        for target_count in (64, 128, 256)
    ],
)
def test_reconstruct_strategy_and_target(strategy, target_count):
    samples, cycles, selected = _chain()
    result = reconstruct_selected_cycles(
        samples,
        cycles,
        selected,
        strategy=strategy,
        target_sample_count=target_count,
    )
    assert result.decision is ReconstructionDecision.RECONSTRUCTED
    assert result.wave_count == 1
    assert len(result.waves[0].samples) == target_count
    assert result.waves[0].peak_amplitude <= 0.98 + 1.0e-12
    assert result.waves[0].strategy is not ReconstructionStrategy.AUTO


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ((0.95, 0.90, 0.85, 0.95), ReconstructionStrategy.SPECTRAL),
        ((0.80, 0.81, 0.60, 0.91), ReconstructionStrategy.SPECTRAL),
        ((0.95, 0.70, 0.85, 0.70), ReconstructionStrategy.PARTIAL),
        ((0.91, 0.79, 0.80, 0.89), ReconstructionStrategy.PARTIAL),
        ((0.89, 0.70, 0.90, 0.70), ReconstructionStrategy.HYBRID),
        ((0.95, 0.70, 0.79, 0.89), ReconstructionStrategy.HYBRID),
    ],
)
def test_auto_strategy_rules(metrics, expected):
    samples, cycles, selected = _chain(metrics=metrics)
    result = reconstruct_selected_cycles(samples, cycles, selected, strategy="auto")
    assert result.waves[0].strategy is expected


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"target_sample_count": 8}, "target_sample_count"),
        ({"target_sample_count": 4097}, "target_sample_count"),
        ({"maximum_partials": 0}, "maximum_partials"),
        ({"hybrid_time_weight": -0.1}, "hybrid_time_weight"),
        ({"hybrid_time_weight": 1.1}, "hybrid_time_weight"),
        ({"normalization_peak": 0.0}, "normalization_peak"),
        ({"normalization_peak": 1.1}, "normalization_peak"),
        ({"strategy": "unsupported"}, "unsupported"),
    ],
)
def test_parameter_validation(kwargs, message):
    samples, cycles, selected = _chain()
    with pytest.raises((ValueError, TypeError), match=message):
        reconstruct_selected_cycles(samples, cycles, selected, **kwargs)


@pytest.mark.parametrize("case", ["cycle-sample", "selected-sample", "cycle-link", "candidate-link"])
def test_link_validation(case):
    samples, cycles, selected = _chain()
    if case == "cycle-sample":
        cycles.sample_sha256 = _digest("wrong-cycle-sample")
    elif case == "selected-sample":
        selected.sample_sha256 = _digest("wrong-selected-sample")
    elif case == "cycle-link":
        selected.cycle_discovery_analysis_sha256 = _digest("wrong-cycle-link")
    else:
        selected.ranked_candidates[0].candidate_sha256 = _digest("wrong-candidate")
    with pytest.raises(ValueError):
        reconstruct_selected_cycles(samples, cycles, selected)


@pytest.mark.parametrize(
    "strategy",
    [
        ReconstructionStrategy.AUTO,
        ReconstructionStrategy.SPECTRAL,
        ReconstructionStrategy.PARTIAL,
        ReconstructionStrategy.HYBRID,
    ],
)
def test_output_is_deterministic(strategy):
    samples, cycles, selected = _chain(selected_count=2)
    first = reconstruct_selected_cycles(samples, cycles, selected, strategy=strategy)
    second = reconstruct_selected_cycles(samples, cycles, selected, strategy=strategy)
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.to_dict() == second.to_dict()


def test_to_dict_hash_is_canonical():
    samples, cycles, selected = _chain()
    result = reconstruct_selected_cycles(samples, cycles, selected)
    payload = result.to_dict()
    declared = payload.pop("analysis_sha256")
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert sha256(rendered).hexdigest() == declared


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("index", -1),
        ("strategy", ReconstructionStrategy.AUTO),
        ("target_sample_count", 8),
        ("maximum_partials", 0),
        ("retained_harmonic_bin_count", 999),
        ("hybrid_time_weight", 2.0),
        ("normalization_peak", 1.1),
        ("samples", (0.0,)),
    ],
)
def test_wave_dataclass_rejects_invalid(field, value):
    samples, cycles, selected = _chain()
    wave = reconstruct_selected_cycles(samples, cycles, selected).waves[0]
    with pytest.raises(ValueError):
        replace(wave, **{field: value})


@pytest.mark.parametrize(
    "strategy",
    [ReconstructionStrategy.AUTO, ReconstructionStrategy.HYBRID],
)
def test_no_selected_cycles_contract(strategy):
    samples, cycles, selected = _chain(
        selected_count=0,
        decision=CycleSelectionDecision.NO_ACCEPTED_CANDIDATES,
    )
    result = reconstruct_selected_cycles(samples, cycles, selected, strategy=strategy)
    assert result.decision is ReconstructionDecision.NO_SELECTED_CYCLES
    assert result.wave_count == 0
    assert result.selected_candidate_indices == ()


@pytest.mark.parametrize("selected_count", [1, 2, 3])
def test_multiple_selected_cycles(selected_count):
    samples, cycles, selected = _chain(selected_count=selected_count)
    result = reconstruct_selected_cycles(samples, cycles, selected)
    assert result.wave_count == selected_count
    assert result.selected_candidate_indices == tuple(range(selected_count))
    assert len(set(result.wave_sha256)) == selected_count
