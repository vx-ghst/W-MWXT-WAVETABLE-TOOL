from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import math

import pytest

from w_mwxt_wavetable_tool.wavetable import (
    FIXED_TAIL_POSITIONS,
    SAFE_STORED_MAX,
    SAFE_STORED_MIN,
    USER_POSITION_COUNT,
    USER_POSITION_FIRST,
    USER_POSITION_LAST,
    WCTD_POSITION_COUNT,
    ChronologyConstraint,
    ConstraintStrength,
    FixedTailContract,
    GenerationMethod,
    PositionLock,
    ProgressionCurve,
    WaveBuildMetrics,
    WaveOrigin,
    WaveRole,
    WavetableBuild,
    WavetableBuildPolicy,
    WavetableBuildSet,
    WavetableBuildStatus,
    WavetableCandidate,
    WavetableContractError,
    WavetableSlot,
    reconstruct_xt_cycle,
    stored_samples_sha256,
)

from v8a_helpers import HASH_A, HASH_B, HASH_C, candidate, complete_build, fixed_tail, metrics, samples, slot


def test_canonical_xt_position_constants() -> None:
    assert USER_POSITION_COUNT == 61
    assert WCTD_POSITION_COUNT == 64
    assert USER_POSITION_FIRST == 0
    assert USER_POSITION_LAST == 60
    assert FIXED_TAIL_POSITIONS == (61, 62, 63)
    assert (SAFE_STORED_MIN, SAFE_STORED_MAX) == (-127, 127)


def test_reconstruct_xt_cycle_uses_reverse_negate() -> None:
    stored = tuple(range(-32, 32))
    reconstructed = reconstruct_xt_cycle(stored)
    assert len(reconstructed) == 128
    assert reconstructed[:64] == stored
    assert reconstructed[64:] == tuple(-value for value in reversed(stored))


@pytest.mark.parametrize("bad", [(-128,) * 64, (128,) * 64, (0,) * 63, (0,) * 65])
def test_stored_sample_contract_rejects_invalid_vectors(bad: tuple[int, ...]) -> None:
    with pytest.raises(WavetableContractError):
        reconstruct_xt_cycle(bad)


@pytest.mark.parametrize("bad", [(False,) * 64, (0.0,) * 64, ("0",) * 64])
def test_stored_sample_contract_requires_integer_samples(bad: tuple[object, ...]) -> None:
    with pytest.raises(WavetableContractError):
        stored_samples_sha256(bad)  # type: ignore[arg-type]


def test_stored_sample_hash_is_deterministic_and_sensitive() -> None:
    assert stored_samples_sha256(samples()) == stored_samples_sha256(list(samples()))
    assert stored_samples_sha256(samples()) != stored_samples_sha256(samples(1))


@pytest.mark.parametrize("name", [
    "quality_score", "usefulness_score", "stability_score", "harmonic_richness",
    "brightness", "bass_power", "source_fidelity", "xt_compatibility", "perceptual_novelty",
])
@pytest.mark.parametrize("bad", [-0.001, 1.001, math.nan, math.inf])
def test_metrics_reject_out_of_range_and_non_finite(name: str, bad: float) -> None:
    values = metrics().to_dict()
    values.pop("reason")
    values[name] = bad
    with pytest.raises((WavetableContractError, ValueError)):
        WaveBuildMetrics(**values, reason="bad metrics")


def test_metrics_hash_and_json_are_deterministic() -> None:
    first = metrics()
    second = metrics()
    assert first.analysis_sha256 == second.analysis_sha256
    assert json.dumps(first.to_dict(), sort_keys=True, allow_nan=False)


@pytest.mark.parametrize(
    ("origin", "method"),
    [
        (WaveOrigin.REAL_CYCLE, GenerationMethod.SOURCE_CYCLE),
        (WaveOrigin.RECONSTRUCTED_CYCLE, GenerationMethod.SPECTRAL_RECONSTRUCTION),
        (WaveOrigin.REPAIRED_REAL, GenerationMethod.AUTO_REPAIR),
        (WaveOrigin.REPAIRED_RECONSTRUCTED, GenerationMethod.AUTO_REPAIR),
        (WaveOrigin.GENERATED_VARIANT, GenerationMethod.DETERMINISTIC_VARIANT),
        (WaveOrigin.INTERPOLATED_TRANSITION, GenerationMethod.PERCEPTUAL_INTERPOLATION),
    ],
)
def test_candidate_accepts_canonical_origin_method_pairs(origin: WaveOrigin, method: GenerationMethod) -> None:
    result = candidate(origin=origin, generation_method=method)
    assert result.origin is origin
    assert result.generation_method is method


@pytest.mark.parametrize(
    ("origin", "method"),
    [
        (WaveOrigin.REAL_CYCLE, GenerationMethod.AUTO_REPAIR),
        (WaveOrigin.RECONSTRUCTED_CYCLE, GenerationMethod.SOURCE_CYCLE),
        (WaveOrigin.REPAIRED_REAL, GenerationMethod.SOURCE_CYCLE),
        (WaveOrigin.GENERATED_VARIANT, GenerationMethod.SPECTRAL_RECONSTRUCTION),
        (WaveOrigin.INTERPOLATED_TRANSITION, GenerationMethod.AUTO_REPAIR),
    ],
)
def test_candidate_rejects_inconsistent_origin_method_pairs(origin: WaveOrigin, method: GenerationMethod) -> None:
    with pytest.raises(WavetableContractError, match="inconsistent"):
        candidate(origin=origin, generation_method=method)


def test_candidate_rejects_fixed_reference_origin() -> None:
    with pytest.raises(WavetableContractError):
        candidate(origin=WaveOrigin.FIXED_REFERENCE, generation_method=GenerationMethod.FIXED_REFERENCE)


def test_candidate_serializes_complete_metadata_and_hashes() -> None:
    result = candidate()
    payload = result.to_dict()
    assert payload["candidate_id"] == "candidate-01"
    assert payload["stored_samples_sha256"] == result.stored_samples_sha256
    assert payload["reconstructed_samples_sha256"] == result.reconstructed_samples_sha256
    assert payload["candidate_sha256"] == result.candidate_sha256
    assert payload["is_real"] is True
    assert payload["is_reconstructed"] is False


def test_candidate_sequences_are_canonical_immutable_tuples() -> None:
    result = WavetableCandidate(
        schema_version=1,
        candidate_id="candidate-list",
        source_artifact_sha256=HASH_A,
        origin=WaveOrigin.REPAIRED_REAL,
        generation_method=GenerationMethod.AUTO_REPAIR,
        stored_samples=list(samples()),
        metrics=metrics(),
        source_time_seconds=0.0,
        source_index=0,
        structural_eligible=True,
        evidence=["one"],
        reason="Canonicalized.",
    )
    assert isinstance(result.stored_samples, tuple)
    assert isinstance(result.evidence, tuple)
    with pytest.raises(FrozenInstanceError):
        result.reason = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("bad", [-1, 1.5, True, "1"])
def test_candidate_rejects_invalid_source_index(bad: object) -> None:
    kwargs = candidate().to_dict()
    del kwargs["candidate_sha256"]
    del kwargs["stored_samples_sha256"]
    del kwargs["reconstructed_samples_sha256"]
    del kwargs["is_real"]
    del kwargs["is_reconstructed"]
    del kwargs["is_interpolated"]
    kwargs["origin"] = WaveOrigin(kwargs["origin"])
    kwargs["generation_method"] = GenerationMethod(kwargs["generation_method"])
    kwargs["metrics"] = metrics()
    kwargs["stored_samples"] = samples()
    kwargs["source_index"] = bad
    with pytest.raises(WavetableContractError):
        WavetableCandidate(**kwargs)


def test_fixed_tail_records_positions_61_to_63() -> None:
    result = fixed_tail()
    assert result.to_dict()["positions"] == [61, 62, 63]
    assert len(result.analysis_sha256) == 64


@pytest.mark.parametrize("references", [(1, 2), (1, 2, 3, 4), (1, 2, 0xFFFF), (-1, 2, 3), (1.0, 2, 3)])
def test_fixed_tail_rejects_invalid_references(references: tuple[object, ...]) -> None:
    with pytest.raises(WavetableContractError):
        FixedTailContract(1, HASH_B, references, "Invalid tail")  # type: ignore[arg-type]


@pytest.mark.parametrize("position", [-1, 61, 1.5, True])
def test_position_lock_only_targets_integer_user_positions(position: object) -> None:
    with pytest.raises(WavetableContractError):
        PositionLock(position, "candidate-01", ConstraintStrength.REQUIRED, "lock")  # type: ignore[arg-type]


def test_constraint_models_serialize_strength_and_display_position() -> None:
    lock = PositionLock(0, "candidate-01", ConstraintStrength.REQUIRED, "First wave")
    chronology = ChronologyConstraint(
        "candidate-01", "candidate-02", ConstraintStrength.PREFERENCE, "Order"
    )
    assert lock.to_dict()["display_position"] == 1
    assert chronology.to_dict()["strength"] == "preference"


def test_policy_requires_exactly_61_user_positions() -> None:
    with pytest.raises(WavetableContractError):
        WavetableBuildPolicy(
            1, 60, 1, ProgressionCurve.LINEAR,
            (GenerationMethod.WAVEFORM_INTERPOLATION,), True, True, False, False, "bad"
        )


@pytest.mark.parametrize("count", [0, 17, True, 1.5])
def test_policy_rejects_invalid_variant_counts(count: object) -> None:
    with pytest.raises(WavetableContractError):
        WavetableBuildPolicy(
            1, 61, count, ProgressionCurve.LINEAR,
            (GenerationMethod.WAVEFORM_INTERPOLATION,), True, True, False, False, "bad"
        )  # type: ignore[arg-type]


def test_policy_requires_only_unique_interpolation_methods() -> None:
    with pytest.raises(WavetableContractError):
        WavetableBuildPolicy(
            1, 61, 1, ProgressionCurve.LINEAR,
            (GenerationMethod.AUTO_REPAIR,), True, True, False, False, "bad"
        )
    with pytest.raises(WavetableContractError):
        WavetableBuildPolicy(
            1, 61, 1, ProgressionCurve.LINEAR,
            (GenerationMethod.WAVEFORM_INTERPOLATION, GenerationMethod.WAVEFORM_INTERPOLATION),
            True, True, False, False, "bad"
        )


def test_slot_contract_serializes_required_per_wave_metadata() -> None:
    result = slot(0, role=WaveRole.ESSENTIAL, structural=True)
    payload = result.to_dict()
    assert payload["display_position"] == 1
    assert payload["role"] == "essential"
    assert payload["structural"] is True
    assert payload["metrics"]["quality_score"] == result.metrics.quality_score
    assert len(payload["slot_sha256"]) == 64


def test_transition_slot_requires_two_sources_and_interpolation_method() -> None:
    with pytest.raises(WavetableContractError):
        slot(
            1,
            role=WaveRole.TRANSITION,
            origin=WaveOrigin.INTERPOLATED_TRANSITION,
            method=GenerationMethod.WAVEFORM_INTERPOLATION,
            candidate_ids=("candidate-01",),
        )
    result = slot(
        1,
        role=WaveRole.TRANSITION,
        origin=WaveOrigin.INTERPOLATED_TRANSITION,
        method=GenerationMethod.WAVEFORM_INTERPOLATION,
        candidate_ids=("candidate-01", "candidate-02"),
    )
    assert result.transition is True


def test_complete_build_requires_canonical_61_slots() -> None:
    result = complete_build()
    assert len(result.slots) == 61
    assert result.structural_positions == (0, 30)
    assert result.essential_positions == (0,)
    assert result.to_dict()["boundaries"]["sysex_generated"] is False


def test_complete_build_rejects_missing_slot() -> None:
    valid = complete_build()
    with pytest.raises(WavetableContractError):
        WavetableBuild(
            1, "0.7.0", HASH_A, HASH_C, "short", WavetableBuildStatus.COMPLETE,
            valid.slots[:-1], fixed_tail(), (), (), "bad"
        )


def test_rejected_build_requires_blockers_and_no_slots() -> None:
    result = WavetableBuild(
        1, "0.7.0", HASH_A, HASH_C, "rejected", WavetableBuildStatus.REJECTED,
        (), fixed_tail(), ("Infeasible required lock.",), (), "Rejected explicitly."
    )
    assert result.status is WavetableBuildStatus.REJECTED
    with pytest.raises(WavetableContractError):
        WavetableBuild(
            1, "0.7.0", HASH_A, HASH_C, "bad", WavetableBuildStatus.REJECTED,
            (), fixed_tail(), (), (), "bad"
        )


def test_build_set_requires_unique_variants_and_complete_primary() -> None:
    first = complete_build("first")
    second = complete_build("second")
    result = WavetableBuildSet(1, HASH_A, [first, second], "first", "Variants")
    assert isinstance(result.builds, tuple)
    assert result.primary_variant_id == "first"
    with pytest.raises(WavetableContractError):
        WavetableBuildSet(1, HASH_A, (first, first), "first", "duplicates")


def test_build_and_build_set_json_are_deterministic() -> None:
    build = complete_build()
    build_set = WavetableBuildSet(1, HASH_A, (build,), build.variant_id, "one")
    assert build.to_json() == build.to_json()
    assert build_set.to_json() == build_set.to_json()
    json.loads(build.to_json())
    json.loads(build_set.to_json())
