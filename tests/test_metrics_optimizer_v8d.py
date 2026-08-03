from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pytest

from w_mwxt_wavetable_tool.profiles import (
    OptimizationProfile,
    evaluate_bass_working_pitches,
    profile_definition,
)
from w_mwxt_wavetable_tool.xt.quantization import QuantizationAlgorithm
from w_mwxt_wavetable_tool.xt.resampling import NormalizationPolicy
from w_mwxt_wavetable_tool.xt.symmetry_candidates import HalfWaveMethod, SymmetryTreatment, WaveTransform
from w_mwxt_wavetable_tool.xt.wave_metrics import analyze_xt_aliasing_risk, measure_xt_wave_metrics
from w_mwxt_wavetable_tool.xt.wave_optimizer import (
    OptimizationStatus,
    OptimizerSearchConfig,
    evaluate_cycle_xt_compatibility,
    optimize_xt_wave,
)


def sine(harmonic: int = 1) -> np.ndarray:
    return np.sin(2.0 * np.pi * harmonic * np.arange(128) / 128.0)


def config() -> OptimizerSearchConfig:
    return OptimizerSearchConfig(
        phases=(0, 1, 2, 3),
        transforms=(WaveTransform.IDENTITY, WaveTransform.TIME_REVERSED),
        half_wave_methods=(
            HalfWaveMethod.PAIRWISE_LEAST_SQUARES,
            HalfWaveMethod.RESAMPLED_FOURIER,
        ),
        quantization_algorithms=(QuantizationAlgorithm.NEAREST,),
        top_candidate_count=4,
    )


def test_identical_wave_metrics_are_near_perfect() -> None:
    source = sine()
    metrics = measure_xt_wave_metrics(source, source)
    assert metrics.time_nrmse == 0.0
    assert metrics.perceptual_difference == 0.0
    assert metrics.spectral_similarity == pytest.approx(1.0)
    assert metrics.sub_score == pytest.approx(1.0)
    assert metrics.bass_score == pytest.approx(1.0)
    assert not metrics.monophonic_bass_warning


def test_phase_and_bass_warning_are_explicit() -> None:
    source = sine()
    shifted = np.roll(source, 32)
    metrics = measure_xt_wave_metrics(source, shifted)
    assert metrics.phase_shift_samples != 0
    assert metrics.phase_difference > 0.0
    assert metrics.monophonic_bass_warning or metrics.sub_score < 1.0


def test_aliasing_is_measured_across_notes_and_octaves() -> None:
    source = 0.8 * sine(1) + 0.2 * sine(40)
    analysis = analyze_xt_aliasing_risk(source)
    assert len(analysis.note_risks) == 5
    assert tuple(item.playback_frequency_hz for item in analysis.note_risks) == (55.0, 110.0, 220.0, 440.0, 880.0)
    assert analysis.note_risks[-1].risk > analysis.note_risks[0].risk
    assert analysis.maximum_risk == max(item.risk for item in analysis.note_risks)


def test_bass_profile_optimizer_is_deterministic_and_exposes_all_representations() -> None:
    source = 0.8 * sine(1) + 0.15 * sine(2) + 0.05 * sine(20)
    left = optimize_xt_wave(source, profile=OptimizationProfile.BASS_SUB, search_config=config())
    right = optimize_xt_wave(source, profile=OptimizationProfile.BASS_SUB, search_config=config())
    assert left.to_dict() == right.to_dict()
    assert left.status is OptimizationStatus.AUTOMATIC
    assert left.search_config.candidate_count == 16
    assert len(left.representations.original_source) == 128
    assert len(left.representations.native_64_float) == 64
    assert len(left.representations.quantized_native_64) == 64
    assert len(left.representations.reconstructed_128) == 128
    assert left.bass_protection.pitch_comparison_required
    assert 0.0 <= left.bass_protection.sub_score <= 1.0
    assert 0.0 <= left.bass_protection.bass_score <= 1.0


def test_manual_treatment_override_records_automatic_optimum() -> None:
    source = 0.8 * sine(1) + 0.1 * sine(4)
    requested = SymmetryTreatment(
        transform=WaveTransform.POLARITY_INVERTED,
        phase_rotation_samples=0,
        half_wave_method=HalfWaveMethod.FIRST_HALF,
        quantization_algorithm=QuantizationAlgorithm.NEAREST,
        normalization=NormalizationPolicy.NONE,
    )
    result = optimize_xt_wave(
        source,
        profile=OptimizationProfile.LEAD,
        requested_treatment=requested,
        search_config=config(),
    )
    assert result.status is OptimizationStatus.OVERRIDDEN
    assert result.requested_treatment == requested
    assert result.selected_candidate.treatment == requested
    assert result.automatic_treatment != requested
    assert result.warnings


def test_cycle_compatibility_reports_xt_and_psychoacoustic_scores() -> None:
    result = evaluate_cycle_xt_compatibility(sine(), search_config=config())
    assert 0.0 <= result.xt_compatibility_score <= 1.0
    assert 0.0 <= result.psychoacoustic_quality_score <= 1.0
    assert result.recommended
    assert len(result.analysis_sha256) == 64


@dataclass(frozen=True)
class PitchCandidate:
    candidate_sha256: str
    target_frequency_hz: float
    target_period_samples: float
    score: float


@dataclass(frozen=True)
class PitchCandidates:
    analysis_sha256: str
    candidates: tuple[PitchCandidate, ...]


def test_bass_pitch_comparison_uses_all_v6_candidates() -> None:
    candidates = PitchCandidates(
        analysis_sha256="a" * 64,
        candidates=(
            PitchCandidate("1" * 64, 55.0, 128.0, 0.8),
            PitchCandidate("2" * 64, 82.41, 128.0, 0.9),
            PitchCandidate("3" * 64, 164.81, 64.0, 0.95),
        ),
    )
    result = evaluate_bass_working_pitches(candidates)
    assert len(result.evaluations) == 3
    assert result.selected in result.evaluations
    assert result.selected.target_frequency_hz in {55.0, 82.41, 164.81}
    assert math.isclose(max(item.bass_score for item in result.evaluations), result.selected.bass_score)


def test_experimental_profile_records_controlled_defect_preservation() -> None:
    source = np.tanh(2.5 * (0.8 * sine(1) + 0.25 * sine(7)))
    result = optimize_xt_wave(source, profile=OptimizationProfile.EXPERIMENTAL, search_config=config())
    assert result.profile.preserve_controlled_defects
    assert any("Experimental preserves" in item for item in result.warnings)
    assert all(item.controlled_defect_error >= 0.0 for item in result.top_candidates)


def test_profile_weighted_objectives_are_bounded_for_all_profiles() -> None:
    metrics = measure_xt_wave_metrics(sine(), 0.98 * sine())
    for profile in OptimizationProfile:
        score = metrics.weighted_objective(profile_definition(profile).weights)
        assert 0.0 <= score <= 1.0


def test_search_config_normalizes_serialized_enum_values() -> None:
    serialized = OptimizerSearchConfig(
        phases=(0,),
        transforms=("identity",),
        half_wave_methods=("pairwise_least_squares",),
        quantization_algorithms=("nearest",),
        normalization="none",
        top_candidate_count=1,
    )
    assert serialized.transforms == (WaveTransform.IDENTITY,)
    assert serialized.half_wave_methods == (HalfWaveMethod.PAIRWISE_LEAST_SQUARES,)
    assert serialized.quantization_algorithms == (QuantizationAlgorithm.NEAREST,)
    assert serialized.normalization is NormalizationPolicy.NONE


def test_exactly_sixty_one_waves_are_optimized_independently() -> None:
    from w_mwxt_wavetable_tool.xt.wave_optimizer import optimize_xt_wave_set

    minimal = OptimizerSearchConfig(
        phases=(0,),
        transforms=(WaveTransform.IDENTITY,),
        half_wave_methods=(HalfWaveMethod.PAIRWISE_LEAST_SQUARES,),
        quantization_algorithms=(QuantizationAlgorithm.NEAREST,),
        top_candidate_count=1,
    )
    waves = tuple((0.75 + 0.002 * index) * sine() for index in range(61))
    result = optimize_xt_wave_set(
        waves,
        profile=OptimizationProfile.BASS_SUB,
        search_config=minimal,
    )
    assert result.wave_count == 61
    assert tuple(item.index for item in result.entries) == tuple(range(61))
    assert result.bass_sequence_consistency is not None
    assert result.bass_sequence_consistency.wave_count == 61
    assert len(result.analysis_sha256) == 64
