from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import pytest

from v8i_helpers import identical_build
from w_mwxt_wavetable_tool import (
    ConsolidationPolicy,
    ConsolidationStatus,
    FinalSlotClass,
    WavetableContractError,
    consolidate_wavetable_build,
)


def test_v8i_models_are_canonical_hashed_and_immutable() -> None:
    analysis = consolidate_wavetable_build(identical_build())
    assert analysis.status is ConsolidationStatus.COMPLETE
    assert analysis.logical_wavetable is not None
    assert analysis.physical_wave_set is not None
    assert analysis.mapping is not None
    assert analysis.final_usefulness is not None
    assert analysis.report is not None
    assert len(analysis.logical_wavetable.slots) == 61
    assert analysis.physical_wave_set.physical_wave_count == 1
    assert len(analysis.mapping.logical_to_physical) == 61
    assert set(analysis.final_usefulness.slot_classes) <= set(FinalSlotClass)
    payload = analysis.to_dict()
    assert payload["analysis_sha256"] == analysis.analysis_sha256
    assert json.loads(analysis.to_json())["analysis_sha256"] == analysis.analysis_sha256
    with pytest.raises(FrozenInstanceError):
        analysis.reason = "changed"  # type: ignore[misc]


def test_consolidation_policy_rejects_non_conservative_near_threshold() -> None:
    with pytest.raises(WavetableContractError, match="too permissive"):
        ConsolidationPolicy(near_perceptual_distance=0.11)
