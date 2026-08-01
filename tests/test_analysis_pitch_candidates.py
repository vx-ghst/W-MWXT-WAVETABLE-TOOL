from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.analysis.pitch_candidates import (
    WorkingPitchCandidateKind,
    generate_working_pitch_candidates,
)


SAMPLE_HASH = "a" * 64
PITCH_HASH = "b" * 64


def pitch(
    frequency_hz: float | None = 440.0,
    *,
    sample_rate: int = 48000,
    periodicity_score: float = 0.92,
    pitch_stability: float = 0.88,
):
    return SimpleNamespace(
        sample_rate=sample_rate,
        sample_count=96000,
        sample_sha256=SAMPLE_HASH,
        analysis_sha256=PITCH_HASH,
        frequency_hz=frequency_hz,
        periodicity_score=periodicity_score,
        pitch_stability=pitch_stability,
        reference_a4_hz=440.0,
    )


def test_default_candidate_identity() -> None:
    result = generate_working_pitch_candidates(pitch())
    assert result.schema_version == 1
    assert result.tool_version == "0.6.0"
    assert result.sample_rate == 48000
    assert result.sample_count == 96000
    assert result.sample_sha256 == SAMPLE_HASH
    assert result.pitch_periodicity_analysis_sha256 == PITCH_HASH


def test_unpitched_analysis_has_no_candidates() -> None:
    result = generate_working_pitch_candidates(pitch(None))
    assert result.source_frequency_hz is None
    assert result.source_period_samples is None
    assert result.source_note_name is None
    assert result.candidates == ()


def test_locked_frequency_requires_detected_source_pitch() -> None:
    with pytest.raises(ValueError, match="detected source frequency"):
        generate_working_pitch_candidates(pitch(None), locked_frequency_hz=440.0)


def test_candidate_ranks_are_consecutive() -> None:
    result = generate_working_pitch_candidates(pitch())
    assert [candidate.rank for candidate in result.candidates] == list(
        range(1, len(result.candidates) + 1)
    )


def test_source_candidate_is_included() -> None:
    result = generate_working_pitch_candidates(pitch())
    source = [candidate for candidate in result.candidates if candidate.octave_shift == 0]
    assert len(source) == 1
    assert source[0].repitch_ratio == 1.0
    assert source[0].transposition_cents == 0.0


def test_octave_candidates_preserve_exact_frequency_ratios() -> None:
    result = generate_working_pitch_candidates(pitch(), maximum_octave_shift=2)
    by_shift = {
        candidate.octave_shift: candidate
        for candidate in result.candidates
        if candidate.kind is WorkingPitchCandidateKind.SOURCE_OCTAVE
    }
    assert by_shift[-2].target_frequency_hz == 110.0
    assert by_shift[-1].target_frequency_hz == 220.0
    assert by_shift[0].target_frequency_hz == 440.0
    assert by_shift[1].target_frequency_hz == 880.0
    assert by_shift[2].target_frequency_hz == 1760.0


def test_candidates_never_reach_nyquist() -> None:
    result = generate_working_pitch_candidates(pitch(4000.0), maximum_octave_shift=4)
    assert all(candidate.target_frequency_hz < 24000.0 for candidate in result.candidates)


def test_a4_at_48k_prefers_source_pitch() -> None:
    result = generate_working_pitch_candidates(pitch(440.0))
    assert result.candidates[0].octave_shift == 0
    assert result.candidates[0].within_preferred_period_range


def test_low_source_prefers_octave_up() -> None:
    result = generate_working_pitch_candidates(pitch(50.0))
    assert result.candidates[0].octave_shift == 3
    assert result.candidates[0].target_frequency_hz == 400.0


def test_high_source_prefers_octave_down() -> None:
    result = generate_working_pitch_candidates(pitch(2000.0))
    assert result.candidates[0].octave_shift == -2
    assert result.candidates[0].target_frequency_hz == 500.0


def test_explicit_lock_is_included() -> None:
    result = generate_working_pitch_candidates(pitch(), locked_frequency_hz=330.0)
    locked = [
        candidate
        for candidate in result.candidates
        if candidate.kind is WorkingPitchCandidateKind.EXPLICIT_LOCK
    ]
    assert len(locked) == 1
    assert locked[0].target_frequency_hz == 330.0
    assert locked[0].octave_shift is None


def test_candidate_hash_is_deterministic() -> None:
    first = generate_working_pitch_candidates(pitch())
    second = generate_working_pitch_candidates(pitch())
    assert first.candidate_sha256 == second.candidate_sha256


def test_analysis_hash_is_deterministic() -> None:
    first = generate_working_pitch_candidates(pitch())
    second = generate_working_pitch_candidates(pitch())
    assert first.analysis_sha256 == second.analysis_sha256


def test_configuration_changes_analysis_hash() -> None:
    first = generate_working_pitch_candidates(pitch())
    second = generate_working_pitch_candidates(
        pitch(), preferred_period_samples=192.0, maximum_period_samples=384.0
    )
    assert first.analysis_sha256 != second.analysis_sha256


def test_serialization_is_finite_json() -> None:
    rendered = json.dumps(
        generate_working_pitch_candidates(pitch()).to_dict(),
        allow_nan=False,
        sort_keys=True,
    )
    assert "NaN" not in rendered
    assert "Infinity" not in rendered


@pytest.mark.parametrize(
    "kwargs",
    [
        {"preferred_period_samples": 0.0},
        {"minimum_period_samples": 0.0},
        {"maximum_period_samples": 0.0},
        {
            "minimum_period_samples": 256.0,
            "preferred_period_samples": 128.0,
            "maximum_period_samples": 512.0,
        },
    ],
)
def test_invalid_period_configuration_is_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="period"):
        generate_working_pitch_candidates(pitch(), **kwargs)


@pytest.mark.parametrize("maximum_octave_shift", [-1, 9, 1.5])
def test_invalid_maximum_octave_shift_is_rejected(maximum_octave_shift: object) -> None:
    with pytest.raises(ValueError, match="maximum_octave_shift"):
        generate_working_pitch_candidates(
            pitch(), maximum_octave_shift=maximum_octave_shift  # type: ignore[arg-type]
        )


def test_invalid_sample_hash_is_rejected() -> None:
    invalid = pitch()
    invalid.sample_sha256 = "A" * 64
    with pytest.raises(ValueError, match="hash"):
        generate_working_pitch_candidates(invalid)


def test_invalid_pitch_analysis_hash_is_rejected() -> None:
    invalid = pitch()
    invalid.analysis_sha256 = "z" * 64
    with pytest.raises(ValueError, match="hash"):
        generate_working_pitch_candidates(invalid)


def test_candidate_analysis_is_frozen() -> None:
    result = generate_working_pitch_candidates(pitch())
    with pytest.raises(FrozenInstanceError):
        result.sample_rate = 44100
