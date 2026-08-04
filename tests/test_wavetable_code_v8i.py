from __future__ import annotations

from v8g_helpers import rejected_v8d
from v8h_helpers import v8h_context
from w_mwxt_wavetable_tool import (
    CodeV8HStatus,
    CodeV8IStatus,
    build_code_v8h,
    build_code_v8i,
)


def test_code_v8i_consolidates_every_v8h_variant_and_preserves_ranking() -> None:
    request, v8b, v8c, v8d, regions = v8h_context(requested_variants=2)
    v8h = build_code_v8h(request, v8b, v8c, v8d, regions)
    assert v8h.status is CodeV8HStatus.COMPLETE
    result = build_code_v8i(v8h)
    assert result.status is CodeV8IStatus.COMPLETE
    assert tuple(item.variant_id for item in result.variants) == tuple(
        item.variant_id for item in v8h.variants
    )
    assert tuple(item.rank for item in result.variants) == tuple(
        item.rank for item in v8h.variants
    )
    assert all(1 <= item.physical_wave_count <= 61 for item in result.variants)
    assert result.to_dict()["requirements"]["CDC-USE-004"] == "prepared_for_v9"
    assert result.to_dict()["boundaries"]["inventory_allocation"] is False


def test_code_v8i_rejects_incomplete_v8h_without_partial_output() -> None:
    request, v8b, v8c, v8d, regions = v8h_context(requested_variants=1)
    v8h = build_code_v8h(request, v8b, v8c, rejected_v8d(v8d), regions)
    assert v8h.status is CodeV8HStatus.REJECTED
    result = build_code_v8i(v8h)
    assert result.status is CodeV8IStatus.REJECTED
    assert result.variants == ()
    assert result.primary_variant_id is None
    assert result.blockers
