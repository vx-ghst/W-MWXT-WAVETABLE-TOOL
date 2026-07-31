from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis.cycle_detection import (
    CycleCandidate,
    CycleCandidateStatus,
    CycleDiscoveryAnalysis,
    analyze_audio_source_cycles,
    discover_cycles,
)


def sample_hash(samples: np.ndarray) -> str:
    return sha256(samples.astype("<f8", copy=False).tobytes(order="C")).hexdigest()


def make_samples(*, noisy: bool = False) -> np.ndarray:
    time = np.arange(1600, dtype=np.float64)
    samples = np.sin(2.0 * np.pi * time / 8.0)
    if noisy:
        samples = samples.copy()
        generator = np.random.default_rng(42)
        samples[800:] = generator.normal(0.0, 0.5, 800)
    return samples


def make_segment(index: int, start: int, end: int, digest: str):
    return SimpleNamespace(
        index=index,
        start_sample=start,
        end_sample=end,
        segment_sha256=digest,
        kind=SimpleNamespace(value="steady"),
    )


def make_plan(samples: np.ndarray, *, pitch_available: bool = True):
    digest = sample_hash(samples)
    if not pitch_available:
        target_frequency = None
        target_period = None
        ratio = None
    else:
        target_frequency = 62.5
        target_period = 16.0
        ratio = 0.5
    return SimpleNamespace(
        sample_rate=1000,
        sample_count=samples.size,
        sample_sha256=digest,
        analysis_sha256="d" * 64,
        target_frequency_hz=target_frequency,
        target_period_samples=target_period,
        repitch_ratio=ratio,
        repitch_required=bool(pitch_available),
    )


def make_segmentation(samples: np.ndarray, *, pitch_available: bool = True, short: bool = False):
    digest = sample_hash(samples)
    if short:
        segments = (
            make_segment(0, 0, 8, "a" * 64),
            make_segment(1, 8, samples.size, "b" * 64),
        )
        usable = (0,)
    else:
        segments = (
            make_segment(0, 0, 800, "a" * 64),
            make_segment(1, 800, 1600, "b" * 64),
        )
        usable = (0, 1)
    return SimpleNamespace(
        sample_rate=1000,
        sample_count=samples.size,
        sample_sha256=digest,
        analysis_sha256="c" * 64,
        working_pitch_plan_sha256="d" * 64,
        working_frequency_hz=62.5 if pitch_available else None,
        working_period_samples=16.0 if pitch_available else None,
        repitch_required=bool(pitch_available),
        segments=segments,
        usable_segment_indices=usable,
    )


def make_analysis(**kwargs) -> CycleDiscoveryAnalysis:
    samples = make_samples()
    kwargs.setdefault("maximum_cycles_per_segment", 4)
    return discover_cycles(
        samples,
        make_segmentation(samples),
        make_plan(samples),
        **kwargs,
    )


def test_identity_and_hash_links() -> None:
    samples = make_samples()
    result = make_analysis()
    assert result.schema_version == 1
    assert result.tool_version == "0.5.0"
    assert result.sample_sha256 == sample_hash(samples)
    assert result.segmentation_analysis_sha256 == "c" * 64
    assert result.working_pitch_plan_sha256 == "d" * 64


def test_source_period_maps_virtual_repitch_to_source_domain() -> None:
    result = make_analysis()
    assert result.working_period_samples == 16.0
    assert result.repitch_ratio == 0.5
    assert result.source_period_samples == 8.0


def test_candidate_indexes_are_contiguous() -> None:
    result = make_analysis()
    assert tuple(candidate.index for candidate in result.candidates) == tuple(range(result.candidate_count))


def test_local_indexes_restart_per_segment() -> None:
    result = make_analysis()
    for segment_index in result.analyzed_segment_indices:
        indexes = [candidate.local_index for candidate in result.candidates if candidate.segment_index == segment_index]
        assert indexes == list(range(len(indexes)))


def test_candidates_remain_inside_linked_segments() -> None:
    samples = make_samples()
    segmentation = make_segmentation(samples)
    result = discover_cycles(samples, segmentation, make_plan(samples), maximum_cycles_per_segment=4)
    for candidate in result.candidates:
        segment = segmentation.segments[candidate.segment_index]
        assert segment.start_sample <= candidate.start_sample < candidate.end_sample <= segment.end_sample
        assert candidate.source_segment_sha256 == segment.segment_sha256


def test_candidate_lengths_track_source_period() -> None:
    result = make_analysis()
    assert result.candidates
    assert all(7 <= candidate.cycle_length_samples <= 9 for candidate in result.candidates)


def test_periodic_source_produces_accepted_candidates() -> None:
    result = make_analysis()
    assert result.accepted_candidate_count > 0
    assert all(candidate.periodicity_score > 0.99 for candidate in result.candidates)


def test_candidate_and_analysis_hashes_are_deterministic() -> None:
    first = make_analysis()
    second = make_analysis()
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.candidate_sha256 == second.candidate_sha256


def test_hashes_are_lowercase_sha256() -> None:
    result = make_analysis()
    digests = (result.analysis_sha256, *result.candidate_sha256)
    assert all(len(value) == 64 and value == value.lower() for value in digests)
    assert all(int(value, 16) >= 0 for value in digests)


def test_to_dict_links_candidate_hashes() -> None:
    report = make_analysis().to_dict()
    assert report["candidate_count"] == len(report["candidates"])
    assert report["candidate_sha256"] == [item["candidate_sha256"] for item in report["candidates"]]


def test_models_are_frozen() -> None:
    result = make_analysis()
    with pytest.raises(FrozenInstanceError):
        result.sample_rate = 44100
    with pytest.raises(FrozenInstanceError):
        result.candidates[0].status = CycleCandidateStatus.REJECTED


def test_strict_gate_rejects_candidates_with_reasons() -> None:
    result = make_analysis(minimum_seam_score=1.0)
    rejected = [candidate for candidate in result.candidates if candidate.status is CycleCandidateStatus.REJECTED]
    assert rejected
    assert all(candidate.rejection_reasons for candidate in rejected)


def test_pitch_unavailable_defers_cycle_discovery() -> None:
    samples = make_samples()
    result = discover_cycles(
        samples,
        make_segmentation(samples, pitch_available=False),
        make_plan(samples, pitch_available=False),
    )
    assert result.candidates == ()
    assert result.analyzed_segment_indices == ()
    assert result.skipped_segment_indices == (0, 1)
    assert result.source_period_samples is None


def test_short_segment_is_skipped() -> None:
    samples = make_samples()
    result = discover_cycles(
        samples,
        make_segmentation(samples, short=True),
        make_plan(samples),
        maximum_cycles_per_segment=4,
    )
    assert result.analyzed_segment_indices == ()
    assert result.skipped_segment_indices == (0,)


def test_maximum_cycles_caps_each_segment() -> None:
    result = make_analysis()
    counts = {
        index: sum(candidate.segment_index == index for candidate in result.candidates)
        for index in result.analyzed_segment_indices
    }
    assert all(count <= 4 for count in counts.values())


def test_candidate_hash_changes_with_metric() -> None:
    candidate = make_analysis().candidates[0]
    changed = replace(candidate, composite_score=max(0.0, candidate.composite_score - 0.01))
    assert changed.candidate_sha256 != candidate.candidate_sha256


def test_analysis_hash_changes_with_gate() -> None:
    assert make_analysis().analysis_sha256 != make_analysis(minimum_seam_score=0.60).analysis_sha256


def test_noisy_second_segment_is_measured_independently() -> None:
    samples = make_samples(noisy=True)
    result = discover_cycles(
        samples,
        make_segmentation(samples),
        make_plan(samples),
        maximum_cycles_per_segment=3,
    )
    first_scores = [candidate.composite_score for candidate in result.candidates if candidate.segment_index == 0]
    second_scores = [candidate.composite_score for candidate in result.candidates if candidate.segment_index == 1]
    assert first_scores and second_scores
    assert max(first_scores) > max(second_scores)


def test_candidate_time_fields_match_sample_bounds() -> None:
    candidate = make_analysis().candidates[0]
    assert candidate.start_seconds == candidate.start_sample / candidate.sample_rate
    assert candidate.end_seconds == candidate.end_sample / candidate.sample_rate
    assert candidate.duration_seconds == candidate.cycle_length_samples / candidate.sample_rate


def test_analyzed_and_skipped_segments_partition_usable_segments() -> None:
    result = make_analysis()
    assert set(result.analyzed_segment_indices).isdisjoint(result.skipped_segment_indices)
    assert set(result.analyzed_segment_indices) | set(result.skipped_segment_indices) == set(result.usable_segment_indices)


@pytest.mark.parametrize("maximum", [1, 2, 4, 8])
def test_supported_cycle_caps(maximum: int) -> None:
    result = make_analysis(maximum_cycles_per_segment=maximum)
    assert result.maximum_cycles_per_segment == maximum


@pytest.mark.parametrize(
    "name,value",
    [
        ("period_search_radius_ratio", 0.0),
        ("period_search_radius_ratio", -0.1),
        ("period_search_radius_ratio", 1.1),
        ("boundary_search_radius_samples", -1),
        ("boundary_search_radius_samples", 1.5),
        ("maximum_cycles_per_segment", 0),
        ("maximum_cycles_per_segment", 1025),
        ("minimum_periodicity_score", -0.1),
        ("minimum_seam_score", 1.1),
        ("minimum_energy_consistency_score", -0.1),
        ("minimum_spectral_consistency_score", 1.1),
    ],
)
def test_rejects_invalid_configuration(name: str, value: object) -> None:
    samples = make_samples()
    with pytest.raises((TypeError, ValueError)):
        discover_cycles(
            samples,
            make_segmentation(samples),
            make_plan(samples),
            **{name: value},
        )


@pytest.mark.parametrize("field", ["sample_rate", "sample_count", "sample_sha256"])
def test_rejects_plan_identity_mismatch(field: str) -> None:
    samples = make_samples()
    plan = make_plan(samples)
    setattr(plan, field, {"sample_rate": 2000, "sample_count": 1599, "sample_sha256": "e" * 64}[field])
    with pytest.raises(ValueError, match="identity"):
        discover_cycles(samples, make_segmentation(samples), plan)


def test_rejects_segmentation_sample_hash_mismatch() -> None:
    samples = make_samples()
    segmentation = make_segmentation(samples)
    segmentation.sample_sha256 = "e" * 64
    with pytest.raises(ValueError, match="sample hash"):
        discover_cycles(samples, segmentation, make_plan(samples))


def test_rejects_plan_link_mismatch() -> None:
    samples = make_samples()
    segmentation = make_segmentation(samples)
    segmentation.working_pitch_plan_sha256 = "e" * 64
    with pytest.raises(ValueError, match="does not link"):
        discover_cycles(samples, segmentation, make_plan(samples))


@pytest.mark.parametrize("tool_version", ["", " 0.5.0", "0.5.0 "])
def test_rejects_non_normalized_version(tool_version: str) -> None:
    samples = make_samples()
    with pytest.raises(ValueError, match="tool_version"):
        discover_cycles(
            samples,
            make_segmentation(samples),
            make_plan(samples),
            tool_version=tool_version,
        )


@pytest.mark.parametrize(
    "status,reasons,valid",
    [
        (CycleCandidateStatus.ACCEPTED, (), True),
        (CycleCandidateStatus.REJECTED, ("periodicity_below_gate",), True),
        (CycleCandidateStatus.ACCEPTED, ("unexpected",), False),
        (CycleCandidateStatus.REJECTED, (), False),
    ],
)
def test_candidate_status_reason_contract(status, reasons, valid) -> None:
    candidate = make_analysis().candidates[0]
    if valid:
        replace(candidate, status=status, rejection_reasons=reasons)
    else:
        with pytest.raises(ValueError):
            replace(candidate, status=status, rejection_reasons=reasons)


def test_audio_wrapper_preserves_public_contract(monkeypatch) -> None:
    samples = make_samples()
    source = SimpleNamespace(
        mono_samples=samples,
        metadata=SimpleNamespace(sample_rate=1000),
        sample_sha256=sample_hash(samples),
    )
    signal = SimpleNamespace(pitch_periodicity_analysis=object())
    plan = make_plan(samples)
    segmentation = make_segmentation(samples)
    monkeypatch.setattr("w_mwxt_wavetable_tool.analysis.cycle_detection.analyze_audio_source_signal", lambda value: signal)
    monkeypatch.setattr("w_mwxt_wavetable_tool.analysis.cycle_detection.plan_working_pitch", lambda *args, **kwargs: plan)
    monkeypatch.setattr("w_mwxt_wavetable_tool.analysis.cycle_detection.segment_source", lambda *args, **kwargs: segmentation)
    result = analyze_audio_source_cycles(source, maximum_cycles_per_segment=2)
    assert result.sample_sha256 == source.sample_sha256
    assert result.maximum_cycles_per_segment == 2
