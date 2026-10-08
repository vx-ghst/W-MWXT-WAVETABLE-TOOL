from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.analysis.regions import (
    RegionKind,
    allocate_region_slots,
    analyze_region_interest,
)


HASH = "a" * 64
SIGNAL_HASH = "b" * 64
EXTENSION_HASH = "c" * 64
SEGMENTATION_HASH = "d" * 64


def kind(value: str):
    return SimpleNamespace(value=value)


def segment(
    index: int,
    start: int,
    end: int,
    value: str,
    *,
    rms: float = 0.2,
    voiced: float = 0.9,
    flux: float = 0.01,
    onset: float = 0.0,
    transients: int = 0,
    changes: int = 0,
):
    return SimpleNamespace(
        index=index,
        start_sample=start,
        end_sample=end,
        duration_seconds=(end - start) / 1000.0,
        kind=kind(value),
        mean_rms=rms,
        active_frame_ratio=0.0 if value == "silence" else 1.0,
        voiced_frame_ratio=voiced,
        mean_spectral_flux=flux,
        maximum_onset_strength=onset,
        transient_count=transients,
        change_point_count=changes,
    )


def make_inputs(*, saturation_score: float = 0.0, noisy: bool = False):
    segments = (
        segment(0, 0, 100, "silence", rms=0.0, voiced=0.0),
        segment(1, 100, 200, "attack", onset=5.0, transients=1),
        segment(2, 200, 400, "transition", flux=0.15, changes=1),
        segment(3, 400, 1400, "steady", flux=0.005),
        segment(4, 1400, 1550, "transition", flux=0.40, changes=2),
        segment(5, 1550, 1700, "release", rms=0.05, voiced=0.2),
    )
    signal = SimpleNamespace(
        sample_rate=1000,
        sample_count=1700,
        sample_sha256=HASH,
        analysis_sha256=SIGNAL_HASH,
        noise_analysis=SimpleNamespace(
            signal_rms=0.20,
            noise_floor_rms=0.18 if noisy else 0.001,
        ),
    )
    saturation_frames = tuple(
        SimpleNamespace(
            start_sample=start,
            sample_count=100,
            saturation_score=saturation_score,
        )
        for start in range(0, 1700, 100)
    )
    extension = SimpleNamespace(
        sample_rate=1000,
        sample_count=1700,
        sample_sha256=HASH,
        signal_analysis_sha256=SIGNAL_HASH,
        analysis_sha256=EXTENSION_HASH,
        saturation_analysis=SimpleNamespace(frames=saturation_frames),
        complexity_analysis=SimpleNamespace(
            complexity_score=0.90 if noisy else 0.20
        ),
    )
    segmentation = SimpleNamespace(
        sample_rate=1000,
        sample_count=1700,
        sample_sha256=HASH,
        signal_analysis_sha256=SIGNAL_HASH,
        analysis_sha256=SEGMENTATION_HASH,
        segments=segments,
    )
    return signal, extension, segmentation


def test_regions_cover_source_and_close_named_region_contracts() -> None:
    result = analyze_region_interest(*make_inputs())
    assert result.regions[0].start_sample == 0
    assert result.regions[-1].end_sample == 1700
    assert all(a.end_sample == b.start_sample for a, b in zip(result.regions, result.regions[1:]))
    kinds = {region.kind for region in result.regions}
    assert RegionKind.SILENCE in kinds
    assert RegionKind.ATTACK in kinds
    assert RegionKind.ESTABLISHMENT in kinds
    assert RegionKind.SUSTAIN in kinds
    assert RegionKind.REDUNDANCY in kinds
    assert RegionKind.EVOLUTION in kinds
    assert RegionKind.DISAPPEARANCE in kinds


def test_long_stable_plateau_is_split_into_representative_and_redundant_regions() -> None:
    result = analyze_region_interest(*make_inputs())
    redundant = [region for region in result.regions if region.kind is RegionKind.REDUNDANCY]
    sustain = [region for region in result.regions if region.kind is RegionKind.SUSTAIN]
    assert len(redundant) == 1
    assert len(sustain) == 1
    assert sustain[0].end_sample == redundant[0].start_sample
    assert redundant[0].redundancy_score >= 0.75
    assert redundant[0].interest_score < sustain[0].interest_score


def test_saturation_and_noise_overrides_are_explicit() -> None:
    saturated = analyze_region_interest(*make_inputs(saturation_score=0.8))
    assert any(region.kind is RegionKind.SATURATION for region in saturated.regions)

    signal, extension, segmentation = make_inputs(noisy=True)
    segmentation.segments[3].voiced_frame_ratio = 0.0
    noisy_result = analyze_region_interest(signal, extension, segmentation)
    assert any(region.kind is RegionKind.NOISE for region in noisy_result.regions)


def test_interest_allocation_uses_61_slots_and_deprioritizes_redundancy() -> None:
    analysis = analyze_region_interest(*make_inputs())
    allocation = allocate_region_slots(analysis, total_slots=61)
    assert sum(allocation.region_slot_counts) == 61
    evolution_index = next(
        region.index for region in analysis.regions if region.kind is RegionKind.EVOLUTION
    )
    redundant_index = next(
        region.index for region in analysis.regions if region.kind is RegionKind.REDUNDANCY
    )
    assert allocation.region_slot_counts[evolution_index] > allocation.region_slot_counts[redundant_index]


def test_region_hash_allocation_and_json_are_deterministic() -> None:
    first = analyze_region_interest(*make_inputs())
    second = analyze_region_interest(*make_inputs())
    assert first.analysis_sha256 == second.analysis_sha256
    assert allocate_region_slots(first).to_dict() == allocate_region_slots(second).to_dict()
    json.dumps(first.to_dict(), allow_nan=False, sort_keys=True)


def test_signal_link_mismatch_is_rejected() -> None:
    signal, extension, segmentation = make_inputs()
    extension.signal_analysis_sha256 = "e" * 64
    with pytest.raises(ValueError, match="does not link"):
        analyze_region_interest(signal, extension, segmentation)


def test_single_active_steady_segment_is_establishment_not_disappearance() -> None:
    signal, extension, segmentation = make_inputs()
    segmentation.segments = (
        segment(0, 0, 100, "silence", rms=0.0, voiced=0.0),
        segment(1, 100, 1700, "steady", flux=0.005),
    )
    result = analyze_region_interest(signal, extension, segmentation)
    active = [region for region in result.regions if region.kind is not RegionKind.SILENCE]
    assert active[0].kind is RegionKind.ESTABLISHMENT
    assert all(region.kind is not RegionKind.DISAPPEARANCE for region in active)


def test_segmentation_identity_mismatch_is_rejected() -> None:
    signal, extension, segmentation = make_inputs()
    segmentation.sample_count = 1699
    with pytest.raises(ValueError, match="sample count"):
        analyze_region_interest(signal, extension, segmentation)


def test_allocation_hash_and_region_count_are_explicit() -> None:
    analysis = analyze_region_interest(*make_inputs())
    allocation = allocate_region_slots(analysis)
    assert allocation.region_count == len(analysis.regions)
    assert len(allocation.analysis_sha256) == 64
    assert allocation.to_dict()["region_count"] == len(analysis.regions)
