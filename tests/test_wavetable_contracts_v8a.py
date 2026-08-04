from __future__ import annotations

from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    DEFAULT_INTERPOLATION_METHODS,
    ChronologyConstraint,
    ConstraintStrength,
    GenerationMethod,
    PositionLock,
    ProgressionCurve,
    WavetableBuildPolicy,
    WavetableContractError,
    create_wavetable_build_request,
    default_wavetable_build_policy,
    validate_candidate_inventory,
)

from v8a_helpers import candidate, fixed_tail, ready_preflight, rejected_preflight


def test_default_policy_is_deterministic_61_position_contract() -> None:
    first = default_wavetable_build_policy()
    second = default_wavetable_build_policy()
    assert first.user_position_count == 61
    assert first.requested_variant_count == 1
    assert first.progression_curve is ProgressionCurve.ADAPTIVE
    assert first.allowed_interpolation_methods == DEFAULT_INTERPOLATION_METHODS
    assert first.analysis_sha256 == second.analysis_sha256


def test_default_policy_accepts_explicit_future_controls() -> None:
    result = default_wavetable_build_policy(
        requested_variant_count=4,
        progression_curve=ProgressionCurve.EXPONENTIAL,
        allow_mixed_provenance=False,
        preserve_chronology=False,
        allow_intentional_breaks=True,
        factory_style=True,
    )
    assert result.requested_variant_count == 4
    assert result.factory_style is True
    assert result.allow_intentional_breaks is True


def test_candidate_inventory_requires_at_least_one_candidate() -> None:
    with pytest.raises(WavetableContractError, match="must not be empty"):
        validate_candidate_inventory(())


def test_candidate_inventory_requires_unique_ids() -> None:
    with pytest.raises(WavetableContractError, match="IDs must be unique"):
        validate_candidate_inventory((candidate(), candidate(offset=1)))


def test_candidate_inventory_allows_duplicate_wave_content_for_later_deduplication() -> None:
    first = candidate("first")
    second = candidate("second")
    result = validate_candidate_inventory((first, second))
    assert result[0].stored_samples_sha256 == result[1].stored_samples_sha256


def test_request_links_ready_preflight_candidate_inventory_and_fixed_tail() -> None:
    candidates = (candidate("real"), candidate("reconstructed", source_index=1, offset=1))
    result = create_wavetable_build_request(ready_preflight(), candidates, fixed_tail())
    assert result.preflight_analysis_sha256 == ready_preflight().analysis_sha256
    assert result.candidate_count == 2
    assert result.candidate_inventory_sha256
    assert result.fixed_tail.references == (1, 2, 3)
    assert result.to_dict()["selected_mode"] == "hybrid"
    assert result.to_dict()["boundaries"] if "boundaries" in result.to_dict() else True


def test_request_rejects_non_ready_preflight_without_fallback() -> None:
    with pytest.raises(WavetableContractError, match="no hidden fallback"):
        create_wavetable_build_request(
            rejected_preflight(), (candidate(), candidate("second", offset=1)), fixed_tail()
        )


def test_request_rejects_candidate_count_mismatch() -> None:
    with pytest.raises(WavetableContractError, match="count does not match"):
        create_wavetable_build_request(ready_preflight(repaired_wave_count=3), (candidate(),), fixed_tail())


def test_request_rejects_missing_preflight_links() -> None:
    broken = SimpleNamespace(status=SimpleNamespace(value="ready"))
    with pytest.raises(WavetableContractError, match="required V8-0F links"):
        create_wavetable_build_request(broken, (candidate(),), fixed_tail())


def test_request_rejects_ready_preflight_without_selected_mode() -> None:
    preflight = ready_preflight(repaired_wave_count=1)
    preflight.decision_plan.selected_mode = None
    with pytest.raises(WavetableContractError, match="selected_mode"):
        create_wavetable_build_request(preflight, (candidate(),), fixed_tail())


def test_request_canonicalizes_sequence_inputs() -> None:
    candidates = [candidate("first"), candidate("second", source_index=1, offset=1)]
    result = create_wavetable_build_request(
        ready_preflight(),
        candidates,
        fixed_tail(),
        warnings=["warning"],
    )
    assert isinstance(result.candidates, tuple)
    assert isinstance(result.warnings, tuple)


def test_request_rejects_unknown_position_lock_candidate() -> None:
    with pytest.raises(WavetableContractError, match="unknown candidate"):
        create_wavetable_build_request(
            ready_preflight(repaired_wave_count=1),
            (candidate(),),
            fixed_tail(),
            position_locks=(PositionLock(0, "unknown", ConstraintStrength.REQUIRED, "bad"),),
        )


def test_request_rejects_duplicate_lock_positions() -> None:
    candidates = (candidate("first"), candidate("second", source_index=1, offset=1))
    locks = (
        PositionLock(0, "first", ConstraintStrength.REQUIRED, "first"),
        PositionLock(0, "second", ConstraintStrength.PREFERENCE, "second"),
    )
    with pytest.raises(WavetableContractError, match="unique positions"):
        create_wavetable_build_request(ready_preflight(), candidates, fixed_tail(), position_locks=locks)


def test_request_rejects_required_chronology_cycle() -> None:
    candidates = (candidate("first"), candidate("second", source_index=1, offset=1))
    chronology = (
        ChronologyConstraint("first", "second", ConstraintStrength.REQUIRED, "forward"),
        ChronologyConstraint("second", "first", ConstraintStrength.REQUIRED, "backward"),
    )
    with pytest.raises(WavetableContractError, match="cycle"):
        create_wavetable_build_request(
            ready_preflight(), candidates, fixed_tail(), chronology_constraints=chronology
        )


def test_request_allows_preference_chronology_cycle_for_variant_comparison() -> None:
    candidates = (candidate("first"), candidate("second", source_index=1, offset=1))
    chronology = (
        ChronologyConstraint("first", "second", ConstraintStrength.PREFERENCE, "forward"),
        ChronologyConstraint("second", "first", ConstraintStrength.PREFERENCE, "backward"),
    )
    result = create_wavetable_build_request(
        ready_preflight(), candidates, fixed_tail(), chronology_constraints=chronology
    )
    assert len(result.chronology_constraints) == 2


def test_request_rejects_required_lock_chronology_contradiction() -> None:
    candidates = (candidate("first"), candidate("second", source_index=1, offset=1))
    locks = (
        PositionLock(40, "first", ConstraintStrength.REQUIRED, "late"),
        PositionLock(20, "second", ConstraintStrength.REQUIRED, "early"),
    )
    chronology = (
        ChronologyConstraint("first", "second", ConstraintStrength.REQUIRED, "must precede"),
    )
    with pytest.raises(WavetableContractError, match="contradict"):
        create_wavetable_build_request(
            ready_preflight(), candidates, fixed_tail(),
            position_locks=locks, chronology_constraints=chronology,
        )


def test_request_detects_transitive_lock_chronology_contradiction() -> None:
    candidates = (
        candidate("first"),
        candidate("middle", source_index=1, offset=1),
        candidate("last", source_index=2, offset=2),
    )
    locks = (
        PositionLock(50, "first", ConstraintStrength.REQUIRED, "late"),
        PositionLock(10, "last", ConstraintStrength.REQUIRED, "early"),
    )
    chronology = (
        ChronologyConstraint("first", "middle", ConstraintStrength.REQUIRED, "one"),
        ChronologyConstraint("middle", "last", ConstraintStrength.REQUIRED, "two"),
    )
    with pytest.raises(WavetableContractError, match="contradict"):
        create_wavetable_build_request(
            ready_preflight(repaired_wave_count=3), candidates, fixed_tail(),
            position_locks=locks, chronology_constraints=chronology,
        )


def test_request_allows_preference_lock_conflict_for_future_solver() -> None:
    candidates = (candidate("first"), candidate("second", source_index=1, offset=1))
    locks = (
        PositionLock(40, "first", ConstraintStrength.PREFERENCE, "late preference"),
        PositionLock(20, "second", ConstraintStrength.REQUIRED, "early required"),
    )
    chronology = (
        ChronologyConstraint("first", "second", ConstraintStrength.REQUIRED, "must precede"),
    )
    result = create_wavetable_build_request(
        ready_preflight(), candidates, fixed_tail(),
        position_locks=locks, chronology_constraints=chronology,
    )
    assert len(result.position_locks) == 2


def test_request_rejects_mixed_provenance_when_policy_forbids_it() -> None:
    candidates = (
        candidate("real"),
        candidate(
            "reconstructed",
            origin=__import__("w_mwxt_wavetable_tool.wavetable", fromlist=["WaveOrigin"]).WaveOrigin.REPAIRED_RECONSTRUCTED,
            generation_method=GenerationMethod.AUTO_REPAIR,
            source_index=1,
            offset=1,
        ),
    )
    policy = default_wavetable_build_policy(allow_mixed_provenance=False)
    with pytest.raises(WavetableContractError, match="mixed"):
        create_wavetable_build_request(ready_preflight(), candidates, fixed_tail(), policy=policy)


def test_request_hash_and_json_are_deterministic() -> None:
    candidates = (candidate("first"), candidate("second", source_index=1, offset=1))
    first = create_wavetable_build_request(ready_preflight(), candidates, fixed_tail())
    second = create_wavetable_build_request(ready_preflight(), candidates, fixed_tail())
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.to_json() == second.to_json()
