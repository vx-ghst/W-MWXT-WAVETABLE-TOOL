from __future__ import annotations

from typing import Any, Sequence

from ..version import __version__
from .models import (
    ChronologyConstraint,
    FixedTailContract,
    GenerationMethod,
    PositionLock,
    ProgressionCurve,
    WavetableBuildPolicy,
    WavetableBuildRequest,
    WavetableCandidate,
    WavetableContractError,
    WAVETABLE_BUILD_SCHEMA_VERSION,
    USER_POSITION_COUNT,
)

DEFAULT_INTERPOLATION_METHODS = (
    GenerationMethod.WAVEFORM_INTERPOLATION,
    GenerationMethod.PHASE_AWARE_INTERPOLATION,
    GenerationMethod.SPECTRAL_INTERPOLATION,
    GenerationMethod.HARMONIC_INTERPOLATION,
    GenerationMethod.PERCEPTUAL_INTERPOLATION,
)


def default_wavetable_build_policy(
    *,
    requested_variant_count: int = 1,
    progression_curve: ProgressionCurve = ProgressionCurve.ADAPTIVE,
    allow_mixed_provenance: bool = True,
    preserve_chronology: bool = True,
    allow_intentional_breaks: bool = False,
    factory_style: bool = False,
) -> WavetableBuildPolicy:
    return WavetableBuildPolicy(
        schema_version=WAVETABLE_BUILD_SCHEMA_VERSION,
        user_position_count=USER_POSITION_COUNT,
        requested_variant_count=requested_variant_count,
        progression_curve=progression_curve,
        allowed_interpolation_methods=DEFAULT_INTERPOLATION_METHODS,
        allow_mixed_provenance=allow_mixed_provenance,
        preserve_chronology=preserve_chronology,
        allow_intentional_breaks=allow_intentional_breaks,
        factory_style=factory_style,
        reason=(
            "The default contract requests one deterministic 61-position build, "
            "preserves chronology where relevant, and permits explainable mixed provenance."
        ),
    )


def validate_candidate_inventory(
    candidates: Sequence[WavetableCandidate],
) -> tuple[WavetableCandidate, ...]:
    result = tuple(candidates)
    if not result:
        raise WavetableContractError("candidate inventory must not be empty")
    candidate_ids = tuple(candidate.candidate_id for candidate in result)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise WavetableContractError("candidate inventory IDs must be unique")
    candidate_hashes = tuple(candidate.candidate_sha256 for candidate in result)
    if len(candidate_hashes) != len(result):
        raise WavetableContractError("candidate inventory hash calculation failed")
    return result


def create_wavetable_build_request(
    preflight: Any,
    candidates: Sequence[WavetableCandidate],
    fixed_tail: FixedTailContract,
    *,
    policy: WavetableBuildPolicy | None = None,
    position_locks: Sequence[PositionLock] = (),
    chronology_constraints: Sequence[ChronologyConstraint] = (),
    warnings: Sequence[str] = (),
    tool_version: str = __version__,
) -> WavetableBuildRequest:
    """Create the immutable V8-A request contract from a ready V8-0F preflight.

    This function validates provenance, candidate count and constraints. It does
    not select, order, interpolate, materialize WCTD, allocate XT memory, build
    SysEx, open MIDI, or transmit anything.
    """

    status_object = getattr(preflight, "status", None)
    status = str(getattr(status_object, "value", status_object))
    if status != "ready":
        raise WavetableContractError(
            "CODE V8 requires a ready CODE V8-0F preflight; rejected sources have no hidden fallback"
        )
    preflight_hash = getattr(preflight, "analysis_sha256", None)
    source_chain = getattr(preflight, "source_chain", None)
    decision_plan = getattr(preflight, "decision_plan", None)
    if source_chain is None or decision_plan is None or not isinstance(preflight_hash, str):
        raise WavetableContractError("preflight does not expose the required V8-0F links")

    inventory = validate_candidate_inventory(candidates)
    expected_count = getattr(decision_plan, "repaired_wave_count", None)
    if expected_count is not None and int(expected_count) != len(inventory):
        raise WavetableContractError(
            "candidate inventory count does not match the V8-0F repaired-wave count"
        )
    selected_mode = getattr(decision_plan, "selected_mode", None)
    selected_profile = getattr(decision_plan, "selected_profile", None)
    if selected_mode is None:
        raise WavetableContractError("ready preflight must expose selected_mode")
    if not isinstance(selected_profile, str) or not selected_profile:
        raise WavetableContractError("ready preflight must expose selected_profile")

    return WavetableBuildRequest(
        schema_version=WAVETABLE_BUILD_SCHEMA_VERSION,
        tool_version=tool_version,
        preflight_analysis_sha256=preflight_hash,
        sample_rate=int(getattr(source_chain, "sample_rate")),
        sample_count=int(getattr(source_chain, "sample_count")),
        sample_sha256=str(getattr(source_chain, "sample_sha256")),
        selected_mode=str(selected_mode),
        selected_profile=selected_profile,
        candidates=inventory,
        fixed_tail=fixed_tail,
        policy=default_wavetable_build_policy() if policy is None else policy,
        position_locks=tuple(position_locks),
        chronology_constraints=tuple(chronology_constraints),
        warnings=tuple(warnings),
        reason=(
            "The request links one ready pre-V8 analysis to a deterministic candidate inventory, "
            "fixed-tail contract and explicit future selection/placement constraints."
        ),
    )
