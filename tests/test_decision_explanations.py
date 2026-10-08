from __future__ import annotations

import pytest

from w_mwxt_wavetable_tool.decision.explanations import (
    MODE_EXECUTION_PATHS,
    confidence_from_ranked_scores,
    execution_path_for_mode,
    validate_mode_execution_paths,
)
from w_mwxt_wavetable_tool.decision.models import ConversionMode


def test_every_mode_has_exactly_one_importable_callable_path() -> None:
    paths = validate_mode_execution_paths()
    assert len(paths) == 5
    assert tuple(path.mode for path in paths) == tuple(ConversionMode)
    assert set(MODE_EXECUTION_PATHS) == set(ConversionMode)


@pytest.mark.parametrize("mode", tuple(ConversionMode))
def test_execution_path_lookup_is_deterministic(mode: ConversionMode) -> None:
    first = execution_path_for_mode(mode)
    second = execution_path_for_mode(mode.value)
    assert first == second
    assert first.mode is mode
    assert first.module.startswith("w_mwxt_wavetable_tool.")
    assert first.callable_name
    assert first.purpose


def test_unknown_execution_path_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown conversion mode"):
        execution_path_for_mode("unknown")


@pytest.mark.parametrize(
    "scores",
    [
        (1.0,),
        (0.8, 0.2),
        (0.5, 0.5),
        (0.9, 0.05, 0.05),
    ],
)
def test_confidence_and_ambiguity_are_bounded_and_complementary(scores) -> None:
    confidence, ambiguity = confidence_from_ranked_scores(scores)
    assert 0.0 <= confidence <= 1.0
    assert 0.0 <= ambiguity <= 1.0
    assert confidence + ambiguity == pytest.approx(1.0)


def test_confidence_increases_with_winner_separation() -> None:
    separated = confidence_from_ranked_scores((0.9, 0.1))[0]
    tied = confidence_from_ranked_scores((0.5, 0.5))[0]
    assert separated > tied


def test_invalid_confidence_scores_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        confidence_from_ranked_scores(())
    with pytest.raises(ValueError, match="between 0 and 1"):
        confidence_from_ranked_scores((1.2, 0.0))
