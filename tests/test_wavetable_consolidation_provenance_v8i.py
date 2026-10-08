from __future__ import annotations

from v8i_helpers import exact_mixed_provenance_build, identical_build
from w_mwxt_wavetable_tool import WaveOrigin, consolidate_wavetable_build


def test_physical_wave_aggregates_mixed_real_and_reconstructed_provenance() -> None:
    result = consolidate_wavetable_build(exact_mixed_provenance_build())
    assert result.mapping is not None
    assert result.physical_wave_set is not None
    physical_index = result.mapping.logical_to_physical[5]
    assert physical_index == result.mapping.logical_to_physical[6]
    physical = result.physical_wave_set.waves[physical_index]
    assert set(physical.logical_positions) >= {5, 6}
    assert set(physical.origins) >= {
        WaveOrigin.REAL_CYCLE,
        WaveOrigin.RECONSTRUCTED_CYCLE,
    }
    assert set(physical.source_candidate_ids) >= {"real-cycle", "reconstructed-cycle"}
    assert len(physical.logical_slot_sha256s) == len(physical.logical_positions)


def test_final_usefulness_covers_all_slots_and_prepares_essential_data_for_v9() -> None:
    result = consolidate_wavetable_build(identical_build())
    assert result.final_usefulness is not None
    usefulness = result.final_usefulness
    covered = (
        set(usefulness.structural_positions)
        | set(usefulness.transition_positions)
        | set(usefulness.redundant_positions)
    )
    assert covered == set(range(61))
    assert usefulness.essential_positions_for_v9 == (0, 30)
    assert usefulness.to_dict()["cdc_use_004_status"] == "prepared_for_v9"
