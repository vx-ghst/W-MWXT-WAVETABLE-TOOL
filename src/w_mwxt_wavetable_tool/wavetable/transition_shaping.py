from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .continuity import ContinuityStatus, WavetableContinuityReport, analyze_wavetable_continuity
from .models import (
    GenerationMethod,
    SAFE_STORED_MAX,
    SAFE_STORED_MIN,
    USER_POSITION_COUNT,
    WAVETABLE_BUILD_SCHEMA_VERSION,
    WaveBuildMetrics,
    WaveOrigin,
    WaveRole,
    WavetableBuild,
    WavetableBuildRequest,
    WavetableBuildSet,
    WavetableBuildStatus,
    WavetableContractError,
    WavetableSlot,
)

TRANSITION_SHAPING_SCHEMA_VERSION = 1
_PRECISION = 12


def _q(value: float) -> float:
    return round(float(value), _PRECISION)


def _canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _normalized(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise WavetableContractError(f"{name} must be a normalized non-empty string")
    return value


def _entries(values: Sequence[str], *, name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence")
    result = tuple(_normalized(value, name=f"{name} entry") for value in values)
    if not allow_empty and not result:
        raise WavetableContractError(f"{name} must not be empty")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


def _ratio(value: float, *, name: str) -> float:
    checked = float(value)
    if not math.isfinite(checked) or not 0.0 <= checked <= 1.0:
        raise WavetableContractError(f"{name} must be finite and between 0 and 1")
    return checked


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


class TransitionShapingStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


class TransitionShapingAction(str, Enum):
    PRESERVE_PROTECTED = "preserve_protected"
    PRESERVE_KEYFRAME = "preserve_keyframe"
    PRESERVE_EDGE_HOLD = "preserve_edge_hold"
    PRESERVE_TRANSITION = "preserve_transition"
    SMOOTH_TRANSITION = "smooth_transition"


@dataclass(frozen=True, slots=True)
class TransitionShapingPolicy:
    schema_version: int = TRANSITION_SHAPING_SCHEMA_VERSION
    enabled: bool = True
    smoothing_passes: int = 1
    smoothing_strength: float = 0.25
    neighbor_blend: float = 0.12
    maximum_sample_delta: int = 12
    require_non_worsening_continuity: bool = False
    continuity_tolerance: float = 0.02

    def __post_init__(self) -> None:
        if self.schema_version != TRANSITION_SHAPING_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported transition-shaping policy schema version")
        for name in ("enabled", "require_non_worsening_continuity"):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        if (
            isinstance(self.smoothing_passes, bool)
            or not isinstance(self.smoothing_passes, int)
            or not 0 <= self.smoothing_passes <= 4
        ):
            raise WavetableContractError("smoothing_passes must be an integer from 0 to 4")
        _ratio(self.smoothing_strength, name="smoothing_strength")
        _ratio(self.neighbor_blend, name="neighbor_blend")
        if (
            isinstance(self.maximum_sample_delta, bool)
            or not isinstance(self.maximum_sample_delta, int)
            or not 0 <= self.maximum_sample_delta <= 127
        ):
            raise WavetableContractError("maximum_sample_delta must be an integer from 0 to 127")
        tolerance = float(self.continuity_tolerance)
        if not math.isfinite(tolerance) or not 0.0 <= tolerance <= 1.0:
            raise WavetableContractError("continuity_tolerance must be finite and between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "enabled": self.enabled,
            "smoothing_passes": self.smoothing_passes,
            "smoothing_strength": self.smoothing_strength,
            "neighbor_blend": self.neighbor_blend,
            "maximum_sample_delta": self.maximum_sample_delta,
            "require_non_worsening_continuity": self.require_non_worsening_continuity,
            "continuity_tolerance": self.continuity_tolerance,
            "semantic_role": "optional_post_transition_shaping",
            "closes_factory_style_requirement": False,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


DEFAULT_TRANSITION_SHAPING_POLICY = TransitionShapingPolicy()
DISABLED_TRANSITION_SHAPING_POLICY = TransitionShapingPolicy(enabled=False)


@dataclass(frozen=True, slots=True)
class TransitionShapingSlotDecision:
    schema_version: int
    position: int
    action: TransitionShapingAction
    protected: bool
    before_sha256: str
    after_sha256: str
    changed: bool
    maximum_sample_delta: int
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != TRANSITION_SHAPING_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported transition-shaping decision schema version")
        if isinstance(self.position, bool) or not isinstance(self.position, int) or not 0 <= self.position < USER_POSITION_COUNT:
            raise WavetableContractError("position must be an integer in 0..60")
        if not isinstance(self.action, TransitionShapingAction):
            raise WavetableContractError("action must be TransitionShapingAction")
        for name in ("protected", "changed"):
            if not isinstance(getattr(self, name), bool):
                raise WavetableContractError(f"{name} must be boolean")
        _sha256(self.before_sha256, name="before_sha256")
        _sha256(self.after_sha256, name="after_sha256")
        if self.changed != (self.before_sha256 != self.after_sha256):
            raise WavetableContractError("changed flag disagrees with sample hashes")
        if self.protected and self.changed:
            raise WavetableContractError("protected slots cannot be changed")
        if (
            isinstance(self.maximum_sample_delta, bool)
            or not isinstance(self.maximum_sample_delta, int)
            or not 0 <= self.maximum_sample_delta <= 254
        ):
            raise WavetableContractError("maximum_sample_delta is invalid")
        object.__setattr__(self, "evidence", _entries(self.evidence, name="evidence", allow_empty=False))
        _normalized(self.reason, name="reason")

    @property
    def display_position(self) -> int:
        return self.position + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "position": self.position,
            "display_position": self.display_position,
            "action": self.action.value,
            "protected": self.protected,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "changed": self.changed,
            "maximum_sample_delta": self.maximum_sample_delta,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class TransitionShapingVariant:
    schema_version: int
    variant_id: str
    source_variant_sha256: str
    build: WavetableBuild
    continuity: WavetableContinuityReport
    decisions: tuple[TransitionShapingSlotDecision, ...]
    changed_positions: tuple[int, ...]
    objective_score: float
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != TRANSITION_SHAPING_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported transition-shaping variant schema version")
        _normalized(self.variant_id, name="variant_id")
        _sha256(self.source_variant_sha256, name="source_variant_sha256")
        if not isinstance(self.build, WavetableBuild) or self.build.status is not WavetableBuildStatus.COMPLETE:
            raise WavetableContractError("transition-shaping variant requires a complete build")
        if self.build.variant_id != self.variant_id:
            raise WavetableContractError("build variant_id disagrees with transition-shaping variant")
        if not isinstance(self.continuity, WavetableContinuityReport):
            raise WavetableContractError("continuity must be WavetableContinuityReport")
        if self.continuity.build_sha256 != self.build.analysis_sha256:
            raise WavetableContractError("continuity report does not link to transition-shaped build")
        if self.continuity.status is ContinuityStatus.FAIL:
            raise WavetableContractError("transition-shaping variant cannot retain failed continuity")
        decisions = tuple(self.decisions)
        object.__setattr__(self, "decisions", decisions)
        if len(decisions) != USER_POSITION_COUNT:
            raise WavetableContractError("transition-shaping variant requires 61 decisions")
        if tuple(item.position for item in decisions) != tuple(range(USER_POSITION_COUNT)):
            raise WavetableContractError("transition-shaping decisions must use canonical positions")
        changed = tuple(self.changed_positions)
        object.__setattr__(self, "changed_positions", changed)
        if changed != tuple(item.position for item in decisions if item.changed):
            raise WavetableContractError("changed_positions disagree with decisions")
        _ratio(self.objective_score, name="objective_score")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        _normalized(self.reason, name="reason")

    @property
    def source_v8e_variant_sha256(self) -> str:
        """Deprecated compatibility property for the original V8-F schema."""
        return self.source_variant_sha256

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "source_variant_sha256": self.source_variant_sha256,
            "build": self.build.to_dict(),
            "continuity": self.continuity.to_dict(),
            "decisions": [item.to_dict() for item in self.decisions],
            "changed_positions": list(self.changed_positions),
            "display_changed_positions": [item + 1 for item in self.changed_positions],
            "objective_score": self.objective_score,
            "warnings": list(self.warnings),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class TransitionShapingAnalysis:
    schema_version: int
    status: TransitionShapingStatus
    request_sha256: str
    source_analysis_sha256: str
    policy: TransitionShapingPolicy
    applied: bool
    variants: tuple[TransitionShapingVariant, ...]
    primary_variant_id: str | None
    build_set: WavetableBuildSet | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != TRANSITION_SHAPING_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported transition-shaping analysis schema version")
        if not isinstance(self.status, TransitionShapingStatus):
            raise WavetableContractError("status must be TransitionShapingStatus")
        _sha256(self.request_sha256, name="request_sha256")
        _sha256(self.source_analysis_sha256, name="source_analysis_sha256")
        if not isinstance(self.policy, TransitionShapingPolicy):
            raise WavetableContractError("policy must be TransitionShapingPolicy")
        if not isinstance(self.applied, bool):
            raise WavetableContractError("applied must be boolean")
        variants = tuple(self.variants)
        object.__setattr__(self, "variants", variants)
        if any(not isinstance(item, TransitionShapingVariant) for item in variants):
            raise WavetableContractError("variants contain invalid values")
        if len({item.variant_id for item in variants}) != len(variants):
            raise WavetableContractError("transition-shaping variant IDs must be unique")
        if tuple(item.objective_score for item in variants) != tuple(
            sorted((item.objective_score for item in variants), reverse=True)
        ):
            raise WavetableContractError("transition-shaping variants must be ranked by score")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        object.__setattr__(self, "blockers", _entries(self.blockers, name="blockers"))
        _normalized(self.reason, name="reason")
        if self.status is TransitionShapingStatus.COMPLETE:
            if self.blockers:
                raise WavetableContractError("complete transition-shaping analysis cannot contain blockers")
            if not variants or self.primary_variant_id is None or self.build_set is None:
                raise WavetableContractError("complete transition-shaping analysis requires variants")
            if variants[0].variant_id != self.primary_variant_id:
                raise WavetableContractError("primary transition-shaping variant must rank first")
            if self.build_set.primary_variant_id != self.primary_variant_id:
                raise WavetableContractError("build_set primary variant disagrees")
        else:
            if not self.blockers:
                raise WavetableContractError("rejected transition-shaping analysis requires blockers")
            if variants or self.primary_variant_id is not None or self.build_set is not None:
                raise WavetableContractError("rejected transition-shaping analysis cannot expose partial variants")

    @property
    def v8e_analysis_sha256(self) -> str:
        """Deprecated compatibility property for the original V8-F schema."""
        return self.source_analysis_sha256

    @property
    def primary_variant(self) -> TransitionShapingVariant | None:
        return self.variants[0] if self.variants else None

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "request_sha256": self.request_sha256,
            "source_analysis_sha256": self.source_analysis_sha256,
            "policy": self.policy.to_dict(),
            "applied": self.applied,
            "variants": [item.to_dict() for item in self.variants],
            "primary_variant_id": self.primary_variant_id,
            "build_set": None if self.build_set is None else self.build_set.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
            "boundaries": {
                "semantic_role": "optional_post_transition_shaping",
                "closes_factory_style_requirement": False,
                "mutates_protected_keyframes": False,
                "materializes_wctd": False,
                "generates_sysex": False,
                "opens_midi_port": False,
                "transmits_midi": False,
            },
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _protected(slot: WavetableSlot) -> bool:
    return slot.locked or slot.structural or slot.role in {
        WaveRole.ESSENTIAL,
        WaveRole.BREAKPOINT,
        WaveRole.EXTREME,
        WaveRole.STRUCTURAL,
    }


def _smooth(samples: Sequence[int], passes: int, strength: float) -> tuple[float, ...]:
    current = tuple(float(item) for item in samples)
    for _ in range(passes):
        current = tuple(
            (1.0 - strength) * value
            + strength
            * (
                current[(index - 1) % len(current)]
                + 2.0 * value
                + current[(index + 1) % len(current)]
            )
            / 4.0
            for index, value in enumerate(current)
        )
    return current


def _shaped_samples(
    previous_slot: WavetableSlot,
    slot: WavetableSlot,
    next_slot: WavetableSlot,
    policy: TransitionShapingPolicy,
) -> tuple[int, ...]:
    smoothed = _smooth(slot.stored_samples, policy.smoothing_passes, policy.smoothing_strength)
    result: list[int] = []
    for index, (original, value) in enumerate(zip(slot.stored_samples, smoothed)):
        neighbor = 0.5 * (
            previous_slot.stored_samples[index] + next_slot.stored_samples[index]
        )
        target = (1.0 - policy.neighbor_blend) * value + policy.neighbor_blend * neighbor
        delta = max(
            -policy.maximum_sample_delta,
            min(policy.maximum_sample_delta, round(target - original)),
        )
        result.append(max(SAFE_STORED_MIN, min(SAFE_STORED_MAX, original + delta)))
    return tuple(result)


def _shaped_metrics(metrics: WaveBuildMetrics) -> WaveBuildMetrics:
    return replace(
        metrics,
        quality_score=_q(min(1.0, metrics.quality_score + 0.01)),
        stability_score=_q(min(1.0, metrics.stability_score + 0.02)),
        source_fidelity=_q(max(0.0, metrics.source_fidelity - 0.01)),
        xt_compatibility=_q(min(1.0, metrics.xt_compatibility + 0.02)),
        reason="Optional V8-H transition shaping with bounded sample-domain movement.",
    )


def _decision(
    position: int,
    before: WavetableSlot,
    after: WavetableSlot,
    action: TransitionShapingAction,
    protected: bool,
    reason: str,
) -> TransitionShapingSlotDecision:
    delta = max(abs(a - b) for a, b in zip(before.stored_samples, after.stored_samples))
    return TransitionShapingSlotDecision(
        schema_version=TRANSITION_SHAPING_SCHEMA_VERSION,
        position=position,
        action=action,
        protected=protected,
        before_sha256=before.stored_samples_sha256,
        after_sha256=after.stored_samples_sha256,
        changed=before.stored_samples != after.stored_samples,
        maximum_sample_delta=delta,
        evidence=(f"source slot {before.slot_sha256}", f"result slot {after.slot_sha256}"),
        reason=reason,
    )


def _shape_variant(source: object, policy: TransitionShapingPolicy, active: bool) -> TransitionShapingVariant:
    original = getattr(source, "build")
    source_continuity = getattr(source, "continuity")
    source_objective = float(getattr(source, "objective_score"))
    source_warnings = tuple(getattr(source, "warnings"))
    styled_slots: list[WavetableSlot] = []
    decisions: list[TransitionShapingSlotDecision] = []
    for position, slot in enumerate(original.slots):
        protected = _protected(slot)
        if protected:
            styled = slot
            action = TransitionShapingAction.PRESERVE_PROTECTED
            reason = "Protected keyframe preserved byte-for-byte."
        elif not slot.transition:
            styled = slot
            action = (
                TransitionShapingAction.PRESERVE_EDGE_HOLD
                if slot.redundant
                else TransitionShapingAction.PRESERVE_KEYFRAME
            )
            reason = "Non-transition slot preserved byte-for-byte."
        elif not active or policy.smoothing_passes == 0 or policy.maximum_sample_delta == 0:
            styled = slot
            action = TransitionShapingAction.PRESERVE_TRANSITION
            reason = "Transition shaping is inactive or configured as a no-op."
        else:
            previous_slot = original.slots[max(0, position - 1)]
            next_slot = original.slots[min(USER_POSITION_COUNT - 1, position + 1)]
            samples = _shaped_samples(previous_slot, slot, next_slot, policy)
            if samples == slot.stored_samples:
                styled = slot
                action = TransitionShapingAction.PRESERVE_TRANSITION
                reason = "Bounded shaping produced no integer sample change."
            else:
                styled = replace(
                    slot,
                    stored_samples=samples,
                    origin=WaveOrigin.GENERATED_VARIANT,
                    generation_method=GenerationMethod.DETERMINISTIC_VARIANT,
                    metrics=_shaped_metrics(slot.metrics),
                    evidence=tuple(
                        dict.fromkeys(
                            slot.evidence
                            + (f"transition-shaping policy {policy.analysis_sha256}",)
                        )
                    ),
                    reason="Optional transition shaping; provenance and source candidate links preserved.",
                )
                action = TransitionShapingAction.SMOOTH_TRANSITION
                reason = "Mutable transition shaped inside the configured sample-delta bound."
        styled_slots.append(styled)
        decisions.append(_decision(position, slot, styled, action, protected, reason))
    if active:
        styled_build = replace(
            original,
            slots=tuple(styled_slots),
            reason="Optional V8-H transition shaping applied without changing protected keyframes.",
        )
        continuity = analyze_wavetable_continuity(
            styled_build,
            source_continuity.thresholds,
            intentional_break_positions=tuple(
                item.left_position
                for item in source_continuity.transitions
                if item.intentional_break
            ),
        )
    else:
        styled_build = original
        continuity = source_continuity
    if continuity.status is ContinuityStatus.FAIL:
        raise WavetableContractError("transition-shaping result failed mandatory continuity")
    if (
        active
        and policy.require_non_worsening_continuity
        and continuity.mean_continuity_score + policy.continuity_tolerance
        < source_continuity.mean_continuity_score
    ):
        raise WavetableContractError(
            "transition-shaping result exceeded the continuity regression tolerance"
        )
    changed = tuple(item.position for item in decisions if item.changed)
    change_fraction = len(changed) / USER_POSITION_COUNT
    objective = _q(
        0.55 * continuity.mean_continuity_score
        + 0.25 * continuity.minimum_continuity_score
        + 0.15 * source_objective
        + 0.05 * (1.0 - change_fraction)
    )
    return TransitionShapingVariant(
        schema_version=TRANSITION_SHAPING_SCHEMA_VERSION,
        variant_id=styled_build.variant_id,
        source_variant_sha256=getattr(source, "analysis_sha256"),
        build=styled_build,
        continuity=continuity,
        decisions=tuple(decisions),
        changed_positions=changed,
        objective_score=objective,
        warnings=tuple(dict.fromkeys(source_warnings + continuity.warnings)),
        reason="Optional shaping variant ranked with continuity and bounded-change evidence.",
    )


def apply_transition_shaping(
    request: WavetableBuildRequest,
    source_analysis: object,
    policy: TransitionShapingPolicy = DEFAULT_TRANSITION_SHAPING_POLICY,
    *,
    requested: bool | None = None,
) -> TransitionShapingAnalysis:
    """Apply optional shaping to complete V8-E or V8-G builds.

    This operation is deliberately not the Factory Style placement feature.  The
    legacy ``factory_style`` request flag is consulted only when ``requested`` is
    omitted, preserving the V8-F compatibility path.
    """

    if not isinstance(request, WavetableBuildRequest):
        raise WavetableContractError("request must be WavetableBuildRequest")
    if not isinstance(policy, TransitionShapingPolicy):
        raise WavetableContractError("policy must be TransitionShapingPolicy")
    for name in ("request_sha256", "analysis_sha256", "status", "variants", "warnings", "blockers"):
        if not hasattr(source_analysis, name):
            raise WavetableContractError(f"source_analysis is missing {name}")
    if getattr(source_analysis, "request_sha256") != request.analysis_sha256:
        raise WavetableContractError("source analysis does not link to request")
    source_hash = getattr(source_analysis, "analysis_sha256")
    complete = getattr(getattr(source_analysis, "status"), "value", None) == "complete"
    if not complete:
        return TransitionShapingAnalysis(
            schema_version=TRANSITION_SHAPING_SCHEMA_VERSION,
            status=TransitionShapingStatus.REJECTED,
            request_sha256=request.analysis_sha256,
            source_analysis_sha256=source_hash,
            policy=policy,
            applied=False,
            variants=(),
            primary_variant_id=None,
            build_set=None,
            warnings=tuple(getattr(source_analysis, "warnings")),
            blockers=tuple(getattr(source_analysis, "blockers")) or ("source analysis is rejected",),
            reason="Transition shaping rejected the input without partial output.",
        )
    active = policy.enabled and (
        request.policy.factory_style if requested is None else bool(requested)
    )
    built: list[TransitionShapingVariant] = []
    failures: list[str] = []
    for source in getattr(source_analysis, "variants"):
        try:
            built.append(_shape_variant(source, policy, active))
        except WavetableContractError as exc:
            failures.append(f"{getattr(source, 'variant_id')}: {exc}")
    if not built:
        return TransitionShapingAnalysis(
            schema_version=TRANSITION_SHAPING_SCHEMA_VERSION,
            status=TransitionShapingStatus.REJECTED,
            request_sha256=request.analysis_sha256,
            source_analysis_sha256=source_hash,
            policy=policy,
            applied=active,
            variants=(),
            primary_variant_id=None,
            build_set=None,
            warnings=tuple(getattr(source_analysis, "warnings")),
            blockers=tuple(failures) or ("no transition-shaping variant remained valid",),
            reason="Transition shaping rejected all variants without partial builds.",
        )
    built.sort(key=lambda item: (-item.objective_score, item.variant_id, item.analysis_sha256))
    primary_id = built[0].variant_id
    build_set = WavetableBuildSet(
        schema_version=WAVETABLE_BUILD_SCHEMA_VERSION,
        request_sha256=request.analysis_sha256,
        builds=tuple(item.build for item in built),
        primary_variant_id=primary_id,
        reason="Optional transition-shaping build set preserving source-build provenance.",
    )
    return TransitionShapingAnalysis(
        schema_version=TRANSITION_SHAPING_SCHEMA_VERSION,
        status=TransitionShapingStatus.COMPLETE,
        request_sha256=request.analysis_sha256,
        source_analysis_sha256=source_hash,
        policy=policy,
        applied=active,
        variants=tuple(built),
        primary_variant_id=primary_id,
        build_set=build_set,
        warnings=tuple(dict.fromkeys(tuple(getattr(source_analysis, "warnings")) + tuple(failures))),
        blockers=(),
        reason=(
            "Optional transition shaping applied with immutable protected keyframes."
            if active
            else "Transition shaping was disabled; source builds were preserved exactly."
        ),
    )


__all__ = [
    "DEFAULT_TRANSITION_SHAPING_POLICY",
    "DISABLED_TRANSITION_SHAPING_POLICY",
    "TRANSITION_SHAPING_SCHEMA_VERSION",
    "TransitionShapingAction",
    "TransitionShapingAnalysis",
    "TransitionShapingPolicy",
    "TransitionShapingSlotDecision",
    "TransitionShapingStatus",
    "TransitionShapingVariant",
    "apply_transition_shaping",
]
