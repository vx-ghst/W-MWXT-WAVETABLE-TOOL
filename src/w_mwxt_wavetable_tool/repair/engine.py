from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from typing import Sequence

import numpy as np

from ..errors import AnalysisError
from .actions import apply_repair_action
from .detectors import detect_wave_defects, measure_repair_wave
from .models import (
    AutoRepairResult,
    AutoRepairSequenceEntry,
    AutoRepairSequenceResult,
    RepairActionRecord,
    RepairActionStatus,
    RepairComparison,
    RepairContext,
    RepairDefect,
    RepairFinding,
    RepairPolicy,
    RepairPolicySet,
    RepairThresholds,
    _sample_hash,
)
from .policy import build_repair_policy_set


_ACTION_ORDER = (
    RepairDefect.CYCLE_LENGTH,
    RepairDefect.DC_OFFSET,
    RepairDefect.CLIPPING,
    RepairDefect.POLARITY_INVERSION,
    RepairDefect.ZERO_CROSSING,
    RepairDefect.PHASE_INVERSION,
    RepairDefect.PARASITIC_NOISE,
    RepairDefect.FUNDAMENTAL_LOSS,
    RepairDefect.SPECTRAL_JUMP,
    RepairDefect.INTER_WAVE_LEVEL_MISMATCH,
    RepairDefect.REDUNDANT_WAVE,
    RepairDefect.EXCESSIVE_ALIASING,
    RepairDefect.AMPLITUDE_INCONSISTENCY,
    RepairDefect.START_END_MISMATCH,
    RepairDefect.LOOP_DISCONTINUITY,
    RepairDefect.DERIVATIVE_DISCONTINUITY,
    RepairDefect.PITCH_ESTIMATE,
)


def _canonical_hash(payload: dict[str, object]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


def _validate(samples: Sequence[float]) -> tuple[float, ...]:
    result = tuple(float(value) for value in samples)
    array = np.asarray(result, dtype=np.float64)
    if array.ndim != 1 or array.size < 2:
        raise AnalysisError("Auto Repair input must contain at least two samples")
    if not np.all(np.isfinite(array)):
        raise AnalysisError("Auto Repair input contains NaN or infinite values")
    if float(np.max(np.abs(array))) > 1.0 + 1.0e-12:
        raise AnalysisError("Auto Repair input exceeds normalized range [-1, 1]")
    return result


def _finding_map(findings: tuple[RepairFinding, ...]) -> dict[RepairDefect, RepairFinding]:
    return {finding.defect: finding for finding in findings}


def _risk(findings: tuple[RepairFinding, ...]) -> float:
    values = tuple(
        finding.score
        for finding in findings
        if finding.evaluated and finding.detected
    )
    if not values:
        return 0.0
    return float(sum(values) / len(RepairDefect))


def _improvement(before: RepairFinding, after: RepairFinding) -> float:
    if not before.detected:
        return 0.0
    if not after.evaluated:
        return 0.0
    return float(min(1.0, max(0.0, before.score - after.score)))


def _context_after_pitch(
    context: RepairContext,
    corrected_pitch_hz: float | None,
) -> RepairContext:
    if corrected_pitch_hz is None:
        return context
    return replace(context, detected_pitch_hz=corrected_pitch_hz)


def _action_record_without_change(
    finding: RepairFinding,
    policy: RepairPolicy,
    status: RepairActionStatus,
    samples: tuple[float, ...],
    *,
    warning: str | None = None,
    reason: str,
) -> RepairActionRecord:
    digest = _sample_hash(samples)
    return RepairActionRecord(
        defect=finding.defect,
        policy=policy,
        action=finding.recommended_action,
        status=status,
        before_samples_sha256=digest,
        candidate_samples_sha256=digest,
        changed=False,
        metadata_changed=False,
        parameters=(),
        improvement=0.0,
        warnings=() if warning is None else (warning,),
        reason=reason,
    )


def auto_repair_wave(
    samples: Sequence[float],
    *,
    context: RepairContext | None = None,
    thresholds: RepairThresholds | None = None,
    policy_set: RepairPolicySet | None = None,
) -> AutoRepairResult:
    source = _validate(samples)
    selected_context = RepairContext() if context is None else context
    selected_thresholds = RepairThresholds() if thresholds is None else thresholds
    selected_policy_set = (
        build_repair_policy_set() if policy_set is None else policy_set
    )

    findings = detect_wave_defects(
        source,
        context=selected_context,
        thresholds=selected_thresholds,
    )
    before_map = _finding_map(findings)

    selected_samples = source
    candidate_samples = source
    selected_pitch = selected_context.detected_pitch_hz
    candidate_pitch = selected_context.detected_pitch_hz
    records: dict[RepairDefect, RepairActionRecord] = {}
    warnings: list[str] = []

    for defect in _ACTION_ORDER:
        finding = before_map[defect]
        policy = selected_policy_set.policy_for(defect)
        record_source = (
            candidate_samples if policy is RepairPolicy.COMPARE else selected_samples
        )

        if not finding.detected:
            records[defect] = _action_record_without_change(
                finding,
                policy,
                RepairActionStatus.NOT_REQUIRED,
                record_source,
                reason=(
                    "The detector did not request this action."
                    if finding.evaluated
                    else "The detector lacked the context required to evaluate this defect."
                ),
            )
            continue

        if policy is RepairPolicy.IGNORE:
            records[defect] = _action_record_without_change(
                finding,
                policy,
                RepairActionStatus.IGNORED,
                selected_samples,
                reason="The detected defect was explicitly ignored.",
            )
            continue

        if policy is RepairPolicy.PRESERVE:
            records[defect] = _action_record_without_change(
                finding,
                policy,
                RepairActionStatus.PRESERVED,
                selected_samples,
                reason="The detected defect was explicitly preserved as intentional material.",
            )
            continue

        if not finding.auto_safe:
            warning = (
                f"{defect.value} requires review because no deterministic safe action "
                "is available with the supplied context."
            )
            warnings.append(warning)
            records[defect] = _action_record_without_change(
                finding,
                policy,
                RepairActionStatus.REVIEW_REQUIRED,
                record_source,
                warning=warning,
                reason="The selected policy requested treatment, but the detector did not authorize automatic execution.",
            )
            continue

        if policy is RepairPolicy.AUTO:
            before_samples = selected_samples
            application = apply_repair_action(
                selected_samples,
                finding,
                context=_context_after_pitch(selected_context, selected_pitch),
            )
            selected_samples = application.samples
            if application.corrected_pitch_hz is not None:
                selected_pitch = application.corrected_pitch_hz

            candidate_application = apply_repair_action(
                candidate_samples,
                finding,
                context=_context_after_pitch(selected_context, candidate_pitch),
            )
            candidate_samples = candidate_application.samples
            if candidate_application.corrected_pitch_hz is not None:
                candidate_pitch = candidate_application.corrected_pitch_hz

            after_findings = detect_wave_defects(
                selected_samples,
                context=_context_after_pitch(selected_context, selected_pitch),
                thresholds=selected_thresholds,
            )
            after_finding = _finding_map(after_findings)[defect]
            record = RepairActionRecord(
                defect=defect,
                policy=policy,
                action=finding.recommended_action,
                status=RepairActionStatus.APPLIED,
                before_samples_sha256=_sample_hash(before_samples),
                candidate_samples_sha256=_sample_hash(selected_samples),
                changed=_sample_hash(before_samples) != _sample_hash(selected_samples),
                metadata_changed=(
                    application.corrected_pitch_hz is not None
                    and application.corrected_pitch_hz != selected_context.detected_pitch_hz
                ),
                parameters=application.parameters,
                improvement=(
                    1.0
                    if defect is RepairDefect.PITCH_ESTIMATE
                    and application.corrected_pitch_hz is not None
                    else _improvement(finding, after_finding)
                ),
                warnings=application.warnings,
                reason=application.reason,
            )
            records[defect] = record
            warnings.extend(application.warnings)
            continue

        if policy is RepairPolicy.COMPARE:
            before_samples = candidate_samples
            application = apply_repair_action(
                candidate_samples,
                finding,
                context=_context_after_pitch(selected_context, candidate_pitch),
            )
            candidate_samples = application.samples
            if application.corrected_pitch_hz is not None:
                candidate_pitch = application.corrected_pitch_hz
            after_findings = detect_wave_defects(
                candidate_samples,
                context=_context_after_pitch(selected_context, candidate_pitch),
                thresholds=selected_thresholds,
            )
            after_finding = _finding_map(after_findings)[defect]
            record = RepairActionRecord(
                defect=defect,
                policy=policy,
                action=finding.recommended_action,
                status=RepairActionStatus.PREVIEWED,
                before_samples_sha256=_sample_hash(before_samples),
                candidate_samples_sha256=_sample_hash(candidate_samples),
                changed=_sample_hash(before_samples) != _sample_hash(candidate_samples),
                metadata_changed=(
                    application.corrected_pitch_hz is not None
                    and application.corrected_pitch_hz != selected_context.detected_pitch_hz
                ),
                parameters=application.parameters,
                improvement=(
                    1.0
                    if defect is RepairDefect.PITCH_ESTIMATE
                    and application.corrected_pitch_hz is not None
                    else _improvement(finding, after_finding)
                ),
                warnings=application.warnings,
                reason=(
                    application.reason
                    + " The candidate is retained for comparison and is not selected automatically."
                ),
            )
            records[defect] = record
            warnings.extend(application.warnings)
            continue

        raise AnalysisError(f"Unsupported repair policy: {policy.value}")

    selected_findings = detect_wave_defects(
        selected_samples,
        context=_context_after_pitch(selected_context, selected_pitch),
        thresholds=selected_thresholds,
    )
    candidate_findings = detect_wave_defects(
        candidate_samples,
        context=_context_after_pitch(selected_context, candidate_pitch),
        thresholds=selected_thresholds,
    )
    before_risk = _risk(findings)
    selected_risk = _risk(selected_findings)
    improvement_score = (
        0.0
        if before_risk <= 1.0e-12
        else float(min(1.0, max(0.0, (before_risk - selected_risk) / before_risk)))
    )
    selected_is_candidate = selected_samples == candidate_samples
    comparison = RepairComparison(
        schema_version=1,
        before_samples=source,
        candidate_samples=candidate_samples,
        selected_samples=selected_samples,
        selected_is_candidate=selected_is_candidate,
        before_metrics=measure_repair_wave(source),
        candidate_metrics=measure_repair_wave(candidate_samples),
        selected_metrics=measure_repair_wave(selected_samples),
        before_detected_count=sum(finding.detected for finding in findings),
        candidate_detected_count=sum(finding.detected for finding in candidate_findings),
        selected_detected_count=sum(finding.detected for finding in selected_findings),
        improvement_score=improvement_score,
        reason=(
            "The report preserves the original, the complete comparison candidate, "
            "and the actually selected AUTO-only result."
        ),
    )
    canonical_actions = tuple(records[defect] for defect in RepairDefect)
    unique_warnings = tuple(dict.fromkeys(warnings))
    return AutoRepairResult(
        schema_version=1,
        source_samples_sha256=_sample_hash(source),
        context_sha256=selected_context.analysis_sha256,
        thresholds_sha256=selected_thresholds.analysis_sha256,
        policy_set_sha256=selected_policy_set.analysis_sha256,
        findings=findings,
        actions=canonical_actions,
        comparison=comparison,
        final_samples=selected_samples,
        corrected_pitch_hz=selected_pitch,
        warnings=unique_warnings,
        reason=(
            "Auto Repair evaluated every canonical defect, executed only policy-authorized "
            "safe actions, and retained complete before/candidate/selected evidence."
        ),
    )


def auto_repair_wave_sequence(
    waves: Sequence[Sequence[float]],
    *,
    base_context: RepairContext | None = None,
    thresholds: RepairThresholds | None = None,
    policy_set: RepairPolicySet | None = None,
) -> AutoRepairSequenceResult:
    source_waves = tuple(_validate(wave) for wave in waves)
    if not source_waves:
        raise AnalysisError("Auto Repair sequence requires at least one wave")
    expected_count = len(source_waves[0])
    if any(len(wave) != expected_count for wave in source_waves):
        raise AnalysisError("Auto Repair sequence waves must have one consistent length")

    selected_thresholds = RepairThresholds() if thresholds is None else thresholds
    selected_policy_set = (
        build_repair_policy_set() if policy_set is None else policy_set
    )
    template = (
        RepairContext(expected_sample_count=expected_count)
        if base_context is None
        else base_context
    )
    rms_values = tuple(measure_repair_wave(wave).rms for wave in source_waves)
    positive_rms = tuple(value for value in rms_values if value > 1.0e-12)
    sequence_target_rms = (
        None if not positive_rms else float(np.median(np.asarray(positive_rms)))
    )

    entries: list[AutoRepairSequenceEntry] = []
    repaired: list[tuple[float, ...]] = []
    for index, wave in enumerate(source_waves):
        previous = None if index == 0 else repaired[index - 1]
        following = None if index + 1 >= len(source_waves) else source_waves[index + 1]
        context = replace(
            template,
            expected_sample_count=expected_count,
            previous_samples=previous,
            next_samples=following,
            target_rms=(
                template.target_rms
                if template.target_rms is not None
                else sequence_target_rms
            ),
            source_label=f"wave_{index:02d}",
        )
        result = auto_repair_wave(
            wave,
            context=context,
            thresholds=selected_thresholds,
            policy_set=selected_policy_set,
        )
        repaired.append(result.final_samples)
        entries.append(AutoRepairSequenceEntry(index=index, result=result))

    before_hash = _canonical_hash(
        {"sample_sha256": [_sample_hash(wave) for wave in source_waves]}
    )
    after_hash = _canonical_hash(
        {"sample_sha256": [_sample_hash(wave) for wave in repaired]}
    )
    detected_count = sum(len(entry.result.detected_defects) for entry in entries)
    applied_count = sum(len(entry.result.applied_actions) for entry in entries)
    return AutoRepairSequenceResult(
        schema_version=1,
        entries=tuple(entries),
        policy_set_sha256=selected_policy_set.analysis_sha256,
        thresholds_sha256=selected_thresholds.analysis_sha256,
        before_sequence_sha256=before_hash,
        after_sequence_sha256=after_hash,
        detected_defect_count=detected_count,
        applied_action_count=applied_count,
        reason=(
            "The sequence was processed in canonical order; each wave used the repaired "
            "previous wave and original next wave as explicit inter-wave context."
        ),
    )


__all__ = ["auto_repair_wave", "auto_repair_wave_sequence"]
