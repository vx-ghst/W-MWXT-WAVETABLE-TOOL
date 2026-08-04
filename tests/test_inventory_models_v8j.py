from __future__ import annotations

from dataclasses import replace

import pytest

from v8j_helpers import complete_source, validated_empty_signature
from w_mwxt_wavetable_tool import (
    InventoryState,
    analyze_xt_memory_inventory,
)
from w_mwxt_wavetable_tool.errors import ProtocolError


def test_complete_inventory_models_all_250_waves_and_32_wavetables() -> None:
    result = analyze_xt_memory_inventory(
        (complete_source(),),
        empty_wave_signature=validated_empty_signature(),
    )
    assert len(result.user_waves) == 250
    assert len(result.user_wavetables) == 32
    assert result.user_waves[0].number == 1000
    assert result.user_waves[-1].number == 1249
    assert result.user_wavetables[0].display_number == 97
    assert result.user_wavetables[-1].display_number == 128
    assert result.evidence_status.safe_free_enabled is True
    assert result.state_counts[InventoryState.SAFE_FREE.value] == 4
    assert result.analysis_sha256 == analyze_xt_memory_inventory(
        (complete_source(),),
        empty_wave_signature=validated_empty_signature(),
    ).analysis_sha256


def test_safe_free_entry_cannot_exist_without_signature_match() -> None:
    result = analyze_xt_memory_inventory((complete_source(),))
    orphan = result.wave_entry(1100)
    assert orphan.state is InventoryState.ORPHANED
    with pytest.raises(ProtocolError):
        replace(
            orphan,
            state=InventoryState.SAFE_FREE,
            matches_validated_empty_signature=False,
        )
