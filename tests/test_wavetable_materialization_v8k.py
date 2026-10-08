from __future__ import annotations

from v8k_helpers import v8k_inputs

from w_mwxt_wavetable_tool import (
    INTERPOLATED_WAVE_REFERENCE,
    WctdMode,
    materialize_v8k_wctd,
)


def _materialization():
    v8i, v8j, fixed_tail, _ = v8k_inputs()
    return materialize_v8k_wctd(v8i.primary_variant, v8j.allocation, fixed_tail)


def test_dense_wctd_has_61_explicit_positions_and_repeated_references() -> None:
    result = _materialization()
    dense = result.dense
    assert dense.mode is WctdMode.DENSE
    assert dense.explicit_user_positions == tuple(range(61))
    assert dense.interpolated_user_positions == ()
    assert len(set(dense.references[:61])) == 1
    assert dense.references[:61] == (dense.allocated_user_wave_numbers[0],) * 61


def test_sparse_candidate_uses_explicit_boundaries_and_interpolation_sentinel() -> None:
    sparse = _materialization().sparse_candidate
    assert sparse is not None
    assert sparse.mode is WctdMode.SPARSE
    assert 0 in sparse.explicit_user_positions
    assert 60 in sparse.explicit_user_positions
    assert sparse.references[0] == sparse.allocated_user_wave_numbers[0]
    assert sparse.references[60] == sparse.allocated_user_wave_numbers[0]
    assert all(sparse.references[position] == INTERPOLATED_WAVE_REFERENCE for position in sparse.interpolated_user_positions)
    assert sparse.sparse_hardware_enabled is False


def test_fixed_tail_is_preserved_exactly_in_dense_and_sparse() -> None:
    v8i, v8j, fixed_tail, _ = v8k_inputs()
    result = materialize_v8k_wctd(v8i.primary_variant, v8j.allocation, fixed_tail)
    assert result.dense.references[61:] == fixed_tail.references
    assert result.sparse_candidate.references[61:] == fixed_tail.references


def test_logical_wire_and_sysex_representations_are_distinct_and_exact() -> None:
    dense = _materialization().dense
    assert len(dense.logical_reference_payload) == 128
    assert len(dense.wire_payload()) == 256
    assert len(dense.sysex_message()) == 265
    payload = dense.to_dict()
    assert payload["logical_reference_bytes"] == 128
    assert payload["wire_wctd_nibbles"] == 256
    assert payload["wire_wctd_message_bytes"] == 265
    assert payload["boundaries"]["contains_wavetable_name"] is False


def test_materialization_is_deterministic() -> None:
    assert _materialization().analysis_sha256 == _materialization().analysis_sha256
