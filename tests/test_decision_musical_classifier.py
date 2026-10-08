from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.decision.models import BehaviorClass, MusicalClass
from w_mwxt_wavetable_tool.decision.musical_classifier import classify_musical_source


HASH = "a" * 64
SIGNAL_HASH = "b" * 64
EXTENSION_HASH = "c" * 64
BEHAVIOR_HASH = "d" * 64
FORMANT_HASH = "e" * 64
PERCEPTUAL_HASH = "f" * 64


def inputs(
    *,
    behavior: BehaviorClass = BehaviorClass.PERIODIC,
    low: float = 0.5,
    fundamental: float = 0.7,
    brightness: float = 0.4,
    hardness: float = 0.3,
    saturation: float = 0.2,
    density: float = 0.4,
    motion: float = 0.2,
    tonal: float = 0.8,
    noise: float = 0.1,
    formant: float = 0.0,
    fm: float = 0.0,
    close_pair: float = 0.0,
):
    scores = {item.value: 0.01 for item in BehaviorClass}
    scores[behavior.value] = 0.93
    behavior_model = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        signal_extension_analysis_sha256=EXTENSION_HASH,
        analysis_sha256=BEHAVIOR_HASH,
        behavior=behavior,
        score_map=scores,
    )
    formant_model = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        analysis_sha256=FORMANT_HASH,
        aggregate_confidence=formant,
    )
    perceptual = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        signal_extension_analysis_sha256=EXTENSION_HASH,
        formant_analysis_sha256=FORMANT_HASH,
        analysis_sha256=PERCEPTUAL_HASH,
        low_frequency_power=low,
        fundamental_presence=fundamental,
        brightness=brightness,
        hardness=hardness,
        saturation=saturation,
        density=density,
        motion=motion,
        tonalness=tonal,
        noisiness=noise,
    )
    extension = SimpleNamespace(
        sample_rate=16000,
        sample_count=16000,
        sample_sha256=HASH,
        analysis_sha256=EXTENSION_HASH,
        frequency_modulation_analysis=SimpleNamespace(rapid_fm_score=fm),
        beating_analysis=SimpleNamespace(
            close_fundamentals_detected=close_pair > 0.0,
            confidence=close_pair,
        ),
    )
    return behavior_model, perceptual, formant_model, extension


def classify(**kwargs):
    return classify_musical_source(*inputs(**kwargs), score_threshold=0.55)


def test_taxonomy_contains_exactly_the_27_normative_labels() -> None:
    assert len(MusicalClass) == 27
    assert tuple(item.value for item in MusicalClass) == (
        "sub", "bass", "reese", "fm_bass", "dirty_bass", "hoover", "acid",
        "lead", "pad", "drone", "organ", "pwm", "supersaw", "wavetable",
        "bell", "fm_bell", "pluck", "vocal", "choir", "texture",
        "digital_noise", "noise", "piano", "guitar", "percussion", "fx",
        "hybrid",
    )


def test_every_class_has_a_score_and_explanation() -> None:
    result = classify()
    assert len(result.scores) == 27
    assert tuple(item.musical_class for item in result.scores) == tuple(MusicalClass)
    assert all(item.explanation for item in result.scores)
    assert result.selected_classes
    json.dumps(result.to_dict(), allow_nan=False, sort_keys=True)


@pytest.mark.parametrize(
    "expected,parameters",
    [
        (MusicalClass.SUB, dict(low=1.0, fundamental=1.0, brightness=0.0, tonal=0.9)),
        (MusicalClass.REESE, dict(behavior=BehaviorClass.QUASI_PERIODIC, low=0.8, close_pair=1.0, motion=0.8, density=0.9)),
        (MusicalClass.FM_BASS, dict(behavior=BehaviorClass.PITCH_VARIABLE, low=0.8, fm=1.0, hardness=0.8, density=0.7)),
        (MusicalClass.DIRTY_BASS, dict(low=0.8, saturation=1.0, hardness=1.0, noise=0.7)),
        (MusicalClass.SUPERSAW, dict(behavior=BehaviorClass.QUASI_PERIODIC, close_pair=1.0, brightness=0.9, density=1.0, motion=0.7)),
        (MusicalClass.FM_BELL, dict(behavior=BehaviorClass.TRANSIENT, fm=1.0, brightness=1.0, hardness=1.0, low=0.0)),
        (MusicalClass.VOCAL, dict(formant=1.0, tonal=0.8, fundamental=0.8, low=0.1)),
        (MusicalClass.NOISE, dict(behavior=BehaviorClass.NOISY, noise=1.0, tonal=0.0, fundamental=0.0, low=0.0)),
        (MusicalClass.PERCUSSION, dict(behavior=BehaviorClass.TRANSIENT, noise=0.7, hardness=0.9, density=0.8, tonal=0.1)),
        (MusicalClass.HYBRID, dict(behavior=BehaviorClass.HYBRID, low=0.4, tonal=0.5, noise=0.5, motion=0.5, density=0.8)),
    ],
)
def test_representative_archetypes_select_expected_label(expected, parameters) -> None:
    result = classify(**parameters)
    winner = max(result.scores, key=lambda item: item.score)
    assert winner.musical_class is expected
    assert expected in result.selected_classes


def test_multi_label_output_respects_threshold_and_maximum() -> None:
    result = classify_musical_source(*inputs(low=0.9, fundamental=0.9, tonal=0.9), score_threshold=0.45, maximum_labels=3)
    assert 1 <= len(result.selected_classes) <= 3
    assert all(
        item.selected == (item.musical_class in result.selected_classes)
        for item in result.scores
    )


def test_no_label_above_threshold_still_selects_canonical_winner() -> None:
    result = classify_musical_source(*inputs(), score_threshold=1.0, maximum_labels=5)
    assert len(result.selected_classes) == 1
    winner = max(result.scores, key=lambda item: item.score)
    assert result.selected_classes == (winner.musical_class,)


@pytest.mark.parametrize(
    "threshold,maximum,match",
    [(-0.1, 5, "threshold"), (1.1, 5, "threshold"), (0.5, 0, "maximum_labels"), (0.5, 28, "maximum_labels")],
)
def test_invalid_classifier_configuration_is_rejected(threshold, maximum, match) -> None:
    with pytest.raises(ValueError, match=match):
        classify_musical_source(*inputs(), score_threshold=threshold, maximum_labels=maximum)


def test_broken_links_are_rejected() -> None:
    behavior, perceptual, formants, extension = inputs()
    perceptual.signal_extension_analysis_sha256 = "0" * 64
    with pytest.raises(ValueError, match="not link"):
        classify_musical_source(behavior, perceptual, formants, extension)


def test_classification_is_deterministic() -> None:
    first = classify()
    second = classify()
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256
