from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from ..constants import USER_WAVE_FIRST, USER_WAVE_LAST, DumpType
from ..dump import DumpFile
from ..errors import HardwareValidationError
from ..message import SysExMessage
from ..models import UserWave
from ..version import __version__

_STEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

MANIFEST_SCHEMA_VERSION = 2
PROBE_COUNT = 3
STORED_COUNT = 64
FULL_COUNT = 128
WIRE_SAMPLE_ENCODING = "offset_binary_msb_flipped"
DOCUMENTED_RECONSTRUCTION_LAW = (
    "second_half[n] = -first_half[63 - n], n=0..63"
)
DOCUMENTED_SOURCE = (
    "Waldorf Microwave II/XT manual, SysEx appendix, printed page 112 "
    "(PDF page 111)"
)
SAFE_OPTIMIZER_MIN = -127
SAFE_OPTIMIZER_MAX = 127


class XtGatePattern(str, Enum):
    INDEXED_ASYMMETRIC = "indexed_asymmetric"
    OFFSET_BINARY_GOLDEN = "offset_binary_golden"
    NEGATIVE_FULL_SCALE_EDGE = "negative_full_scale_edge"


class XtReconstructionHypothesis(str, Enum):
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
    INCONCLUSIVE = "inconclusive"
    FAIL = "fail"


class XtGateVerdict(str, Enum):
    DOCUMENTED_RECONSTRUCTION_STORAGE_CONFIRMED_EDGE_UNRESOLVED = (
        "documented_reconstruction_storage_confirmed_edge_unresolved"
    )
    DOCUMENTED_RECONSTRUCTION_AND_EDGE_MATHEMATICAL_CONFIRMED = (
        "documented_reconstruction_and_edge_mathematical_confirmed"
    )
    DOCUMENTED_RECONSTRUCTION_AND_EDGE_WRAP_I8_CONFIRMED = (
        "documented_reconstruction_and_edge_wrap_i8_confirmed"
    )
    DOCUMENTED_RECONSTRUCTION_AND_EDGE_SATURATE_I8_CONFIRMED = (
        "documented_reconstruction_and_edge_saturate_i8_confirmed"
    )
    DOCUMENTED_RECONSTRUCTION_OBSERVATION_CONFLICT = (
        "documented_reconstruction_observation_conflict"
    )
    READBACK_FAILED = "readback_failed"
    RESTORE_CONFIRMED = "restore_confirmed"
    RESTORE_FAILED = "restore_failed"


_VERDICT = {
    XtReconstructionHypothesis.REVERSE_NEGATE_MATHEMATICAL: (
        XtGateVerdict.DOCUMENTED_RECONSTRUCTION_AND_EDGE_MATHEMATICAL_CONFIRMED
    ),
    XtReconstructionHypothesis.REVERSE_NEGATE_WRAP_I8: (
        XtGateVerdict.DOCUMENTED_RECONSTRUCTION_AND_EDGE_WRAP_I8_CONFIRMED
    ),
    XtReconstructionHypothesis.REVERSE_NEGATE_SATURATE_I8: (
        XtGateVerdict.DOCUMENTED_RECONSTRUCTION_AND_EDGE_SATURATE_I8_CONFIRMED
    ),
}

_EDGE_STATUS = {
    XtReconstructionHypothesis.REVERSE_NEGATE_MATHEMATICAL: "mathematical_wide_+128",
    XtReconstructionHypothesis.REVERSE_NEGATE_WRAP_I8: "wrap_i8_to_-128",
    XtReconstructionHypothesis.REVERSE_NEGATE_SATURATE_I8: "saturate_i8_to_+127",
}


def _json_hash(data: Mapping[str, Any]) -> str:
    raw = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _bytes_hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _i8(values: Sequence[int], count: int, label: str) -> tuple[int, ...]:
    result = tuple(int(value) for value in values)
    if len(result) != count or any(value < -128 or value > 127 for value in result):
        raise HardwareValidationError(
            f"{label} must contain {count} signed int8 samples"
        )
    return result


def _next_sample(value: int) -> int:
    return -127 if value in {-128, 127} else value + 1


@dataclass(frozen=True, slots=True)
class XtGateProbe:
    index: int
    pattern: XtGatePattern
    target_wave_number: int
    stored_samples: tuple[int, ...]
    reason: str

    def __post_init__(self) -> None:
        _i8(self.stored_samples, STORED_COUNT, "stored_samples")
        if self.index < 0:
            raise HardwareValidationError("probe index must be non-negative")
        if not USER_WAVE_FIRST <= self.target_wave_number <= USER_WAVE_LAST:
            raise HardwareValidationError("invalid User Wave target")
        if not self.reason:
            raise HardwareValidationError("probe reason must not be empty")

    @property
    def has_negative_full_scale(self) -> bool:
        return -128 in self.stored_samples

    @property
    def documented_full_samples(self) -> tuple[int, ...]:
        return UserWave(
            device_id=0,
            number=self.target_wave_number,
            stored_samples=self.stored_samples,
        ).reconstruct("documented")

    def _dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "pattern": self.pattern.value,
            "target_wave_number": self.target_wave_number,
            "stored_samples": list(self.stored_samples),
            "has_negative_full_scale": self.has_negative_full_scale,
            "reason": self.reason,
        }

    @property
    def probe_sha256(self) -> str:
        return _json_hash(self._dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self._dict(), "probe_sha256": self.probe_sha256}

    def to_user_wave(self, device_id: int) -> UserWave:
        return UserWave(device_id, self.target_wave_number, self.stored_samples)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "XtGateProbe":
        probe = cls(
            index=int(data["index"]),
            pattern=XtGatePattern(str(data["pattern"])),
            target_wave_number=int(data["target_wave_number"]),
            stored_samples=tuple(int(value) for value in data["stored_samples"]),
            reason=str(data["reason"]),
        )
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
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise HardwareValidationError(
                "CODE V7-A.1 requires manifest schema 2; rebuild any schema-1 gate package"
            )
        if not 0 <= self.device_id <= 126:
            raise HardwareValidationError("gate plan requires one direct Device ID")
        if len(self.probes) != PROBE_COUNT:
            raise HardwareValidationError(
                f"gate plan must contain {PROBE_COUNT} probes"
            )
        if tuple(probe.index for probe in self.probes) != tuple(range(PROBE_COUNT)):
            raise HardwareValidationError("probe indexes must be contiguous")
        expected_targets = tuple(
            range(self.target_wave_start, self.target_wave_start + PROBE_COUNT)
        )
        if tuple(probe.target_wave_number for probe in self.probes) != expected_targets:
            raise HardwareValidationError("probe targets must be consecutive")
        for name in (
            "baseline_sha256",
            "probe_package_sha256",
            "restore_bundle_sha256",
        ):
            value = getattr(self, name)
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise HardwareValidationError(f"invalid {name}")

    def _dict(self) -> dict[str, Any]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "tool_version": self.tool_version,
            "seed": self.seed,
            "device_id": self.device_id,
            "target_wave_start": self.target_wave_start,
            "probe_count": PROBE_COUNT,
            "stored_sample_count": STORED_COUNT,
            "logical_sample_count": FULL_COUNT,
            "wavd_payload_nibble_count": 128,
            "wire_sample_encoding": WIRE_SAMPLE_ENCODING,
            "documented_reconstruction_law": DOCUMENTED_RECONSTRUCTION_LAW,
            "documented_source": DOCUMENTED_SOURCE,
            "safe_optimizer_sample_range": [
                SAFE_OPTIMIZER_MIN,
                SAFE_OPTIMIZER_MAX,
            ],
            "negative_full_scale_behavior": "pending_hardware_characterization",
            "baseline_sha256": self.baseline_sha256,
            "probe_package_sha256": self.probe_package_sha256,
            "restore_bundle_sha256": self.restore_bundle_sha256,
            "probe_sha256": [probe.probe_sha256 for probe in self.probes],
            "probes": [probe.to_dict() for probe in self.probes],
            "adjustments": list(self.adjustments),
            "evidence_boundary": {
                "documentation_establishes": [
                    "64 independent samples are stored/transmitted",
                    "sample bytes use offset binary with the MSB flipped for signed interpretation",
                    "the second half is the sign-inverted reverse of the first half",
                ],
                "wavd_readback_can_prove": [
                    "the exact 64 offset-binary sample bytes survived write and read-back"
                ],
                "hardware_observation_still_needed_for": [
                    "the exact treatment of negating -128",
                    "later oscillator interpolation and analog-output behavior",
                ],
            },
        }

    @property
    def plan_sha256(self) -> str:
        return _json_hash(self._dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self._dict(), "plan_sha256": self.plan_sha256}

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False
        ) + "\n"

    def to_markdown(self) -> str:
        rows = "\n".join(
            (
                f"| {probe.index} | {probe.pattern.value} | "
                f"{probe.target_wave_number} | "
                f"{'yes' if probe.has_negative_full_scale else 'no'} | "
                f"`{probe.probe_sha256}` |"
            )
            for probe in self.probes
        )
        return f"""# CODE V7-A.1 - XT documented reconstruction gate plan

- Plan SHA-256: `{self.plan_sha256}`
- Device ID: `{self.device_id}`
- User Waves: `{self.target_wave_start}-{self.target_wave_start + PROBE_COUNT - 1}`
- WAVD: `128 nibbles = 64 stored sample bytes`
- Wire coding: `{WIRE_SAMPLE_ENCODING}`
- Reconstruction: `{DOCUMENTED_RECONSTRUCTION_LAW}`
- Safe optimizer range until the edge test closes: `{SAFE_OPTIMIZER_MIN}..{SAFE_OPTIMIZER_MAX}`

## Evidence boundary

The manual establishes the 64-to-128 reconstruction law and the offset-binary wire coding. Exact WAVD read-back validates storage and transmission. The remaining hardware question is limited to the `-128 -> +128` edge and later oscillator/output behavior.

| # | Pattern | User Wave | Contains -128 | Probe SHA-256 |
|---:|---|---:|---|---|
{rows}

Restore the generated bundle after the test and verify it with a fresh read-back.
"""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "XtReconstructionGatePlan":
        plan = cls(
            schema_version=int(data["schema_version"]),
            tool_version=str(data["tool_version"]),
            seed=int(data["seed"]),
            device_id=int(data["device_id"]),
            target_wave_start=int(data["target_wave_start"]),
            baseline_sha256=str(data["baseline_sha256"]),
            probe_package_sha256=str(data["probe_package_sha256"]),
            restore_bundle_sha256=str(data["restore_bundle_sha256"]),
            probes=tuple(XtGateProbe.from_dict(item) for item in data["probes"]),
            adjustments=tuple(str(item) for item in data.get("adjustments", ())),
        )
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
        return all(
            sent.payload != baseline.payload
            for sent, baseline in zip(
                self.probe_package.messages,
                self.restore_bundle.messages,
                strict=True,
            )
        )

    def write(
        self,
        directory: str | Path,
        *,
        stem: str = "CODE_V7_A1_XT_RECONSTRUCTION_GATE",
    ) -> XtGateBuildOutputPaths:
        _check_stem(stem)
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        paths = XtGateBuildOutputPaths(
            root / f"{stem}.probe.syx",
            root / f"{stem}.restore.syx",
            root / f"{stem}.manifest.json",
            root / f"{stem}.manifest.md",
            root / f"{stem}.observation-template.json",
        )
        paths.probe_package.write_bytes(self.probe_package.to_bytes())
        paths.restore_bundle.write_bytes(self.restore_bundle.to_bytes())
        paths.manifest_json.write_text(
            self.plan.to_json(), encoding="utf-8", newline="\n"
        )
        paths.manifest_markdown.write_text(
            self.plan.to_markdown(), encoding="utf-8", newline="\n"
        )
        template = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "gate_plan_sha256": self.plan.plan_sha256,
            "measurement_method": (
                "independent digital phase-aligned 128-sample observation; "
                "optional and primarily intended to characterize -128"
            ),
            "cycles": [
                {"target_wave_number": probe.target_wave_number, "samples": []}
                for probe in self.plan.probes
            ],
        }
        paths.observation_template_json.write_text(
            json.dumps(template, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
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
        return {
            "index": self.index,
            "target_wave_number": self.target_wave_number,
            "status": self.status.value,
            "expected_stored_sha256": self.expected_stored_sha256,
            "observed_stored_sha256": self.observed_stored_sha256,
            "differing_sample_indexes": list(self.differing_sample_indexes),
            "note": self.note,
        }


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
        return {
            "hypothesis": self.hypothesis.value,
            "compared_sample_count": self.compared_sample_count,
            "differing_sample_count": self.differing_sample_count,
            "total_absolute_error": self.total_absolute_error,
            "maximum_absolute_error": self.maximum_absolute_error,
            "normalized_rmse": self.normalized_rmse,
            "exact": self.exact,
        }


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
    negative_full_scale_status: str
    v7_b_allowed_under_safe_range: bool
    reason: str

    @property
    def storage_passed(self) -> bool:
        return bool(self.storage_evidence) and all(
            evidence.status is XtProbeStorageStatus.EXACT
            for evidence in self.storage_evidence
        )

    def _dict(self) -> dict[str, Any]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "tool_version": self.tool_version,
            "gate_plan_sha256": self.gate_plan_sha256,
            "expected_package_sha256": self.expected_package_sha256,
            "readback_sha256": self.readback_sha256,
            "wire_sample_encoding": WIRE_SAMPLE_ENCODING,
            "documented_reconstruction_law": DOCUMENTED_RECONSTRUCTION_LAW,
            "safe_optimizer_sample_range": [
                SAFE_OPTIMIZER_MIN,
                SAFE_OPTIMIZER_MAX,
            ],
            "storage_passed": self.storage_passed,
            "storage_evidence": [
                evidence.to_dict() for evidence in self.storage_evidence
            ],
            "observation_complete": self.observation_complete,
            "observation_method": self.observation_method,
            "hypothesis_scores": [score.to_dict() for score in self.hypothesis_scores],
            "matched_hypotheses": [
                hypothesis.value for hypothesis in self.matched_hypotheses
            ],
            "status": self.status.value,
            "verdict": self.verdict.value,
            "architecture_decision": self.architecture_decision,
            "negative_full_scale_status": self.negative_full_scale_status,
            "v7_b_allowed_under_safe_range": self.v7_b_allowed_under_safe_range,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _json_hash(self._dict())

    def to_dict(self) -> dict[str, Any]:
        return {**self._dict(), "analysis_sha256": self.analysis_sha256}

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False
        ) + "\n"

    def to_markdown(self) -> str:
        rows = "\n".join(
            (
                f"| {evidence.index} | {evidence.target_wave_number} | "
                f"{evidence.status.value} | "
                f"{', '.join(map(str, evidence.differing_sample_indexes))} |"
            )
            for evidence in self.storage_evidence
        )
        return f"""# CODE V7-A.1 - XT documented reconstruction gate result

- Status: **{self.status.value}**
- Verdict: **{self.verdict.value}**
- Storage passed: `{'yes' if self.storage_passed else 'no'}`
- Reconstruction law: `{DOCUMENTED_RECONSTRUCTION_LAW}`
- Negative full-scale: `{self.negative_full_scale_status}`
- V7-B allowed with range {SAFE_OPTIMIZER_MIN}..{SAFE_OPTIMIZER_MAX}: `{'yes' if self.v7_b_allowed_under_safe_range else 'no'}`
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

    def write(
        self,
        directory: str | Path,
        *,
        stem: str = "CODE_V7_A1_XT_RECONSTRUCTION_GATE",
    ) -> XtGateAnalysisOutputPaths:
        _check_stem(stem)
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        paths = XtGateAnalysisOutputPaths(
            root / f"{stem}.analysis.json",
            root / f"{stem}.analysis.md",
        )
        paths.json_report.write_text(
            self.analysis.to_json(), encoding="utf-8", newline="\n"
        )
        paths.markdown_report.write_text(
            self.analysis.to_markdown(), encoding="utf-8", newline="\n"
        )
        return paths


def generate_xt_gate_probes(
    *, target_wave_start: int, seed: int = 0x57A
) -> tuple[XtGateProbe, ...]:
    if not USER_WAVE_FIRST <= target_wave_start <= USER_WAVE_LAST - 2:
        raise HardwareValidationError(
            "target_wave_start must fit three consecutive User Waves"
        )
    return tuple(
        XtGateProbe(
            index=index,
            pattern=pattern,
            target_wave_number=target_wave_start + index,
            stored_samples=_pattern(pattern, seed + index),
            reason=_pattern_reason(pattern),
        )
        for index, pattern in enumerate(XtGatePattern)
    )


def build_xt_reconstruction_gate(
    baseline: DumpFile,
    *,
    target_wave_start: int = 1247,
    seed: int = 0x57A,
    tool_version: str = __version__,
) -> XtGateBuild:
    if baseline.validate():
        raise HardwareValidationError("baseline contains invalid SysEx messages")
    if len(baseline.device_ids) != 1 or not 0 <= baseline.device_ids[0] <= 126:
        raise HardwareValidationError(
            "baseline must contain exactly one direct Device ID"
        )

    device_id = baseline.device_ids[0]
    baseline_index = _index(baseline)
    probes = list(
        generate_xt_gate_probes(
            target_wave_start=target_wave_start,
            seed=seed,
        )
    )
    restore_messages: list[SysExMessage] = []
    adjustments: list[str] = []

    for probe_index, probe in enumerate(probes):
        matches = baseline_index.get(probe.target_wave_number, ())
        if len(matches) != 1:
            raise HardwareValidationError(
                "baseline must contain exactly one User Wave "
                f"{probe.target_wave_number}"
            )
        restore_messages.append(matches[0])
        sent = probe.to_user_wave(device_id).to_message()
        if sent.payload == matches[0].payload:
            stored = list(probe.stored_samples)
            sample_index = (seed + probe_index * 17) % STORED_COUNT
            stored[sample_index] = _next_sample(stored[sample_index])
            probes[probe_index] = replace(probe, stored_samples=tuple(stored))
            adjustments.append(
                f"User Wave {probe.target_wave_number}: sample {sample_index} "
                "changed to avoid a baseline-identical payload"
            )

    package = DumpFile(
        tuple(probe.to_user_wave(device_id).to_message() for probe in probes)
    )
    restore_bundle = DumpFile(tuple(restore_messages))
    package_bytes = package.to_bytes()
    restore_bytes = restore_bundle.to_bytes()

    if DumpFile.from_bytes(package_bytes).to_bytes() != package_bytes:
        raise HardwareValidationError("generated probe package failed strict round-trip")
    if DumpFile.from_bytes(restore_bytes).to_bytes() != restore_bytes:
        raise HardwareValidationError("generated restore bundle failed strict round-trip")

    plan = XtReconstructionGatePlan(
        schema_version=MANIFEST_SCHEMA_VERSION,
        tool_version=tool_version,
        seed=seed,
        device_id=device_id,
        target_wave_start=target_wave_start,
        baseline_sha256=_bytes_hash(baseline.to_bytes()),
        probe_package_sha256=_bytes_hash(package_bytes),
        restore_bundle_sha256=_bytes_hash(restore_bytes),
        probes=tuple(probes),
        adjustments=tuple(adjustments),
    )
    result = XtGateBuild(package, restore_bundle, plan)
    if not result.ready_for_transmission:
        raise HardwareValidationError("probe payload still matches baseline")
    return result


def analyze_xt_reconstruction_gate(
    expected_probe_package: DumpFile,
    readback: DumpFile,
    plan: XtReconstructionGatePlan,
    *,
    observed_cycles: Mapping[int | str, Sequence[int | float]] | None = None,
    observation_method: str | None = None,
    exact_tolerance: float = 0.0,
    tool_version: str = __version__,
) -> XtGateAnalysisResult:
    if exact_tolerance < 0 or not math.isfinite(exact_tolerance):
        raise HardwareValidationError(
            "exact_tolerance must be finite and non-negative"
        )

    expected_raw = expected_probe_package.to_bytes()
    if _bytes_hash(expected_raw) != plan.probe_package_sha256:
        raise HardwareValidationError(
            "expected probe package does not match the schema-2 manifest"
        )

    evidence = _compare_targets(expected_probe_package, readback, plan)
    if not all(
        item.status is XtProbeStorageStatus.EXACT for item in evidence
    ):
        return _result(
            plan,
            expected_raw,
            readback,
            evidence,
            status=XtGateStatus.FAIL,
            verdict=XtGateVerdict.READBACK_FAILED,
            architecture="do_not_start_code_v7_b",
            edge_status="not_evaluated",
            v7_b_allowed=False,
            reason=(
                "The 64 stored values were not recovered exactly. Resolve "
                "transmission, addressing, or decoder mismatch before V7-B."
            ),
            tool_version=tool_version,
        )

    observed = _observed(observed_cycles, plan)
    if observed is None:
        return _result(
            plan,
            expected_raw,
            readback,
            evidence,
            status=XtGateStatus.PASS,
            verdict=(
                XtGateVerdict.DOCUMENTED_RECONSTRUCTION_STORAGE_CONFIRMED_EDGE_UNRESOLVED
            ),
            architecture=(
                "stored_64_plus_documented_reverse_negate_128; "
                "optimizer_range_-127_to_127"
            ),
            edge_status="pending_hardware_characterization",
            v7_b_allowed=True,
            reason=(
                "WAVD read-back confirms the 64 offset-binary values exactly. "
                "The manual establishes the reverse-negate reconstruction law. "
                "V7-B may proceed only while generated values remain in -127..127; "
                "the -128 edge remains reserved for a dedicated observation."
            ),
            observation_method=observation_method,
            tool_version=tool_version,
        )

    scores = tuple(
        _score(hypothesis, plan.probes, observed)
        for hypothesis in XtReconstructionHypothesis
    )
    matches = tuple(
        score.hypothesis
        for score in scores
        if score.maximum_absolute_error <= exact_tolerance
    )

    if len(matches) == 1:
        matched = matches[0]
        status = XtGateStatus.PASS
        verdict = _VERDICT[matched]
        architecture = "stored_64_plus_documented_reverse_negate_128"
        edge_status = _EDGE_STATUS[matched]
        v7_b_allowed = True
        reason = (
            "The independent observation confirms the documented reverse-negate "
            f"law and uniquely characterizes the -128 edge as {edge_status}."
        )
    else:
        status = XtGateStatus.INCONCLUSIVE
        verdict = XtGateVerdict.DOCUMENTED_RECONSTRUCTION_OBSERVATION_CONFLICT
        architecture = "retain_documented_law_but_investigate_observation"
        edge_status = "observation_conflict"
        v7_b_allowed = False
        reason = (
            "The supplied observation does not uniquely match one documented "
            "negative-full-scale policy. Verify phase alignment, scaling, and "
            "measurement provenance before proceeding."
        )

    return _result(
        plan,
        expected_raw,
        readback,
        evidence,
        status=status,
        verdict=verdict,
        architecture=architecture,
        edge_status=edge_status,
        v7_b_allowed=v7_b_allowed,
        reason=reason,
        observation_method=observation_method,
        scores=scores,
        matches=matches,
        observation_complete=True,
        tool_version=tool_version,
    )


def verify_xt_reconstruction_gate_restore(
    expected_restore_bundle: DumpFile,
    readback: DumpFile,
    plan: XtReconstructionGatePlan,
    *,
    tool_version: str = __version__,
) -> XtGateAnalysisResult:
    expected_raw = expected_restore_bundle.to_bytes()
    if _bytes_hash(expected_raw) != plan.restore_bundle_sha256:
        raise HardwareValidationError("restore bundle does not match manifest")
    evidence = _compare_targets(expected_restore_bundle, readback, plan)
    passed = all(
        item.status is XtProbeStorageStatus.EXACT for item in evidence
    )
    return _result(
        plan,
        expected_raw,
        readback,
        evidence,
        status=XtGateStatus.PASS if passed else XtGateStatus.FAIL,
        verdict=(
            XtGateVerdict.RESTORE_CONFIRMED
            if passed
            else XtGateVerdict.RESTORE_FAILED
        ),
        architecture="restore_complete" if passed else "restore_required",
        edge_status="not_applicable",
        v7_b_allowed=False,
        reason=(
            "All pre-write User Waves were restored exactly."
            if passed
            else "At least one target differs from the pre-write backup."
        ),
        observation_method="restore read-back",
        tool_version=tool_version,
    )


def parse_observation_document(
    text: str,
) -> tuple[
    dict[int, tuple[int | float, ...]],
    str | None,
    str | None,
]:
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("cycles"), list):
        raise HardwareValidationError("invalid observation document")
    if int(data.get("schema_version", -1)) != MANIFEST_SCHEMA_VERSION:
        raise HardwareValidationError(
            "observation document must use CODE V7-A.1 schema 2"
        )
    cycles: dict[int, tuple[int | float, ...]] = {}
    for item in data["cycles"]:
        target = int(item["target_wave_number"])
        if target in cycles or not isinstance(item.get("samples"), list):
            raise HardwareValidationError("duplicate target or invalid samples")
        cycles[target] = tuple(item["samples"])
    method = (
        None
        if data.get("measurement_method") is None
        else str(data["measurement_method"])
    )
    plan_sha = (
        None
        if data.get("gate_plan_sha256") is None
        else str(data["gate_plan_sha256"])
    )
    return cycles, method, plan_sha


def reconstruct_probe(
    probe: XtGateProbe,
    hypothesis: XtReconstructionHypothesis,
) -> tuple[int, ...]:
    wave = probe.to_user_wave(device_id=0)
    if hypothesis is XtReconstructionHypothesis.REVERSE_NEGATE_MATHEMATICAL:
        return wave.reconstruct("mathematical")
    if hypothesis is XtReconstructionHypothesis.REVERSE_NEGATE_WRAP_I8:
        return wave.reconstruct("wrap_i8")
    if hypothesis is XtReconstructionHypothesis.REVERSE_NEGATE_SATURATE_I8:
        return wave.reconstruct("saturate_i8")
    raise HardwareValidationError("unsupported reconstruction hypothesis")


def _result(
    plan: XtReconstructionGatePlan,
    expected_raw: bytes,
    readback: DumpFile,
    evidence: tuple[XtProbeReadbackEvidence, ...],
    *,
    status: XtGateStatus,
    verdict: XtGateVerdict,
    architecture: str,
    edge_status: str,
    v7_b_allowed: bool,
    reason: str,
    observation_method: str | None = None,
    scores: tuple[XtHypothesisScore, ...] = (),
    matches: tuple[XtReconstructionHypothesis, ...] = (),
    observation_complete: bool = False,
    tool_version: str,
) -> XtGateAnalysisResult:
    analysis = XtGateAnalysis(
        schema_version=MANIFEST_SCHEMA_VERSION,
        tool_version=tool_version,
        gate_plan_sha256=plan.plan_sha256,
        expected_package_sha256=_bytes_hash(expected_raw),
        readback_sha256=_bytes_hash(readback.to_bytes()),
        storage_evidence=evidence,
        observation_complete=observation_complete,
        observation_method=observation_method,
        hypothesis_scores=scores,
        matched_hypotheses=matches,
        status=status,
        verdict=verdict,
        architecture_decision=architecture,
        negative_full_scale_status=edge_status,
        v7_b_allowed_under_safe_range=v7_b_allowed,
        reason=reason,
    )
    return XtGateAnalysisResult(analysis)


def _compare_targets(
    expected: DumpFile,
    readback: DumpFile,
    plan: XtReconstructionGatePlan,
) -> tuple[XtProbeReadbackEvidence, ...]:
    expected_index = _index(expected)
    observed_index = _index(readback)
    result: list[XtProbeReadbackEvidence] = []

    for probe in plan.probes:
        expected_matches = expected_index.get(probe.target_wave_number, ())
        if len(expected_matches) != 1:
            raise HardwareValidationError(
                "expected file must contain one User Wave "
                f"{probe.target_wave_number}"
            )
        expected_wave = UserWave.from_message(expected_matches[0])
        expected_hash = _sample_hash(expected_wave.stored_samples)
        observed_matches = observed_index.get(probe.target_wave_number, ())

        if not observed_matches:
            result.append(
                XtProbeReadbackEvidence(
                    probe.index,
                    probe.target_wave_number,
                    XtProbeStorageStatus.MISSING,
                    expected_hash,
                    None,
                    (),
                    "missing",
                )
            )
            continue
        if len(observed_matches) != 1:
            result.append(
                XtProbeReadbackEvidence(
                    probe.index,
                    probe.target_wave_number,
                    XtProbeStorageStatus.DUPLICATE,
                    expected_hash,
                    None,
                    (),
                    "duplicate",
                )
            )
            continue

        observed_wave = UserWave.from_message(observed_matches[0])
        differing = tuple(
            index
            for index, pair in enumerate(
                zip(
                    expected_wave.stored_samples,
                    observed_wave.stored_samples,
                    strict=True,
                )
            )
            if pair[0] != pair[1]
        )
        result.append(
            XtProbeReadbackEvidence(
                probe.index,
                probe.target_wave_number,
                (
                    XtProbeStorageStatus.EXACT
                    if not differing
                    else XtProbeStorageStatus.PAYLOAD_CHANGED
                ),
                expected_hash,
                _sample_hash(observed_wave.stored_samples),
                differing,
                "exact" if not differing else "changed",
            )
        )
    return tuple(result)


def _pattern(pattern: XtGatePattern, seed: int) -> tuple[int, ...]:
    if pattern is XtGatePattern.INDEXED_ASYMMETRIC:
        return tuple(((index * 37 + seed) % 255) - 127 for index in range(64))
    if pattern is XtGatePattern.OFFSET_BINARY_GOLDEN:
        anchors = (-128, -127, -1, 0, 1, 126, 127)
        return tuple(anchors[index % len(anchors)] for index in range(64))
    if pattern is XtGatePattern.NEGATIVE_FULL_SCALE_EDGE:
        values = [((index * 53 + seed) % 255) - 127 for index in range(64)]
        values[0] = -128
        values[17] = -128
        values[63] = -128
        return tuple(values)
    raise HardwareValidationError("unsupported gate pattern")


def _pattern_reason(pattern: XtGatePattern) -> str:
    if pattern is XtGatePattern.INDEXED_ASYMMETRIC:
        return "Confirms ordered storage with a non-palindromic safe-range pattern."
    if pattern is XtGatePattern.OFFSET_BINARY_GOLDEN:
        return (
            "Exercises the documented raw-byte mapping 00, 01, 7F, 80, 81, FE, FF."
        )
    if pattern is XtGatePattern.NEGATIVE_FULL_SCALE_EDGE:
        return "Reserves three known -128 positions for edge-policy characterization."
    raise HardwareValidationError("unsupported gate pattern")


def _observed(
    data: Mapping[int | str, Sequence[int | float]] | None,
    plan: XtReconstructionGatePlan,
) -> dict[int, tuple[float, ...]] | None:
    if data is None:
        return None
    result = {
        int(key): tuple(float(value) for value in values)
        for key, values in data.items()
    }
    targets = {probe.target_wave_number for probe in plan.probes}
    if set(result) != targets:
        raise HardwareValidationError(
            "observations must cover exactly all gate targets"
        )
    if any(
        len(values) != FULL_COUNT
        or any(not math.isfinite(value) for value in values)
        for values in result.values()
    ):
        raise HardwareValidationError(
            "every observation must contain 128 finite samples"
        )
    return result


def _score(
    hypothesis: XtReconstructionHypothesis,
    probes: Sequence[XtGateProbe],
    observed: Mapping[int, Sequence[float]],
) -> XtHypothesisScore:
    errors = [
        abs(float(expected) - float(actual))
        for probe in probes
        for expected, actual in zip(
            reconstruct_probe(probe, hypothesis),
            observed[probe.target_wave_number],
            strict=True,
        )
    ]
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors)) / 256.0
    return XtHypothesisScore(
        hypothesis=hypothesis,
        compared_sample_count=len(errors),
        differing_sample_count=sum(error != 0 for error in errors),
        total_absolute_error=float(sum(errors)),
        maximum_absolute_error=float(max(errors, default=0.0)),
        normalized_rmse=float(rmse),
    )


def _index(dump: DumpFile) -> dict[int, tuple[SysExMessage, ...]]:
    grouped: dict[int, list[SysExMessage]] = {}
    for message in dump.messages:
        if int(message.dump_type) == int(DumpType.USER_WAVE):
            grouped.setdefault(message.address, []).append(message)
    return {key: tuple(values) for key, values in grouped.items()}


def _sample_hash(samples: Sequence[int]) -> str:
    return _json_hash({"signed_samples": [int(value) for value in samples]})


def _check_stem(stem: str) -> None:
    if not _STEM.fullmatch(stem):
        raise HardwareValidationError("invalid output stem")
