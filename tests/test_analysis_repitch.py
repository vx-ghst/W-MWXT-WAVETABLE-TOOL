from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.analysis import repitch
from w_mwxt_wavetable_tool.analysis.repitch import (
    WorkingPitchDecision,
    WorkingPitchPolicy,
    analyze_audio_source_working_pitch,
    plan_working_pitch,
)


SAMPLE_HASH = "a" * 64
PITCH_HASH = "b" * 64


def pitch(
    frequency_hz: float | None = 440.0,
    *,
    periodicity_score: float = 0.92,
    pitch_stability: float = 0.88,
):
    return SimpleNamespace(
        sample_rate=48000,
        sample_count=96000,
        sample_sha256=SAMPLE_HASH,
        analysis_sha256=PITCH_HASH,
        frequency_hz=frequency_hz,
        periodicity_score=periodicity_score,
        pitch_stability=pitch_stability,
        reference_a4_hz=440.0,
    )


def test_auto_preserves_a4_at_48k() -> None:
    plan = plan_working_pitch(pitch())
    assert plan.policy is WorkingPitchPolicy.AUTO
    assert plan.decision is WorkingPitchDecision.NO_REPITCH
    assert not plan.repitch_required
    assert plan.repitch_ratio == 1.0
    assert plan.target_frequency_hz == 440.0


def test_auto_repitches_low_source_by_octaves() -> None:
    plan = plan_working_pitch(pitch(50.0))
    assert plan.decision is WorkingPitchDecision.REPITCH
    assert plan.repitch_required
    assert plan.target_frequency_hz == 400.0
    assert plan.repitch_ratio == 8.0


def test_no_repitch_policy_overrides_candidate_ranking() -> None:
    plan = plan_working_pitch(pitch(50.0), policy=WorkingPitchPolicy.NO_REPITCH)
    assert plan.decision is WorkingPitchDecision.NO_REPITCH
    assert plan.target_frequency_hz == 50.0
    assert plan.repitch_ratio == 1.0


def test_lock_policy_requires_frequency() -> None:
    with pytest.raises(ValueError, match="requires locked_frequency_hz"):
        plan_working_pitch(pitch(), policy=WorkingPitchPolicy.LOCK)


def test_lock_frequency_is_only_valid_with_lock_policy() -> None:
    with pytest.raises(ValueError, match="only valid"):
        plan_working_pitch(pitch(), locked_frequency_hz=330.0)


def test_explicit_lock_is_authoritative() -> None:
    plan = plan_working_pitch(
        pitch(), policy=WorkingPitchPolicy.LOCK, locked_frequency_hz=330.0
    )
    assert plan.locked
    assert plan.decision is WorkingPitchDecision.REPITCH
    assert plan.target_frequency_hz == 330.0
    assert plan.repitch_ratio == 0.75


def test_lock_matching_source_does_not_repitch() -> None:
    plan = plan_working_pitch(
        pitch(), policy=WorkingPitchPolicy.LOCK, locked_frequency_hz=440.0
    )
    assert plan.locked
    assert plan.decision is WorkingPitchDecision.NO_REPITCH
    assert not plan.repitch_required


def test_unpitched_auto_reports_unavailable() -> None:
    plan = plan_working_pitch(pitch(None))
    assert plan.decision is WorkingPitchDecision.PITCH_UNAVAILABLE
    assert plan.selected_candidate is None
    assert plan.repitch_ratio is None


def test_unpitched_no_repitch_preserves_source() -> None:
    plan = plan_working_pitch(pitch(None), policy=WorkingPitchPolicy.NO_REPITCH)
    assert plan.decision is WorkingPitchDecision.NO_REPITCH
    assert plan.selected_candidate is None
    assert not plan.repitch_required


def test_unpitched_lock_is_rejected() -> None:
    with pytest.raises(ValueError, match="detected source frequency"):
        plan_working_pitch(
            pitch(None), policy=WorkingPitchPolicy.LOCK, locked_frequency_hz=440.0
        )


def test_low_periodicity_withholds_automatic_repitch() -> None:
    plan = plan_working_pitch(pitch(50.0, periodicity_score=0.40))
    assert plan.decision is WorkingPitchDecision.NO_REPITCH
    assert plan.target_frequency_hz == 50.0
    assert "periodicity" in plan.decision_reason


def test_low_pitch_stability_withholds_automatic_repitch() -> None:
    plan = plan_working_pitch(pitch(50.0, pitch_stability=0.10))
    assert plan.decision is WorkingPitchDecision.NO_REPITCH
    assert plan.target_frequency_hz == 50.0
    assert "stability" in plan.decision_reason


def test_improvement_gate_can_withhold_repitch() -> None:
    plan = plan_working_pitch(pitch(50.0), minimum_score_improvement=0.90)
    assert plan.decision is WorkingPitchDecision.NO_REPITCH
    assert plan.target_frequency_hz == 50.0


def test_plan_hash_is_deterministic() -> None:
    assert plan_working_pitch(pitch()).analysis_sha256 == plan_working_pitch(
        pitch()
    ).analysis_sha256


def test_policy_changes_plan_hash() -> None:
    auto = plan_working_pitch(pitch())
    preserve = plan_working_pitch(pitch(), policy=WorkingPitchPolicy.NO_REPITCH)
    assert auto.analysis_sha256 != preserve.analysis_sha256


def test_selected_candidate_links_to_candidate_analysis() -> None:
    plan = plan_working_pitch(pitch(50.0))
    assert plan.selected_candidate_sha256 in plan.pitch_candidates.candidate_sha256


def test_plan_is_frozen() -> None:
    plan = plan_working_pitch(pitch())
    with pytest.raises(FrozenInstanceError):
        plan.locked = True


def test_audio_source_wrapper_forwards_pitch_configuration(monkeypatch) -> None:
    captured: dict[str, object] = {}
    analysis = pitch()

    def fake_pitch(source, **kwargs):
        captured.update(kwargs)
        return analysis

    monkeypatch.setattr(repitch, "analyze_audio_source_pitch_periodicity", fake_pitch)
    source = object()
    plan = analyze_audio_source_working_pitch(
        source,
        pitch_frame_size=2048,
        pitch_hop_size=512,
        minimum_frequency_hz=60.0,
        maximum_frequency_hz=1200.0,
        pitch_confidence_threshold=0.70,
    )
    assert plan.sample_sha256 == SAMPLE_HASH
    assert captured["frame_size"] == 2048
    assert captured["hop_size"] == 512
    assert captured["minimum_frequency_hz"] == 60.0
    assert captured["maximum_frequency_hz"] == 1200.0
    assert captured["confidence_threshold"] == 0.70


@pytest.mark.parametrize(
    "name,value",
    [
        ("minimum_periodicity_score", -0.1),
        ("minimum_pitch_stability", 1.1),
        ("minimum_score_improvement", float("nan")),
    ],
)
def test_invalid_plan_thresholds_are_rejected(name: str, value: float) -> None:
    with pytest.raises(ValueError):
        plan_working_pitch(pitch(), **{name: value})


def test_enum_values_are_stable() -> None:
    assert [policy.value for policy in WorkingPitchPolicy] == [
        "auto",
        "lock",
        "no_repitch",
    ]
    assert [decision.value for decision in WorkingPitchDecision] == [
        "repitch",
        "no_repitch",
        "pitch_unavailable",
    ]


def test_plan_serialization_is_finite_json() -> None:
    rendered = json.dumps(plan_working_pitch(pitch(50.0)).to_dict(), allow_nan=False)
    assert "NaN" not in rendered
    assert "Infinity" not in rendered
