from __future__ import annotations

import numpy as np
import pytest

from w_mwxt_wavetable_tool.audio import MonoPolicy, MonoStrategy, convert_to_mono
from w_mwxt_wavetable_tool.errors import InvalidAudioDataError


def test_complete_policy_values_are_stable() -> None:
    assert tuple(item.value for item in MonoPolicy) == (
        "auto",
        "sum",
        "average",
        "left",
        "right",
        "mid",
        "best_periodicity",
        "first_channel",
        "dominant_channel",
    )


def test_sum_and_average_are_distinct() -> None:
    source = np.array([[0.25, 0.50], [-0.25, 0.25]], dtype=np.float64)
    summed, sum_report = convert_to_mono(source, policy=MonoPolicy.SUM)
    averaged, average_report = convert_to_mono(source, policy=MonoPolicy.AVERAGE)
    np.testing.assert_allclose(summed, np.sum(source, axis=1))
    np.testing.assert_allclose(averaged, np.mean(source, axis=1))
    assert sum_report.strategy is MonoStrategy.SUM
    assert average_report.strategy is MonoStrategy.AVERAGE


def test_explicit_left_right_and_mid() -> None:
    source = np.array([[0.2, 0.8], [-0.4, 0.4]], dtype=np.float64)
    left, left_report = convert_to_mono(source, policy=MonoPolicy.LEFT)
    right, right_report = convert_to_mono(source, policy=MonoPolicy.RIGHT)
    mid, mid_report = convert_to_mono(source, policy=MonoPolicy.MID)
    np.testing.assert_array_equal(left, source[:, 0])
    np.testing.assert_array_equal(right, source[:, 1])
    np.testing.assert_allclose(mid, (source[:, 0] + source[:, 1]) / 2.0)
    assert left_report.strategy is MonoStrategy.LEFT
    assert right_report.strategy is MonoStrategy.RIGHT
    assert mid_report.strategy is MonoStrategy.MID


def test_mid_rejects_non_stereo_source() -> None:
    with pytest.raises(InvalidAudioDataError, match="exactly two"):
        convert_to_mono(np.ones((32, 3)), policy=MonoPolicy.MID)


def test_best_periodicity_requires_sample_rate() -> None:
    with pytest.raises(InvalidAudioDataError, match="sample_rate"):
        convert_to_mono(np.ones((32, 2)), policy=MonoPolicy.BEST_PERIODICITY)


def test_best_periodicity_selects_tonal_channel_over_noise() -> None:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    rng = np.random.default_rng(1234)
    noise = rng.normal(0.0, 0.25, time.size)
    tone = 0.25 * np.sin(2.0 * np.pi * 220.0 * time)
    source = np.column_stack((noise, tone))
    mono, report = convert_to_mono(
        source,
        policy=MonoPolicy.BEST_PERIODICITY,
        sample_rate=sample_rate,
    )
    np.testing.assert_allclose(mono, tone)
    assert report.strategy is MonoStrategy.BEST_PERIODICITY
    assert report.selected_channel == 1
    assert "channel_1" in report.reason
    assert "candidates:" in report.reason


def test_auto_uses_periodicity_when_score_is_decisive() -> None:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    rng = np.random.default_rng(7)
    source = np.column_stack(
        (
            rng.normal(0.0, 0.15, time.size),
            0.20 * np.sin(2.0 * np.pi * 330.0 * time),
        )
    )
    mono, report = convert_to_mono(source, sample_rate=sample_rate)
    np.testing.assert_allclose(mono, source[:, 1])
    assert report.strategy is MonoStrategy.AUTO_BEST_PERIODICITY
    assert report.selected_channel == 1


def test_auto_without_sample_rate_preserves_legacy_average() -> None:
    source = np.array([[0.0, 1.0], [0.25, 0.75], [-0.5, 0.5]])
    mono, report = convert_to_mono(source)
    np.testing.assert_allclose(mono, np.mean(source, axis=1))
    assert report.strategy is MonoStrategy.AVERAGE


def test_best_periodicity_is_deterministic() -> None:
    sample_rate = 8000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    source = np.column_stack(
        (
            0.1 * np.sin(2.0 * np.pi * 110.0 * time),
            0.1 * np.sin(2.0 * np.pi * 220.0 * time),
        )
    )
    first = convert_to_mono(
        source,
        policy=MonoPolicy.BEST_PERIODICITY,
        sample_rate=sample_rate,
    )
    second = convert_to_mono(
        source,
        policy=MonoPolicy.BEST_PERIODICITY,
        sample_rate=sample_rate,
    )
    np.testing.assert_array_equal(first[0], second[0])
    assert first[1].to_dict() == second[1].to_dict()


def test_scored_report_is_structured_and_finite() -> None:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    source = np.column_stack(
        (
            0.2 * np.sin(2.0 * np.pi * 220.0 * time),
            0.2 * np.sin(2.0 * np.pi * 330.0 * time),
        )
    )
    _, report = convert_to_mono(
        source,
        policy=MonoPolicy.BEST_PERIODICITY,
        sample_rate=sample_rate,
    )
    payload = report.to_dict()
    assert payload["selected_candidate"] is not None
    assert len(payload["candidate_periodicity_scores"]) == 3
    assert 0.0 <= payload["periodicity_margin"] <= 1.0


def test_auto_antiphase_protection_precedes_periodicity_scoring() -> None:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    left = 0.2 * np.sin(2.0 * np.pi * 220.0 * time)
    source = np.column_stack((left, -left))
    mono, report = convert_to_mono(source, sample_rate=sample_rate)
    np.testing.assert_allclose(mono, left)
    assert report.strategy is MonoStrategy.ANTIPHASE_CHANNEL_SELECTED
    assert report.candidate_periodicity_scores == ()


def test_candidate_name_duplicates_are_rejected() -> None:
    from w_mwxt_wavetable_tool.audio import score_mono_candidates

    candidates = (
        ("same", np.ones(128, dtype=np.float64)),
        ("same", np.ones(128, dtype=np.float64)),
    )
    with pytest.raises(InvalidAudioDataError, match="unique"):
        score_mono_candidates(candidates, 8000)


def test_project_parser_accepts_legacy_and_extended_mono_reports(tmp_path) -> None:
    import soundfile as sf

    from w_mwxt_wavetable_tool.audio import import_audio
    from w_mwxt_wavetable_tool.project import ProjectAudioRecord

    sample_rate = 8000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    source_path = tmp_path / "stereo.wav"
    sf.write(
        source_path,
        np.column_stack(
            (
                0.2 * np.sin(2.0 * np.pi * 220.0 * time),
                0.2 * np.sin(2.0 * np.pi * 330.0 * time),
            )
        ),
        sample_rate,
        subtype="FLOAT",
    )
    source = import_audio(source_path, mono_policy=MonoPolicy.BEST_PERIODICITY)
    extended = ProjectAudioRecord.from_audio_source(source).to_dict()
    reparsed_extended = ProjectAudioRecord.from_dict(extended)
    assert reparsed_extended.mono_conversion.selected_candidate is not None

    legacy = ProjectAudioRecord.from_audio_source(source).to_dict()
    del legacy["mono_conversion"]["selected_candidate"]
    del legacy["mono_conversion"]["candidate_periodicity_scores"]
    del legacy["mono_conversion"]["periodicity_margin"]
    reparsed_legacy = ProjectAudioRecord.from_dict(legacy)
    assert reparsed_legacy.mono_conversion.selected_candidate is None
    assert reparsed_legacy.mono_conversion.candidate_periodicity_scores == ()


def test_project_parser_rejects_partial_extended_mono_report(tmp_path) -> None:
    import soundfile as sf

    from w_mwxt_wavetable_tool.audio import import_audio
    from w_mwxt_wavetable_tool.errors import ProjectFormatError
    from w_mwxt_wavetable_tool.project import ProjectAudioRecord

    source_path = tmp_path / "mono.wav"
    sf.write(source_path, np.zeros(64, dtype=np.float64), 8000, subtype="FLOAT")
    payload = ProjectAudioRecord.from_audio_source(import_audio(source_path)).to_dict()
    del payload["mono_conversion"]["periodicity_margin"]
    with pytest.raises(ProjectFormatError, match="fields are invalid"):
        ProjectAudioRecord.from_dict(payload)
