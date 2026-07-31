from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.analysis.segmentation import (
    AttackDecision,
    AttackPolicy,
    SegmentKind,
    SegmentationAnalysis,
    SourceSegment,
    segment_source,
)

SAMPLE_HASH = "a" * 64
SIGNAL_HASH = "b" * 64
PITCH_HASH = "c" * 64
PLAN_HASH = "d" * 64


def frame(index: int, start: int, *, rms: float = 0.2, onset: float = 0.0, flux: float = 0.01, energy: float = 0.0):
    return SimpleNamespace(
        frame_index=index,
        start_sample=start,
        center_seconds=(start + 50) / 1000.0,
        sample_count=100,
        rms=rms,
        onset_strength=onset,
        spectral_flux=flux,
        energy_change_db=energy,
    )


def pitch_frame(index: int, start: int, *, voiced: bool = True):
    return SimpleNamespace(
        frame_index=index,
        start_sample=start,
        center_seconds=(start + 50) / 1000.0,
        sample_count=100,
        voiced=voiced,
    )


def make_signal(*, attack: bool = True, silence: bool = False, release: bool = False, change: bool = True):
    frames = []
    pitch_frames = []
    for index, start in enumerate(range(0, 1000, 100)):
        rms = 0.0 if silence or index == 0 else 0.2
        onset = 2.0 if attack and index == 1 else 0.0
        flux = 0.30 if change and index == 4 else 0.01
        energy = -2.0 if release and index == 8 else 0.0
        frames.append(frame(index, start, rms=rms, onset=onset, flux=flux, energy=energy))
        pitch_frames.append(pitch_frame(index, start, voiced=not silence and index > 0))
    transients = () if not attack else (SimpleNamespace(sample_index=150, strength=2.0),)
    change_points = () if not change else (SimpleNamespace(sample_index=450, score=2.0, kind="spectral"),)
    transient = SimpleNamespace(
        sample_sha256=SAMPLE_HASH,
        frames=tuple(frames),
        transients=transients,
        change_points=change_points,
    )
    pitch = SimpleNamespace(analysis_sha256=PITCH_HASH, frames=tuple(pitch_frames))
    return SimpleNamespace(
        sample_rate=1000,
        sample_count=1000,
        sample_sha256=SAMPLE_HASH,
        analysis_sha256=SIGNAL_HASH,
        transient_change_analysis=transient,
        pitch_periodicity_analysis=pitch,
    )


def make_plan():
    return SimpleNamespace(
        sample_rate=1000,
        sample_count=1000,
        sample_sha256=SAMPLE_HASH,
        pitch_periodicity_analysis_sha256=PITCH_HASH,
        analysis_sha256=PLAN_HASH,
        target_frequency_hz=125.0,
        target_period_samples=8.0,
        repitch_required=True,
    )


def make_analysis(**kwargs):
    return segment_source(make_signal(), make_plan(), **kwargs)


def test_default_identity_and_links():
    result = make_analysis()
    assert result.schema_version == 1
    assert result.tool_version == "0.5.0"
    assert result.sample_sha256 == SAMPLE_HASH
    assert result.signal_analysis_sha256 == SIGNAL_HASH
    assert result.working_pitch_plan_sha256 == PLAN_HASH


def test_segments_cover_source_contiguously():
    result = make_analysis()
    assert result.segments[0].start_sample == 0
    assert result.segments[-1].end_sample == 1000
    assert all(a.end_sample == b.start_sample for a, b in zip(result.segments, result.segments[1:]))


def test_hash_is_deterministic():
    assert make_analysis().analysis_sha256 == make_analysis().analysis_sha256


def test_hash_is_lowercase_sha256():
    digest = make_analysis().analysis_sha256
    assert len(digest) == 64
    int(digest, 16)
    assert digest == digest.lower()


def test_to_dict_contains_segment_hashes():
    report = make_analysis().to_dict()
    assert report["segment_count"] == len(report["segments"])
    assert report["segment_sha256"] == [item["segment_sha256"] for item in report["segments"]]


def test_analysis_is_frozen():
    result = make_analysis()
    with pytest.raises(FrozenInstanceError):
        result.sample_rate = 44100


def test_segment_is_frozen():
    segment = make_analysis().segments[0]
    with pytest.raises(FrozenInstanceError):
        segment.kind = SegmentKind.STEADY


def test_attack_is_detected():
    result = make_analysis()
    assert result.attack_segment_index is not None
    assert result.segments[result.attack_segment_index].kind is SegmentKind.ATTACK


def test_auto_keeps_bounded_attack_followed_by_usable_content():
    result = make_analysis(minimum_steady_duration_ms=40.0)
    assert result.attack_decision is AttackDecision.KEEP
    assert result.attack_segment_index in result.usable_segment_indices


def test_explicit_reject_excludes_attack():
    result = make_analysis(attack_policy=AttackPolicy.REJECT)
    assert result.attack_decision is AttackDecision.REJECT
    assert result.attack_segment_index not in result.usable_segment_indices


def test_explicit_keep_includes_attack():
    result = make_analysis(attack_policy="keep")
    assert result.attack_decision is AttackDecision.KEEP
    assert result.attack_segment_index in result.usable_segment_indices


def test_no_attack_uses_not_present():
    result = segment_source(make_signal(attack=False), make_plan())
    assert result.attack_segment_index is None
    assert result.attack_decision is AttackDecision.NOT_PRESENT


def test_silent_source_has_no_usable_segments():
    result = segment_source(make_signal(attack=False, silence=True, change=False), make_plan())
    assert result.usable_segment_indices == ()
    assert all(segment.kind is SegmentKind.SILENCE for segment in result.segments)


def test_transition_segment_is_created_from_change_point():
    result = make_analysis()
    assert any(segment.kind is SegmentKind.TRANSITION for segment in result.segments)


def test_primary_sustain_is_usable():
    result = make_analysis(minimum_steady_duration_ms=40.0)
    assert result.primary_sustain_segment_index in result.usable_segment_indices


def test_working_pitch_metadata_is_propagated():
    result = make_analysis()
    assert result.working_frequency_hz == 125.0
    assert result.working_period_samples == 8.0
    assert result.repitch_required is True


def test_segment_hash_changes_with_classification_reason():
    segment = make_analysis().segments[0]
    changed = replace(segment, classification_reason="changed")
    assert segment.segment_sha256 != changed.segment_sha256


@pytest.mark.parametrize("policy", [AttackPolicy.AUTO, AttackPolicy.KEEP, AttackPolicy.REJECT, "auto", "keep", "reject"])
def test_supported_attack_policies(policy):
    assert segment_source(make_signal(), make_plan(), attack_policy=policy).attack_policy.value == str(getattr(policy, "value", policy))


@pytest.mark.parametrize("policy", ["invalid", "AUTO", "", None])
def test_rejects_invalid_attack_policy(policy):
    with pytest.raises((ValueError, TypeError)):
        segment_source(make_signal(), make_plan(), attack_policy=policy)


@pytest.mark.parametrize(
    "name,value",
    [
        ("minimum_segment_duration_ms", 0.0),
        ("minimum_segment_duration_ms", -1.0),
        ("attack_window_ms", 0.0),
        ("maximum_attack_duration_ms", 0.0),
        ("minimum_steady_duration_ms", 0.0),
        ("boundary_merge_window_ms", -1.0),
        ("minimum_attack_strength", -1.0),
        ("silence_rms_threshold", -1.0),
        ("transition_flux_threshold", -0.1),
        ("transition_flux_threshold", 1.1),
    ],
)
def test_rejects_invalid_configuration(name, value):
    with pytest.raises(ValueError):
        segment_source(make_signal(), make_plan(), **{name: value})


@pytest.mark.parametrize("field", ["sample_rate", "sample_count", "sample_sha256"])
def test_rejects_working_plan_identity_mismatch(field):
    plan = make_plan()
    setattr(plan, field, {"sample_rate": 2000, "sample_count": 999, "sample_sha256": "e" * 64}[field])
    with pytest.raises(ValueError, match="inconsistent"):
        segment_source(make_signal(), plan)


def test_rejects_pitch_hash_link_mismatch():
    plan = make_plan()
    plan.pitch_periodicity_analysis_sha256 = "e" * 64
    with pytest.raises(ValueError, match="does not link"):
        segment_source(make_signal(), plan)


def test_rejects_transient_sample_hash_mismatch():
    signal = make_signal()
    signal.transient_change_analysis.sample_sha256 = "e" * 64
    with pytest.raises(ValueError, match="transient analysis"):
        segment_source(signal, make_plan())


@pytest.mark.parametrize("tool_version", ["", " 0.5.0", "0.5.0 "])
def test_rejects_non_normalized_version(tool_version):
    with pytest.raises(ValueError, match="tool_version"):
        segment_source(make_signal(), make_plan(), tool_version=tool_version)


def test_minimum_duration_reduces_close_boundaries():
    signal = make_signal()
    signal.transient_change_analysis.change_points = (
        SimpleNamespace(sample_index=420, score=2.0, kind="spectral"),
        SimpleNamespace(sample_index=430, score=1.0, kind="energy"),
    )
    result = segment_source(signal, make_plan(), minimum_segment_duration_ms=40.0, boundary_merge_window_ms=20.0)
    assert len(result.segments) < 7


def test_report_serializes_enum_values():
    report = make_analysis().to_dict()
    assert report["attack_policy"] == "auto"
    assert report["attack_decision"] in {"keep", "reject", "not_present"}
    assert all(item["kind"] in {kind.value for kind in SegmentKind} for item in report["segments"])


def test_not_present_reason_is_explainable():
    result = segment_source(make_signal(attack=False), make_plan())
    assert "no qualified" in result.decision_reason.lower()
