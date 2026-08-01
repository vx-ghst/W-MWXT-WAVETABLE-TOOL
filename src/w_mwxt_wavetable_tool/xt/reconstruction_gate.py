from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import re
from typing import Any, Mapping, Sequence

from ..constants import USER_WAVE_FIRST, USER_WAVE_LAST, DumpType
from ..dump import DumpFile
from ..errors import HardwareValidationError
from ..message import SysExMessage
from ..models import UserWave
from ..version import __version__

_STEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PROBE_COUNT, STORED_COUNT, FULL_COUNT = 3, 64, 128


class XtGatePattern(str, Enum):
    INDEXED_ASYMMETRIC = "indexed_asymmetric"
    EDGE_EXTREMES = "edge_extremes"
    SEEDED_RANDOM = "seeded_random"


class XtReconstructionHypothesis(str, Enum):
    PRESERVE_REQUESTED_128 = "preserve_requested_128"
    ZERO_FILL_SECOND_HALF = "zero_fill_second_half"
    REPEAT_FIRST_HALF = "repeat_first_half"
    MIRROR_FIRST_HALF = "mirror_first_half"
    NEGATE_FIRST_HALF = "negate_first_half"
    REVERSE_NEGATE_MATHEMATICAL = "reverse_negate_mathematical"
    REVERSE_NEGATE_WRAP_I8 = "reverse_negate_wrap_i8"
    REVERSE_NEGATE_SATURATE_I8 = "reverse_negate_saturate_i8"


class XtProbeStorageStatus(str, Enum):
    EXACT = "exact"
    PAYLOAD_CHANGED = "payload_changed"
    MISSING = "missing"
    DUPLICATE = "duplicate"


class XtGateStatus(str, Enum):
    PASS = "pass"
    PENDING_OBSERVATION = "pending_observation"
    INCONCLUSIVE = "inconclusive"
    FAIL = "fail"


class XtGateVerdict(str, Enum):
    PROTOCOL_STORAGE_CONFIRMED_RECONSTRUCTION_UNRESOLVED = "protocol_storage_confirmed_reconstruction_unresolved"
    FULL_128_PRESERVED = "full_128_preserved"
    SECOND_HALF_ZERO_FILLED = "second_half_zero_filled"
    SECOND_HALF_REPEATED = "second_half_repeated"
    SECOND_HALF_MIRRORED = "second_half_mirrored"
    SECOND_HALF_NEGATED = "second_half_negated"
    SECOND_HALF_REVERSED_ANTISYMMETRIC_MATHEMATICAL = "second_half_reversed_antisymmetric_mathematical"
    SECOND_HALF_REVERSED_ANTISYMMETRIC_WRAP_I8 = "second_half_reversed_antisymmetric_wrap_i8"
    SECOND_HALF_REVERSED_ANTISYMMETRIC_SATURATE_I8 = "second_half_reversed_antisymmetric_saturate_i8"
    AMBIGUOUS_HYPOTHESES = "ambiguous_hypotheses"
    NO_HYPOTHESIS_MATCH = "no_hypothesis_match"
    READBACK_FAILED = "readback_failed"
    RESTORE_CONFIRMED = "restore_confirmed"
    RESTORE_FAILED = "restore_failed"


_VERDICT = {
    XtReconstructionHypothesis.PRESERVE_REQUESTED_128: XtGateVerdict.FULL_128_PRESERVED,
    XtReconstructionHypothesis.ZERO_FILL_SECOND_HALF: XtGateVerdict.SECOND_HALF_ZERO_FILLED,
    XtReconstructionHypothesis.REPEAT_FIRST_HALF: XtGateVerdict.SECOND_HALF_REPEATED,
    XtReconstructionHypothesis.MIRROR_FIRST_HALF: XtGateVerdict.SECOND_HALF_MIRRORED,
    XtReconstructionHypothesis.NEGATE_FIRST_HALF: XtGateVerdict.SECOND_HALF_NEGATED,
    XtReconstructionHypothesis.REVERSE_NEGATE_MATHEMATICAL: XtGateVerdict.SECOND_HALF_REVERSED_ANTISYMMETRIC_MATHEMATICAL,
    XtReconstructionHypothesis.REVERSE_NEGATE_WRAP_I8: XtGateVerdict.SECOND_HALF_REVERSED_ANTISYMMETRIC_WRAP_I8,
    XtReconstructionHypothesis.REVERSE_NEGATE_SATURATE_I8: XtGateVerdict.SECOND_HALF_REVERSED_ANTISYMMETRIC_SATURATE_I8,
}


def _json_hash(data: Mapping[str, Any]) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return sha256(raw).hexdigest()


def _bytes_hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _i8(values: Sequence[int], count: int, label: str) -> tuple[int, ...]:
    result = tuple(int(v) for v in values)
    if len(result) != count or any(v < -128 or v > 127 for v in result):
        raise HardwareValidationError(f"{label} must contain {count} signed int8 samples")
    return result


def _wrap(value: int) -> int:
    return ((value + 128) % 256) - 128


def _sat(value: int) -> int:
    return max(-128, min(127, value))


def _next(value: int) -> int:
    return -128 if value == 127 else value + 1


@dataclass(frozen=True, slots=True)
class XtGateProbe:
    index: int
    pattern: XtGatePattern
    target_wave_number: int
    stored_samples: tuple[int, ...]
    requested_full_samples: tuple[int, ...]
    reason: str

    def __post_init__(self) -> None:
        stored = _i8(self.stored_samples, STORED_COUNT, "stored_samples")
        full = _i8(self.requested_full_samples, FULL_COUNT, "requested_full_samples")
        if self.index < 0 or not USER_WAVE_FIRST <= self.target_wave_number <= USER_WAVE_LAST:
            raise HardwareValidationError("invalid probe index or User Wave target")
        if full[:STORED_COUNT] != stored or not self.reason:
            raise HardwareValidationError("full probe must begin with its stored half and include a reason")

    @property
    def probe_sha256(self) -> str:
        return _json_hash(self._dict())

    def _dict(self) -> dict[str, Any]:
        return {"index": self.index, "pattern": self.pattern.value, "target_wave_number": self.target_wave_number,
                "stored_samples": list(self.stored_samples), "requested_full_samples": list(self.requested_full_samples),
                "reason": self.reason}

    def to_dict(self) -> dict[str, Any]:
        return {**self._dict(), "probe_sha256": self.probe_sha256}

    def to_user_wave(self, device_id: int) -> UserWave:
        return UserWave(device_id, self.target_wave_number, self.stored_samples)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "XtGateProbe":
        probe = cls(int(data["index"]), XtGatePattern(str(data["pattern"])), int(data["target_wave_number"]),
                    tuple(data["stored_samples"]), tuple(data["requested_full_samples"]), str(data["reason"]))
        if data.get("probe_sha256", probe.probe_sha256) != probe.probe_sha256:
            raise HardwareValidationError("probe SHA-256 mismatch")
        return probe


@dataclass(frozen=True, slots=True)
class XtReconstructionGatePlan:
    schema_version: int
    tool_version: str
    seed: int
    device_id: int
    target_wave_start: int
    baseline_sha256: str
    probe_package_sha256: str
    restore_bundle_sha256: str
    probes: tuple[XtGateProbe, ...]
    adjustments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not 0 <= self.device_id <= 126 or len(self.probes) != PROBE_COUNT:
            raise HardwareValidationError("invalid gate plan identity")
        if tuple(p.index for p in self.probes) != tuple(range(PROBE_COUNT)):
            raise HardwareValidationError("probe indexes must be contiguous")
        if tuple(p.target_wave_number for p in self.probes) != tuple(range(self.target_wave_start, self.target_wave_start + PROBE_COUNT)):
            raise HardwareValidationError("probe targets must be consecutive")
        for name in ("baseline_sha256", "probe_package_sha256", "restore_bundle_sha256"):
            value = getattr(self, name)
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise HardwareValidationError(f"invalid {name}")

    def _dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "tool_version": self.tool_version, "seed": self.seed, "device_id": self.device_id,
                "target_wave_start": self.target_wave_start, "probe_count": PROBE_COUNT, "stored_sample_count": STORED_COUNT,
                "logical_sample_count": FULL_COUNT, "wavd_payload_nibble_count": 128,
                "baseline_sha256": self.baseline_sha256, "probe_package_sha256": self.probe_package_sha256,
                "restore_bundle_sha256": self.restore_bundle_sha256, "probe_sha256": [p.probe_sha256 for p in self.probes],
                "probes": [p.to_dict() for p in self.probes], "adjustments": list(self.adjustments),
                "evidence_boundary": {"readback_can_prove": ["64 stored signed int8 samples survived write and read-back"],
                                      "readback_cannot_prove": ["the oscillator second-half reconstruction law"]}}

    @property
    def plan_sha256(self) -> str:
        return _json_hash(self._dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self._dict(), "plan_sha256": self.plan_sha256}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    def to_markdown(self) -> str:
        rows = "\n".join(f"| {p.index} | {p.pattern.value} | {p.target_wave_number} | `{p.probe_sha256}` |" for p in self.probes)
        return f"""# CODE V7-A — XT reconstruction gate plan

- Plan SHA-256: `{self.plan_sha256}`
- Device ID: `{self.device_id}`
- User Waves: `{self.target_wave_start}–{self.target_wave_start + PROBE_COUNT - 1}`
- WAVD: `128 nibbles = 64 stored signed int8 samples`

## Critical evidence boundary

Exact WAVD read-back proves only the 64 stored values. It cannot prove how oscillator samples 64–127 are produced. A hardware verdict requires an independent phase-aligned 128-sample observation.

| # | Pattern | User Wave | Probe SHA-256 |
|---:|---|---:|---|
{rows}

Restore the generated bundle after the test and verify it by a fresh read-back. Do not freeze V7-B until one hypothesis matches uniquely.
"""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "XtReconstructionGatePlan":
        plan = cls(int(data["schema_version"]), str(data["tool_version"]), int(data["seed"]), int(data["device_id"]),
                   int(data["target_wave_start"]), str(data["baseline_sha256"]), str(data["probe_package_sha256"]),
                   str(data["restore_bundle_sha256"]), tuple(XtGateProbe.from_dict(x) for x in data["probes"]),
                   tuple(str(x) for x in data.get("adjustments", ())))
        if data.get("plan_sha256", plan.plan_sha256) != plan.plan_sha256:
            raise HardwareValidationError("gate plan SHA-256 mismatch")
        return plan

    @classmethod
    def from_json(cls, text: str) -> "XtReconstructionGatePlan":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise HardwareValidationError("manifest root must be an object")
        return cls.from_dict(data)


@dataclass(frozen=True, slots=True)
class XtGateBuildOutputPaths:
    probe_package: Path
    restore_bundle: Path
    manifest_json: Path
    manifest_markdown: Path
    observation_template_json: Path


@dataclass(frozen=True, slots=True)
class XtGateBuild:
    probe_package: DumpFile
    restore_bundle: DumpFile
    plan: XtReconstructionGatePlan

    @property
    def ready_for_transmission(self) -> bool:
        return all(a.payload != b.payload for a, b in zip(self.probe_package.messages, self.restore_bundle.messages, strict=True))

    def write(self, directory: str | Path, *, stem: str = "CODE_V7_A_XT_RECONSTRUCTION_GATE") -> XtGateBuildOutputPaths:
        _check_stem(stem)
        root = Path(directory); root.mkdir(parents=True, exist_ok=True)
        paths = XtGateBuildOutputPaths(root / f"{stem}.probe.syx", root / f"{stem}.restore.syx",
                                       root / f"{stem}.manifest.json", root / f"{stem}.manifest.md",
                                       root / f"{stem}.observation-template.json")
        paths.probe_package.write_bytes(self.probe_package.to_bytes())
        paths.restore_bundle.write_bytes(self.restore_bundle.to_bytes())
        paths.manifest_json.write_text(self.plan.to_json(), encoding="utf-8", newline="\n")
        paths.manifest_markdown.write_text(self.plan.to_markdown(), encoding="utf-8", newline="\n")
        template = {"schema_version": 1, "gate_plan_sha256": self.plan.plan_sha256,
                    "measurement_method": "independent phase-aligned 128-sample observation",
                    "cycles": [{"target_wave_number": p.target_wave_number, "samples": []} for p in self.plan.probes]}
        paths.observation_template_json.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return paths


@dataclass(frozen=True, slots=True)
class XtProbeReadbackEvidence:
    index: int
    target_wave_number: int
    status: XtProbeStorageStatus
    expected_stored_sha256: str
    observed_stored_sha256: str | None
    differing_sample_indexes: tuple[int, ...]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "target_wave_number": self.target_wave_number, "status": self.status.value,
                "expected_stored_sha256": self.expected_stored_sha256, "observed_stored_sha256": self.observed_stored_sha256,
                "differing_sample_indexes": list(self.differing_sample_indexes), "note": self.note}


@dataclass(frozen=True, slots=True)
class XtHypothesisScore:
    hypothesis: XtReconstructionHypothesis
    compared_sample_count: int
    differing_sample_count: int
    total_absolute_error: float
    maximum_absolute_error: float
    normalized_rmse: float

    @property
    def exact(self) -> bool:
        return self.maximum_absolute_error == 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"hypothesis": self.hypothesis.value, "compared_sample_count": self.compared_sample_count,
                "differing_sample_count": self.differing_sample_count, "total_absolute_error": self.total_absolute_error,
                "maximum_absolute_error": self.maximum_absolute_error, "normalized_rmse": self.normalized_rmse, "exact": self.exact}


@dataclass(frozen=True, slots=True)
class XtGateAnalysis:
    schema_version: int
    tool_version: str
    gate_plan_sha256: str
    expected_package_sha256: str
    readback_sha256: str
    storage_evidence: tuple[XtProbeReadbackEvidence, ...]
    observation_complete: bool
    observation_method: str | None
    hypothesis_scores: tuple[XtHypothesisScore, ...]
    matched_hypotheses: tuple[XtReconstructionHypothesis, ...]
    status: XtGateStatus
    verdict: XtGateVerdict
    architecture_decision: str
    reason: str

    @property
    def storage_passed(self) -> bool:
        return bool(self.storage_evidence) and all(x.status is XtProbeStorageStatus.EXACT for x in self.storage_evidence)

    def _dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "tool_version": self.tool_version, "gate_plan_sha256": self.gate_plan_sha256,
                "expected_package_sha256": self.expected_package_sha256, "readback_sha256": self.readback_sha256,
                "storage_passed": self.storage_passed, "storage_evidence": [x.to_dict() for x in self.storage_evidence],
                "observation_complete": self.observation_complete, "observation_method": self.observation_method,
                "hypothesis_scores": [x.to_dict() for x in self.hypothesis_scores],
                "matched_hypotheses": [x.value for x in self.matched_hypotheses], "status": self.status.value,
                "verdict": self.verdict.value, "architecture_decision": self.architecture_decision, "reason": self.reason}

    @property
    def analysis_sha256(self) -> str:
        return _json_hash(self._dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self._dict(), "analysis_sha256": self.analysis_sha256}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    def to_markdown(self) -> str:
        rows = "\n".join(f"| {x.index} | {x.target_wave_number} | {x.status.value} | {', '.join(map(str, x.differing_sample_indexes))} |" for x in self.storage_evidence)
        return f"""# CODE V7-A — XT reconstruction gate result

- Status: **{self.status.value}**
- Verdict: **{self.verdict.value}**
- Storage passed: `{'yes' if self.storage_passed else 'no'}`
- Observation complete: `{'yes' if self.observation_complete else 'no'}`
- Architecture: `{self.architecture_decision}`
- Analysis SHA-256: `{self.analysis_sha256}`

{self.reason}

| # | User Wave | Status | Differing samples |
|---:|---:|---|---|
{rows}
"""


@dataclass(frozen=True, slots=True)
class XtGateAnalysisOutputPaths:
    json_report: Path
    markdown_report: Path


@dataclass(frozen=True, slots=True)
class XtGateAnalysisResult:
    analysis: XtGateAnalysis

    def write(self, directory: str | Path, *, stem: str = "CODE_V7_A_XT_RECONSTRUCTION_GATE") -> XtGateAnalysisOutputPaths:
        _check_stem(stem); root = Path(directory); root.mkdir(parents=True, exist_ok=True)
        paths = XtGateAnalysisOutputPaths(root / f"{stem}.analysis.json", root / f"{stem}.analysis.md")
        paths.json_report.write_text(self.analysis.to_json(), encoding="utf-8", newline="\n")
        paths.markdown_report.write_text(self.analysis.to_markdown(), encoding="utf-8", newline="\n")
        return paths


def generate_xt_gate_probes(*, target_wave_start: int, seed: int = 0x57A) -> tuple[XtGateProbe, ...]:
    if not USER_WAVE_FIRST <= target_wave_start <= USER_WAVE_LAST - 2:
        raise HardwareValidationError("target_wave_start must fit three consecutive User Waves")
    probes = []
    for index, pattern in enumerate(XtGatePattern):
        first, second, reason = _pattern(pattern, seed + index)
        second = _discriminate(first, second)
        probes.append(XtGateProbe(index, pattern, target_wave_start + index, first, first + second, reason))
    return tuple(probes)


def build_xt_reconstruction_gate(baseline: DumpFile, *, target_wave_start: int = 1247,
                                 seed: int = 0x57A, tool_version: str = __version__) -> XtGateBuild:
    if baseline.validate() or len(baseline.device_ids) != 1 or not 0 <= baseline.device_ids[0] <= 126:
        raise HardwareValidationError("baseline must be valid and contain one direct Device ID")
    device = baseline.device_ids[0]; index = _index(baseline); probes = list(generate_xt_gate_probes(target_wave_start=target_wave_start, seed=seed))
    restore, adjustments = [], []
    for i, probe in enumerate(probes):
        matches = index.get(probe.target_wave_number, ())
        if len(matches) != 1:
            raise HardwareValidationError(f"baseline must contain exactly one User Wave {probe.target_wave_number}")
        restore.append(matches[0]); sent = probe.to_user_wave(device).to_message()
        if sent.payload == matches[0].payload:
            stored = list(probe.stored_samples); pos = (seed + i * 17) % 64; stored[pos] = _next(stored[pos])
            probes[i] = replace(probe, stored_samples=tuple(stored), requested_full_samples=tuple(stored) + _discriminate(stored, probe.requested_full_samples[64:]))
            adjustments.append(f"User Wave {probe.target_wave_number}: sample {pos} changed to avoid a baseline-identical payload")
    package = DumpFile(tuple(p.to_user_wave(device).to_message() for p in probes)); restore_dump = DumpFile(tuple(restore))
    if DumpFile.from_bytes(package.to_bytes()).to_bytes() != package.to_bytes() or DumpFile.from_bytes(restore_dump.to_bytes()).to_bytes() != restore_dump.to_bytes():
        raise HardwareValidationError("generated SysEx failed strict round-trip")
    plan = XtReconstructionGatePlan(1, tool_version, seed, device, target_wave_start, _bytes_hash(baseline.to_bytes()),
                                    _bytes_hash(package.to_bytes()), _bytes_hash(restore_dump.to_bytes()), tuple(probes), tuple(adjustments))
    result = XtGateBuild(package, restore_dump, plan)
    if not result.ready_for_transmission:
        raise HardwareValidationError("probe payload still matches baseline")
    return result


def analyze_xt_reconstruction_gate(expected_probe_package: DumpFile, readback: DumpFile, plan: XtReconstructionGatePlan, *,
                                   observed_cycles: Mapping[int | str, Sequence[int | float]] | None = None,
                                   observation_method: str | None = None, exact_tolerance: float = 0.0,
                                   tool_version: str = __version__) -> XtGateAnalysisResult:
    if exact_tolerance < 0 or not math.isfinite(exact_tolerance):
        raise HardwareValidationError("exact_tolerance must be finite and non-negative")
    expected_raw = expected_probe_package.to_bytes()
    if _bytes_hash(expected_raw) != plan.probe_package_sha256:
        raise HardwareValidationError("expected probe package does not match manifest")
    evidence = _compare_targets(expected_probe_package, readback, plan)
    if not all(x.status is XtProbeStorageStatus.EXACT for x in evidence):
        return _result(plan, expected_raw, readback, evidence, XtGateStatus.FAIL, XtGateVerdict.READBACK_FAILED,
                       "do_not_start_code_v7_b", "The 64 stored values were not recovered exactly.", tool_version=tool_version)
    observed = _observed(observed_cycles, plan)
    if observed is None:
        return _result(plan, expected_raw, readback, evidence, XtGateStatus.PENDING_OBSERVATION,
                       XtGateVerdict.PROTOCOL_STORAGE_CONFIRMED_RECONSTRUCTION_UNRESOLVED,
                       "do_not_freeze_symmetry_optimizer",
                       "WAVD read-back confirms 64 stored values only. Supply independent 128-point observations for all probes.",
                       observation_method=observation_method, tool_version=tool_version)
    scores = tuple(_score(h, plan.probes, observed) for h in XtReconstructionHypothesis)
    matches = tuple(x.hypothesis for x in scores if x.maximum_absolute_error <= exact_tolerance)
    if len(matches) == 1:
        status, verdict = XtGateStatus.PASS, _VERDICT[matches[0]]
        architecture = "native_full_128" if matches[0] is XtReconstructionHypothesis.PRESERVE_REQUESTED_128 else "stored_64_plus_explicit_derived_128"
        reason = f"All observations uniquely match {matches[0].value}."
    elif matches:
        status, verdict, architecture = XtGateStatus.INCONCLUSIVE, XtGateVerdict.AMBIGUOUS_HYPOTHESES, "do_not_freeze_symmetry_optimizer"
        reason = "Multiple hypotheses match; add a discriminating observation."
    else:
        status, verdict, architecture = XtGateStatus.INCONCLUSIVE, XtGateVerdict.NO_HYPOTHESIS_MATCH, "do_not_freeze_symmetry_optimizer"
        reason = "No supported hypothesis matches; check provenance and add the observed law explicitly."
    return _result(plan, expected_raw, readback, evidence, status, verdict, architecture, reason,
                   observation_method=observation_method, scores=scores, matches=matches, observation_complete=True, tool_version=tool_version)


def verify_xt_reconstruction_gate_restore(expected_restore_bundle: DumpFile, readback: DumpFile,
                                          plan: XtReconstructionGatePlan, *, tool_version: str = __version__) -> XtGateAnalysisResult:
    raw = expected_restore_bundle.to_bytes()
    if _bytes_hash(raw) != plan.restore_bundle_sha256:
        raise HardwareValidationError("restore bundle does not match manifest")
    evidence = _compare_targets(expected_restore_bundle, readback, plan)
    passed = all(x.status is XtProbeStorageStatus.EXACT for x in evidence)
    return _result(plan, raw, readback, evidence, XtGateStatus.PASS if passed else XtGateStatus.FAIL,
                   XtGateVerdict.RESTORE_CONFIRMED if passed else XtGateVerdict.RESTORE_FAILED,
                   "restore_complete" if passed else "restore_required",
                   "All pre-write User Waves were restored exactly." if passed else "At least one target differs from the pre-write backup.",
                   observation_method="restore read-back", tool_version=tool_version)


def parse_observation_document(text: str) -> tuple[dict[int, tuple[int | float, ...]], str | None, str | None]:
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("cycles"), list):
        raise HardwareValidationError("invalid observation document")
    cycles: dict[int, tuple[int | float, ...]] = {}
    for item in data["cycles"]:
        target = int(item["target_wave_number"])
        if target in cycles or not isinstance(item.get("samples"), list):
            raise HardwareValidationError("duplicate target or invalid samples")
        cycles[target] = tuple(item["samples"])
    return cycles, None if data.get("measurement_method") is None else str(data["measurement_method"]), None if data.get("gate_plan_sha256") is None else str(data["gate_plan_sha256"])


def reconstruct_probe(probe: XtGateProbe, hypothesis: XtReconstructionHypothesis) -> tuple[int, ...]:
    first = probe.stored_samples
    if hypothesis is XtReconstructionHypothesis.PRESERVE_REQUESTED_128: return probe.requested_full_samples
    if hypothesis is XtReconstructionHypothesis.ZERO_FILL_SECOND_HALF: second = (0,) * 64
    elif hypothesis is XtReconstructionHypothesis.REPEAT_FIRST_HALF: second = first
    elif hypothesis is XtReconstructionHypothesis.MIRROR_FIRST_HALF: second = tuple(reversed(first))
    elif hypothesis is XtReconstructionHypothesis.NEGATE_FIRST_HALF: second = tuple(-x for x in first)
    elif hypothesis is XtReconstructionHypothesis.REVERSE_NEGATE_MATHEMATICAL: second = tuple(-x for x in reversed(first))
    elif hypothesis is XtReconstructionHypothesis.REVERSE_NEGATE_WRAP_I8: second = tuple(_wrap(-x) for x in reversed(first))
    elif hypothesis is XtReconstructionHypothesis.REVERSE_NEGATE_SATURATE_I8: second = tuple(_sat(-x) for x in reversed(first))
    else: raise HardwareValidationError("unsupported hypothesis")
    return first + second


def _result(plan: XtReconstructionGatePlan, expected_raw: bytes, readback: DumpFile,
            evidence: tuple[XtProbeReadbackEvidence, ...], status: XtGateStatus, verdict: XtGateVerdict,
            architecture: str, reason: str, *, observation_method: str | None = None,
            scores: tuple[XtHypothesisScore, ...] = (), matches: tuple[XtReconstructionHypothesis, ...] = (),
            observation_complete: bool = False, tool_version: str) -> XtGateAnalysisResult:
    return XtGateAnalysisResult(XtGateAnalysis(1, tool_version, plan.plan_sha256, _bytes_hash(expected_raw),
        _bytes_hash(readback.to_bytes()), evidence, observation_complete, observation_method, scores, matches,
        status, verdict, architecture, reason))


def _compare_targets(expected: DumpFile, readback: DumpFile, plan: XtReconstructionGatePlan) -> tuple[XtProbeReadbackEvidence, ...]:
    exp, obs, result = _index(expected), _index(readback), []
    for probe in plan.probes:
        em = exp.get(probe.target_wave_number, ())
        if len(em) != 1: raise HardwareValidationError(f"expected file must contain one User Wave {probe.target_wave_number}")
        ew = UserWave.from_message(em[0]); eh = _sample_hash(ew.stored_samples); om = obs.get(probe.target_wave_number, ())
        if not om: result.append(XtProbeReadbackEvidence(probe.index, probe.target_wave_number, XtProbeStorageStatus.MISSING, eh, None, (), "missing")); continue
        if len(om) != 1: result.append(XtProbeReadbackEvidence(probe.index, probe.target_wave_number, XtProbeStorageStatus.DUPLICATE, eh, None, (), "duplicate")); continue
        ow = UserWave.from_message(om[0]); diff = tuple(i for i, pair in enumerate(zip(ew.stored_samples, ow.stored_samples, strict=True)) if pair[0] != pair[1])
        result.append(XtProbeReadbackEvidence(probe.index, probe.target_wave_number,
            XtProbeStorageStatus.EXACT if not diff else XtProbeStorageStatus.PAYLOAD_CHANGED,
            eh, _sample_hash(ow.stored_samples), diff, "exact" if not diff else "changed"))
    return tuple(result)


def _pattern(pattern: XtGatePattern, seed: int) -> tuple[tuple[int, ...], tuple[int, ...], str]:
    if pattern is XtGatePattern.INDEXED_ASYMMETRIC:
        return tuple(((i * 37 + 11) % 255) - 127 for i in range(64)), tuple(((i * 53 + 29) % 251) - 125 for i in range(64)), "Distinguishes direct, mirrored, repeated, and negated halves."
    if pattern is XtGatePattern.EDGE_EXTREMES:
        anchors = (-128, 127, 0, 1, -1, 126, -127, 64, -64, 32, -32)
        first = tuple(anchors[i % len(anchors)] if i < len(anchors) * 2 else ((i * 19 + 7) % 256) - 128 for i in range(64))
        return first, tuple(((i * 71 + 17) % 253) - 126 for i in range(64)), "Distinguishes mathematical, wrapped, and saturated negation."
    rng = random.Random(seed)
    return tuple(rng.randint(-128, 127) for _ in range(64)), tuple(rng.randint(-128, 127) for _ in range(64)), "Reduces accidental agreement with an unmodeled transform."


def _discriminate(first: Sequence[int], second: Sequence[int]) -> tuple[int, ...]:
    first = _i8(first, 64, "first half"); result = list(_i8(second, 64, "second half"))
    forbidden = {(0,) * 64, first, tuple(reversed(first)), tuple(-x for x in first), tuple(-x for x in reversed(first)),
                 tuple(_wrap(-x) for x in reversed(first)), tuple(_sat(-x) for x in reversed(first))}
    attempt = 0
    while tuple(result) in forbidden:
        result[attempt % 64] = _next(result[attempt % 64]); attempt += 1
        if attempt > 512: raise HardwareValidationError("could not create discriminating probe")
    return tuple(result)


def _observed(data: Mapping[int | str, Sequence[int | float]] | None, plan: XtReconstructionGatePlan) -> dict[int, tuple[float, ...]] | None:
    if data is None: return None
    result = {int(k): tuple(float(x) for x in v) for k, v in data.items()}
    targets = {p.target_wave_number for p in plan.probes}
    if set(result) != targets or any(len(v) != 128 or any(not math.isfinite(x) for x in v) for v in result.values()):
        raise HardwareValidationError("observations must contain 128 finite samples for exactly all gate targets")
    return result


def _score(hypothesis: XtReconstructionHypothesis, probes: Sequence[XtGateProbe], observed: Mapping[int, Sequence[float]]) -> XtHypothesisScore:
    errors = [abs(float(a) - float(b)) for p in probes for a, b in zip(reconstruct_probe(p, hypothesis), observed[p.target_wave_number], strict=True)]
    rmse = math.sqrt(sum(x * x for x in errors) / len(errors)) / 256.0
    return XtHypothesisScore(hypothesis, len(errors), sum(x != 0 for x in errors), float(sum(errors)), float(max(errors, default=0)), float(rmse))


def _index(dump: DumpFile) -> dict[int, tuple[SysExMessage, ...]]:
    grouped: dict[int, list[SysExMessage]] = {}
    for message in dump.messages:
        if int(message.dump_type) == int(DumpType.USER_WAVE): grouped.setdefault(message.address, []).append(message)
    return {k: tuple(v) for k, v in grouped.items()}


def _sample_hash(samples: Sequence[int]) -> str:
    return _bytes_hash(bytes(int(x) & 0xFF for x in samples))


def _check_stem(stem: str) -> None:
    if not _STEM.fullmatch(stem): raise HardwareValidationError("invalid output stem")
