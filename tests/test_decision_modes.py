from __future__ import annotations

from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.decision.models import (
    BehaviorClass,
    ConversionMode,
    ModeDecisionStatus,
    MusicalClass,
)
from w_mwxt_wavetable_tool.decision.mode_selector import select_conversion_mode


HASH = "a" * 64
SIGNAL_HASH = "b" * 64
EXTENSION_HASH = "c" * 64
BEHAVIOR_HASH = "d" * 64
MUSICAL_HASH = "e" * 64
PERCEPTUAL_HASH = "f" * 64
EVOLUTION_HASH = "1" * 64


def inputs(
    *,
    behavior: BehaviorClass = BehaviorClass.PERIODIC,
    periodicity: float = 0.9,
    pitch_stability: float = 0.9,
    rapid_fm: float = 0.0,
    active: float = 1.0,
    silent: bool = False,
    tonalness: float = 0.9,
    noisiness: float = 0.05,
    motion: float = 0.1,
    density: float = 0.4,
    useful_change: float = 0.05,
    harmonic_evolution: float = 0.05,
    musical_classes: tuple[MusicalClass, ...] = (MusicalClass.LEAD,),
):
    signal = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        analysis_sha256=SIGNAL_HASH,
        time_domain_analysis=SimpleNamespace(
            levels=SimpleNamespace(is_silent=silent),
            envelope=SimpleNamespace(active_frame_ratio=active),
        ),
        pitch_periodicity_analysis=SimpleNamespace(
            periodicity_score=periodicity,
            pitch_stability=pitch_stability,
        ),
    )
    extension = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        signal_analysis_sha256=SIGNAL_HASH,
        analysis_sha256=EXTENSION_HASH,
        frequency_modulation_analysis=SimpleNamespace(rapid_fm_score=rapid_fm),
    )
    score_map = {item.value: 0.01 for item in BehaviorClass}
    score_map[behavior.value] = 0.93
    behavior_model = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        signal_analysis_sha256=SIGNAL_HASH,
        signal_extension_analysis_sha256=EXTENSION_HASH,
        analysis_sha256=BEHAVIOR_HASH,
        score_map=score_map,
        ambiguity=0.1,
    )
    perceptual = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        signal_analysis_sha256=SIGNAL_HASH,
        signal_extension_analysis_sha256=EXTENSION_HASH,
        spectral_evolution_analysis_sha256=EVOLUTION_HASH,
        analysis_sha256=PERCEPTUAL_HASH,
        tonalness=tonalness,
        noisiness=noisiness,
        motion=motion,
        density=density,
    )
    musical = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        behavior_classification_sha256=BEHAVIOR_HASH,
        perceptual_feature_sha256=PERCEPTUAL_HASH,
        analysis_sha256=MUSICAL_HASH,
        selected_classes=musical_classes,
        ambiguity=0.1,
    )
    evolution = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        analysis_sha256=EVOLUTION_HASH,
        useful_change_score=useful_change,
        harmonic_evolution_score=harmonic_evolution,
    )
    return signal, extension, behavior_model, musical, perceptual, evolution


def select(**kwargs):
    return select_conversion_mode(*inputs(**kwargs))


@pytest.mark.parametrize(
    "expected,parameters",
    [
        (ConversionMode.STABLE_CYCLE, dict()),
        (ConversionMode.EVOLVING_HARMONICS, dict(behavior=BehaviorClass.EVOLVING, periodicity=0.6, pitch_stability=0.8, motion=0.9, useful_change=1.0, harmonic_evolution=0.9, musical_classes=(MusicalClass.PAD,))),
        (ConversionMode.DYNAMIC_PITCH, dict(behavior=BehaviorClass.PITCH_VARIABLE, periodicity=0.8, pitch_stability=0.05, rapid_fm=1.0, motion=0.8, musical_classes=(MusicalClass.FM_BASS,))),
        (ConversionMode.SPECTRAL_RECONSTRUCTION, dict(behavior=BehaviorClass.NOISY, periodicity=0.0, pitch_stability=0.0, tonalness=0.0, noisiness=1.0, density=0.8, musical_classes=(MusicalClass.NOISE,))),
        (ConversionMode.HYBRID, dict(behavior=BehaviorClass.HYBRID, periodicity=0.5, pitch_stability=0.4, tonalness=0.5, noisiness=0.5, motion=0.8, density=1.0, useful_change=0.8, musical_classes=(MusicalClass.HYBRID,))),
    ],
)
def test_all_five_modes_have_selectable_executable_paths(expected, parameters) -> None:
    result = select(**parameters)
    assert result.status is ModeDecisionStatus.SELECTED
    assert result.selected_mode is expected
    assert result.execution_path is not None
    assert result.execution_path.mode is expected
    assert len(result.scores) == 5


def test_manual_override_is_explicit_and_preserves_auto_scores() -> None:
    args = inputs()
    result = select_conversion_mode(*args, mode_override=ConversionMode.SPECTRAL_RECONSTRUCTION)
    assert result.status is ModeDecisionStatus.OVERRIDDEN
    assert result.selected_mode is ConversionMode.SPECTRAL_RECONSTRUCTION
    assert result.requested_override is ConversionMode.SPECTRAL_RECONSTRUCTION
    assert result.warnings
    assert sum(item.score for item in result.scores) == pytest.approx(1.0)


def test_weak_periodicity_forced_stable_cycle_has_warning_not_hidden_refusal() -> None:
    result = select_conversion_mode(
        *inputs(behavior=BehaviorClass.NON_PERIODIC, periodicity=0.0, tonalness=0.1),
        mode_override="stable_cycle",
    )
    assert result.status is ModeDecisionStatus.OVERRIDDEN
    assert any("weak periodicity" in warning for warning in result.warnings)


def test_silent_source_is_explicitly_rejected_even_with_override() -> None:
    result = select_conversion_mode(
        *inputs(active=0.0, silent=True),
        mode_override=ConversionMode.STABLE_CYCLE,
    )
    assert result.status is ModeDecisionStatus.REJECTED
    assert result.selected_mode is None
    assert result.execution_path is None
    assert result.requested_override is ConversionMode.STABLE_CYCLE
    assert "refused" in result.reason


def test_musical_classification_cannot_independently_force_mode() -> None:
    base_inputs = inputs(musical_classes=(MusicalClass.NOISE,))
    noisy_label = select_conversion_mode(*base_inputs)
    base_inputs[3].selected_classes = (MusicalClass.PAD,)
    pad_label = select_conversion_mode(*base_inputs)
    assert noisy_label.selected_mode is pad_label.selected_mode
    assert noisy_label.selected_mode is ConversionMode.STABLE_CYCLE


def test_invalid_override_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown conversion mode"):
        select_conversion_mode(*inputs(), mode_override="invalid")


def test_broken_analysis_link_is_rejected() -> None:
    args = list(inputs())
    args[1].signal_analysis_sha256 = "0" * 64
    with pytest.raises(ValueError, match="does not link"):
        select_conversion_mode(*args)


def test_mode_decision_is_deterministic_and_explained() -> None:
    first = select()
    second = select()
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256
    assert all(item.explanation for item in first.scores)
    assert first.evidence
