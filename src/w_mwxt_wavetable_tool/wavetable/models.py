from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping, Sequence

USER_POSITION_COUNT = 61
WCTD_POSITION_COUNT = 64
USER_POSITION_FIRST = 0
USER_POSITION_LAST = 60
FIXED_TAIL_POSITIONS = (61, 62, 63)
SAFE_STORED_MIN = -127
SAFE_STORED_MAX = 127
INTERPOLATED_WAVE_REFERENCE = 0xFFFF
WAVETABLE_BUILD_SCHEMA_VERSION = 1

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class WavetableContractError(ValueError):
    """Raised when a generic CODE V8 wavetable contract is invalid."""


class WaveOrigin(str, Enum):
    REAL_CYCLE = "real_cycle"
    RECONSTRUCTED_CYCLE = "reconstructed_cycle"
    REPAIRED_REAL = "repaired_real"
    REPAIRED_RECONSTRUCTED = "repaired_reconstructed"
    GENERATED_VARIANT = "generated_variant"
    INTERPOLATED_TRANSITION = "interpolated_transition"
    FIXED_REFERENCE = "fixed_reference"

    @property
    def is_real(self) -> bool:
        return self in {self.REAL_CYCLE, self.REPAIRED_REAL}

    @property
    def is_reconstructed(self) -> bool:
        return self in {
            self.RECONSTRUCTED_CYCLE,
            self.REPAIRED_RECONSTRUCTED,
        }

    @property
    def is_interpolated(self) -> bool:
        return self is self.INTERPOLATED_TRANSITION


class GenerationMethod(str, Enum):
    SOURCE_CYCLE = "source_cycle"
    SPECTRAL_RECONSTRUCTION = "spectral_reconstruction"
    DOMINANT_PARTIAL_RECONSTRUCTION = "dominant_partial_reconstruction"
    HYBRID_RECONSTRUCTION = "hybrid_reconstruction"
    XT_OPTIMIZATION = "xt_optimization"
    AUTO_REPAIR = "auto_repair"
    DETERMINISTIC_VARIANT = "deterministic_variant"
    WAVEFORM_INTERPOLATION = "waveform_interpolation"
    AMPLITUDE_INTERPOLATION = "amplitude_interpolation"
    PHASE_AWARE_INTERPOLATION = "phase_aware_interpolation"
    SPECTRAL_INTERPOLATION = "spectral_interpolation"
    HARMONIC_INTERPOLATION = "harmonic_interpolation"
    PERCEPTUAL_INTERPOLATION = "perceptual_interpolation"
    FIXED_REFERENCE = "fixed_reference"

    @property
    def is_interpolation(self) -> bool:
        return self in {
            self.WAVEFORM_INTERPOLATION,
            self.AMPLITUDE_INTERPOLATION,
            self.PHASE_AWARE_INTERPOLATION,
            self.SPECTRAL_INTERPOLATION,
            self.HARMONIC_INTERPOLATION,
            self.PERCEPTUAL_INTERPOLATION,
        }


class WaveRole(str, Enum):
    CANDIDATE = "candidate"
    STRUCTURAL = "structural"
    ESSENTIAL = "essential"
    STABLE = "stable"
    BREAKPOINT = "breakpoint"
    TRANSITION = "transition"
    REDUNDANT = "redundant"
    EXTREME = "extreme"
    FIXED = "fixed"


class ProgressionCurve(str, Enum):
    LINEAR = "linear"
    SMOOTHSTEP = "smoothstep"
    EXPONENTIAL = "exponential"
    LOGARITHMIC = "logarithmic"
    ADAPTIVE = "adaptive"


class WavetableBuildStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


class ConstraintStrength(str, Enum):
    PREFERENCE = "preference"
    REQUIRED = "required"


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def _finite(value: float, *, name: str) -> float:
    try:
        checked = float(value)
    except (TypeError, ValueError) as exc:
        raise WavetableContractError(f"{name} must be numeric") from exc
    if not math.isfinite(checked):
        raise WavetableContractError(f"{name} must be finite")
    return checked


def _ratio(value: float, *, name: str) -> float:
    checked = _finite(value, name=name)
    if not 0.0 <= checked <= 1.0:
        raise WavetableContractError(f"{name} must be between 0 and 1")
    return checked


def _normalized(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise WavetableContractError(f"{name} must be a normalized non-empty string")
    return value


def _identifier(value: str, *, name: str) -> str:
    checked = _normalized(value, name=name)
    if not _ID_RE.fullmatch(checked):
        raise WavetableContractError(f"{name} contains unsupported characters")
    return checked


def _hash(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _normalized_entries(
    values: Sequence[str], *, name: str, allow_empty: bool = True
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence of strings")
    result = tuple(_normalized(value, name=f"{name} entry") for value in values)
    if not allow_empty and not result:
        raise WavetableContractError(f"{name} must not be empty")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


def _boolean(value: bool, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise WavetableContractError(f"{name} must be a boolean")
    return value


def _enum(value: object, enum_type: type[Enum], *, name: str) -> Enum:
    if not isinstance(value, enum_type):
        raise WavetableContractError(f"{name} must be a {enum_type.__name__} value")
    return value


def _stored_samples(values: Sequence[int], *, name: str = "stored_samples") -> tuple[int, ...]:
    result = tuple(values)
    if len(result) != 64:
        raise WavetableContractError(f"{name} must contain exactly 64 samples")
    for sample in result:
        if isinstance(sample, bool) or not isinstance(sample, int):
            raise WavetableContractError(f"{name} must contain integers")
        if not SAFE_STORED_MIN <= sample <= SAFE_STORED_MAX:
            raise WavetableContractError(
                f"{name} must stay inside the safe generated range -127..127"
            )
    return result


def _validate_origin_method(
    origin: WaveOrigin, generation_method: GenerationMethod, *, label: str
) -> None:
    allowed: dict[WaveOrigin, frozenset[GenerationMethod]] = {
        WaveOrigin.REAL_CYCLE: frozenset({GenerationMethod.SOURCE_CYCLE}),
        WaveOrigin.RECONSTRUCTED_CYCLE: frozenset(
            {
                GenerationMethod.SPECTRAL_RECONSTRUCTION,
                GenerationMethod.DOMINANT_PARTIAL_RECONSTRUCTION,
                GenerationMethod.HYBRID_RECONSTRUCTION,
            }
        ),
        WaveOrigin.REPAIRED_REAL: frozenset({GenerationMethod.AUTO_REPAIR}),
        WaveOrigin.REPAIRED_RECONSTRUCTED: frozenset(
            {GenerationMethod.AUTO_REPAIR}
        ),
        WaveOrigin.GENERATED_VARIANT: frozenset(
            {GenerationMethod.DETERMINISTIC_VARIANT}
        ),
        WaveOrigin.INTERPOLATED_TRANSITION: frozenset(
            method for method in GenerationMethod if method.is_interpolation
        ),
        WaveOrigin.FIXED_REFERENCE: frozenset({GenerationMethod.FIXED_REFERENCE}),
    }
    if generation_method not in allowed[origin]:
        raise WavetableContractError(
            f"{label} origin and generation method are inconsistent"
        )


def reconstruct_xt_cycle(stored_samples: Sequence[int]) -> tuple[int, ...]:
    stored = _stored_samples(stored_samples)
    return stored + tuple(-sample for sample in reversed(stored))


def stored_samples_sha256(stored_samples: Sequence[int]) -> str:
    stored = _stored_samples(stored_samples)
    return sha256(bytes(sample + 128 for sample in stored)).hexdigest()


@dataclass(frozen=True, slots=True)
class WaveBuildMetrics:
    quality_score: float
    usefulness_score: float
    stability_score: float
    harmonic_richness: float
    brightness: float
    bass_power: float
    source_fidelity: float
    xt_compatibility: float
    perceptual_novelty: float
    reason: str

    def __post_init__(self) -> None:
        for name in (
            "quality_score",
            "usefulness_score",
            "stability_score",
            "harmonic_richness",
            "brightness",
            "bass_power",
            "source_fidelity",
            "xt_compatibility",
            "perceptual_novelty",
        ):
            _ratio(getattr(self, name), name=name)
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "quality_score": self.quality_score,
            "usefulness_score": self.usefulness_score,
            "stability_score": self.stability_score,
            "harmonic_richness": self.harmonic_richness,
            "brightness": self.brightness,
            "bass_power": self.bass_power,
            "source_fidelity": self.source_fidelity,
            "xt_compatibility": self.xt_compatibility,
            "perceptual_novelty": self.perceptual_novelty,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class WavetableCandidate:
    schema_version: int
    candidate_id: str
    source_artifact_sha256: str
    origin: WaveOrigin
    generation_method: GenerationMethod
    stored_samples: tuple[int, ...]
    metrics: WaveBuildMetrics
    source_time_seconds: float | None
    source_index: int | None
    structural_eligible: bool
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILD_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported candidate schema version")
        _identifier(self.candidate_id, name="candidate_id")
        _hash(self.source_artifact_sha256, name="source_artifact_sha256")
        _enum(self.origin, WaveOrigin, name="origin")
        _enum(self.generation_method, GenerationMethod, name="generation_method")
        object.__setattr__(self, "stored_samples", _stored_samples(self.stored_samples))
        if not isinstance(self.metrics, WaveBuildMetrics):
            raise WavetableContractError("metrics must be WaveBuildMetrics")
        if self.origin is WaveOrigin.FIXED_REFERENCE:
            raise WavetableContractError("fixed references are not candidate waves")
        _validate_origin_method(self.origin, self.generation_method, label="candidate")
        if self.source_time_seconds is not None and _finite(
            self.source_time_seconds, name="source_time_seconds"
        ) < 0.0:
            raise WavetableContractError("source_time_seconds must not be negative")
        if self.source_index is not None and (
            isinstance(self.source_index, bool)
            or not isinstance(self.source_index, int)
            or self.source_index < 0
        ):
            raise WavetableContractError("source_index must be a non-negative integer")
        _boolean(self.structural_eligible, name="structural_eligible")
        object.__setattr__(
            self,
            "evidence",
            _normalized_entries(self.evidence, name="evidence", allow_empty=False),
        )
        _normalized(self.reason, name="reason")

    @property
    def stored_samples_sha256(self) -> str:
        return stored_samples_sha256(self.stored_samples)

    @property
    def reconstructed_samples(self) -> tuple[int, ...]:
        return reconstruct_xt_cycle(self.stored_samples)

    @property
    def reconstructed_samples_sha256(self) -> str:
        payload = bytes(sample + 127 for sample in self.reconstructed_samples)
        return sha256(payload).hexdigest()

    @property
    def is_real(self) -> bool:
        return self.origin.is_real

    @property
    def is_reconstructed(self) -> bool:
        return self.origin.is_reconstructed

    @property
    def is_interpolated(self) -> bool:
        return self.origin.is_interpolated

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "source_artifact_sha256": self.source_artifact_sha256,
            "origin": self.origin.value,
            "generation_method": self.generation_method.value,
            "stored_samples": list(self.stored_samples),
            "stored_samples_sha256": self.stored_samples_sha256,
            "reconstructed_samples_sha256": self.reconstructed_samples_sha256,
            "metrics": self.metrics.to_dict(),
            "source_time_seconds": self.source_time_seconds,
            "source_index": self.source_index,
            "structural_eligible": self.structural_eligible,
            "evidence": list(self.evidence),
            "reason": self.reason,
            "is_real": self.is_real,
            "is_reconstructed": self.is_reconstructed,
            "is_interpolated": self.is_interpolated,
        }

    @property
    def candidate_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["candidate_sha256"] = self.candidate_sha256
        return result


@dataclass(frozen=True, slots=True)
class FixedTailContract:
    schema_version: int
    source_wctd_sha256: str
    references: tuple[int, int, int]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILD_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported fixed-tail schema version")
        _hash(self.source_wctd_sha256, name="source_wctd_sha256")
        references = tuple(self.references)
        object.__setattr__(self, "references", references)
        if len(references) != 3:
            raise WavetableContractError("fixed tail must contain exactly three references")
        for reference in references:
            if isinstance(reference, bool) or not isinstance(reference, int):
                raise WavetableContractError("fixed-tail references must be integers")
            if not 0 <= reference <= 0xFFFF:
                raise WavetableContractError("fixed-tail reference is outside uint16")
            if reference == INTERPOLATED_WAVE_REFERENCE:
                raise WavetableContractError("fixed-tail references must be explicit")
        _normalized(self.reason, name="reason")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_wctd_sha256": self.source_wctd_sha256,
            "positions": list(FIXED_TAIL_POSITIONS),
            "references": list(self.references),
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
class PositionLock:
    position: int
    candidate_id: str
    strength: ConstraintStrength
    reason: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.position, bool)
            or not isinstance(self.position, int)
            or not USER_POSITION_FIRST <= self.position <= USER_POSITION_LAST
        ):
            raise WavetableContractError("position lock must target integer user position 0..60")
        _identifier(self.candidate_id, name="candidate_id")
        _enum(self.strength, ConstraintStrength, name="strength")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "position": self.position,
            "display_position": self.position + 1,
            "candidate_id": self.candidate_id,
            "strength": self.strength.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ChronologyConstraint:
    before_candidate_id: str
    after_candidate_id: str
    strength: ConstraintStrength
    reason: str

    def __post_init__(self) -> None:
        _identifier(self.before_candidate_id, name="before_candidate_id")
        _identifier(self.after_candidate_id, name="after_candidate_id")
        if self.before_candidate_id == self.after_candidate_id:
            raise WavetableContractError("chronology constraint cannot reference one candidate twice")
        _enum(self.strength, ConstraintStrength, name="strength")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "before_candidate_id": self.before_candidate_id,
            "after_candidate_id": self.after_candidate_id,
            "strength": self.strength.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class WavetableBuildPolicy:
    schema_version: int
    user_position_count: int
    requested_variant_count: int
    progression_curve: ProgressionCurve
    allowed_interpolation_methods: tuple[GenerationMethod, ...]
    allow_mixed_provenance: bool
    preserve_chronology: bool
    allow_intentional_breaks: bool
    factory_style: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILD_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported build-policy schema version")
        if self.user_position_count != USER_POSITION_COUNT:
            raise WavetableContractError("generic XT builds require exactly 61 user positions")
        if isinstance(self.requested_variant_count, bool) or not isinstance(
            self.requested_variant_count, int
        ):
            raise WavetableContractError("requested_variant_count must be an integer")
        if not 1 <= self.requested_variant_count <= 16:
            raise WavetableContractError("requested_variant_count must be between 1 and 16")
        _enum(self.progression_curve, ProgressionCurve, name="progression_curve")
        methods = tuple(self.allowed_interpolation_methods)
        object.__setattr__(self, "allowed_interpolation_methods", methods)
        if not methods:
            raise WavetableContractError("at least one interpolation method is required")
        if any(not isinstance(method, GenerationMethod) for method in methods):
            raise WavetableContractError(
                "allowed interpolation methods must be GenerationMethod values"
            )
        if len(set(methods)) != len(methods):
            raise WavetableContractError("interpolation methods must be unique")
        if any(not method.is_interpolation for method in methods):
            raise WavetableContractError("allowed interpolation methods must be interpolation methods")
        for name in (
            "allow_mixed_provenance",
            "preserve_chronology",
            "allow_intentional_breaks",
            "factory_style",
        ):
            _boolean(getattr(self, name), name=name)
        _normalized(self.reason, name="reason")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "user_position_count": self.user_position_count,
            "requested_variant_count": self.requested_variant_count,
            "progression_curve": self.progression_curve.value,
            "allowed_interpolation_methods": [
                method.value for method in self.allowed_interpolation_methods
            ],
            "allow_mixed_provenance": self.allow_mixed_provenance,
            "preserve_chronology": self.preserve_chronology,
            "allow_intentional_breaks": self.allow_intentional_breaks,
            "factory_style": self.factory_style,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _validate_required_constraints(
    locks: Sequence[PositionLock],
    chronology: Sequence[ChronologyConstraint],
) -> None:
    required_edges = tuple(
        (item.before_candidate_id, item.after_candidate_id)
        for item in chronology
        if item.strength is ConstraintStrength.REQUIRED
    )
    graph: dict[str, set[str]] = {}
    for before, after in required_edges:
        graph.setdefault(before, set()).add(after)
        graph.setdefault(after, set())

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise WavetableContractError(
                "required chronology constraints contain a cycle"
            )
        if node in visited:
            return
        visiting.add(node)
        for successor in sorted(graph.get(node, ())):
            visit(successor)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)

    required_locks = {
        lock.candidate_id: lock.position
        for lock in locks
        if lock.strength is ConstraintStrength.REQUIRED
    }
    for start in sorted(graph):
        reachable: set[str] = set()
        pending = list(graph.get(start, ()))
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(graph.get(current, ()))
        if start not in required_locks:
            continue
        for end in reachable:
            if end in required_locks and required_locks[start] >= required_locks[end]:
                raise WavetableContractError(
                    "required position locks contradict required chronology"
                )


@dataclass(frozen=True, slots=True)
class WavetableBuildRequest:
    schema_version: int
    tool_version: str
    preflight_analysis_sha256: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    selected_mode: str
    selected_profile: str
    candidates: tuple[WavetableCandidate, ...]
    fixed_tail: FixedTailContract
    policy: WavetableBuildPolicy
    position_locks: tuple[PositionLock, ...]
    chronology_constraints: tuple[ChronologyConstraint, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILD_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported build-request schema version")
        _normalized(self.tool_version, name="tool_version")
        _hash(self.preflight_analysis_sha256, name="preflight_analysis_sha256")
        if (
            isinstance(self.sample_rate, bool)
            or not isinstance(self.sample_rate, int)
            or isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or self.sample_rate <= 0
            or self.sample_count <= 0
        ):
            raise WavetableContractError(
                "sample_rate and sample_count must be positive integers"
            )
        _hash(self.sample_sha256, name="sample_sha256")
        _normalized(self.selected_mode, name="selected_mode")
        _normalized(self.selected_profile, name="selected_profile")
        candidates = tuple(self.candidates)
        locks = tuple(self.position_locks)
        chronology = tuple(self.chronology_constraints)
        warnings = _normalized_entries(self.warnings, name="warnings")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "position_locks", locks)
        object.__setattr__(self, "chronology_constraints", chronology)
        object.__setattr__(self, "warnings", warnings)
        if not isinstance(self.fixed_tail, FixedTailContract):
            raise WavetableContractError("fixed_tail must be FixedTailContract")
        if not isinstance(self.policy, WavetableBuildPolicy):
            raise WavetableContractError("policy must be WavetableBuildPolicy")
        if not candidates:
            raise WavetableContractError("at least one candidate is required")
        if any(not isinstance(candidate, WavetableCandidate) for candidate in candidates):
            raise WavetableContractError("candidates must be WavetableCandidate values")
        if any(not isinstance(lock, PositionLock) for lock in locks):
            raise WavetableContractError("position_locks must contain PositionLock values")
        if any(not isinstance(item, ChronologyConstraint) for item in chronology):
            raise WavetableContractError(
                "chronology_constraints must contain ChronologyConstraint values"
            )
        candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise WavetableContractError("candidate IDs must be unique")
        lock_positions = tuple(lock.position for lock in self.position_locks)
        if len(set(lock_positions)) != len(lock_positions):
            raise WavetableContractError("position locks must target unique positions")
        if any(lock.candidate_id not in candidate_ids for lock in self.position_locks):
            raise WavetableContractError("position lock references an unknown candidate")
        chronology_pairs = tuple(
            (constraint.before_candidate_id, constraint.after_candidate_id)
            for constraint in self.chronology_constraints
        )
        if len(set(chronology_pairs)) != len(chronology_pairs):
            raise WavetableContractError("chronology constraints must be unique")
        if any(
            left not in candidate_ids or right not in candidate_ids
            for left, right in chronology_pairs
        ):
            raise WavetableContractError("chronology constraint references an unknown candidate")
        if not self.policy.allow_mixed_provenance and self.mixed_provenance:
            raise WavetableContractError("policy forbids mixed real/reconstructed provenance")
        _validate_required_constraints(locks, chronology)
        _normalized(self.reason, name="reason")

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def real_candidate_count(self) -> int:
        return sum(candidate.is_real for candidate in self.candidates)

    @property
    def reconstructed_candidate_count(self) -> int:
        return sum(candidate.is_reconstructed for candidate in self.candidates)

    @property
    def mixed_provenance(self) -> bool:
        return self.real_candidate_count > 0 and self.reconstructed_candidate_count > 0

    @property
    def candidate_sha256(self) -> tuple[str, ...]:
        return tuple(candidate.candidate_sha256 for candidate in self.candidates)

    @property
    def candidate_inventory_sha256(self) -> str:
        return _canonical_hash(
            {
                "candidate_sha256": list(self.candidate_sha256),
                "candidate_ids": [candidate.candidate_id for candidate in self.candidates],
            }
        )

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "preflight_analysis_sha256": self.preflight_analysis_sha256,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "selected_mode": self.selected_mode,
            "selected_profile": self.selected_profile,
            "candidate_count": self.candidate_count,
            "real_candidate_count": self.real_candidate_count,
            "reconstructed_candidate_count": self.reconstructed_candidate_count,
            "mixed_provenance": self.mixed_provenance,
            "candidate_inventory_sha256": self.candidate_inventory_sha256,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "fixed_tail": self.fixed_tail.to_dict(),
            "policy": self.policy.to_dict(),
            "position_locks": [lock.to_dict() for lock in self.position_locks],
            "chronology_constraints": [
                constraint.to_dict() for constraint in self.chronology_constraints
            ],
            "warnings": list(self.warnings),
            "reason": self.reason,
            "boundaries": {
                "selects_structural_waves": False,
                "orders_candidates": False,
                "interpolates_transitions": False,
                "materializes_wctd": False,
                "allocates_xt_memory": False,
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
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"


@dataclass(frozen=True, slots=True)
class WavetableSlot:
    schema_version: int
    position: int
    stored_samples: tuple[int, ...]
    role: WaveRole
    origin: WaveOrigin
    generation_method: GenerationMethod
    metrics: WaveBuildMetrics
    source_candidate_ids: tuple[str, ...]
    source_time_seconds: float | None
    locked: bool
    structural: bool
    transition: bool
    redundant: bool
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILD_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported slot schema version")
        if (
            isinstance(self.position, bool)
            or not isinstance(self.position, int)
            or not USER_POSITION_FIRST <= self.position <= USER_POSITION_LAST
        ):
            raise WavetableContractError("slot position must be an integer between 0 and 60")
        object.__setattr__(self, "stored_samples", _stored_samples(self.stored_samples))
        _enum(self.role, WaveRole, name="role")
        _enum(self.origin, WaveOrigin, name="origin")
        _enum(self.generation_method, GenerationMethod, name="generation_method")
        if not isinstance(self.metrics, WaveBuildMetrics):
            raise WavetableContractError("metrics must be WaveBuildMetrics")
        if self.origin is WaveOrigin.FIXED_REFERENCE:
            raise WavetableContractError("fixed references cannot occupy user slots")
        _validate_origin_method(self.origin, self.generation_method, label="slot")
        source_ids = tuple(
            _identifier(value, name="source_candidate_id")
            for value in self.source_candidate_ids
        )
        object.__setattr__(self, "source_candidate_ids", source_ids)
        if not source_ids:
            raise WavetableContractError("slot must reference at least one candidate")
        if len(set(source_ids)) != len(source_ids):
            raise WavetableContractError("slot source candidate IDs must be unique")
        for name in ("locked", "structural", "transition", "redundant"):
            _boolean(getattr(self, name), name=name)
        if self.transition != (self.role is WaveRole.TRANSITION):
            raise WavetableContractError("transition flag must match role")
        if self.redundant != (self.role is WaveRole.REDUNDANT):
            raise WavetableContractError("redundant flag must match role")
        if self.role in {WaveRole.STRUCTURAL, WaveRole.ESSENTIAL, WaveRole.BREAKPOINT, WaveRole.EXTREME} and not self.structural:
            raise WavetableContractError("structural role requires structural=True")
        if self.transition and len(source_ids) < 2:
            raise WavetableContractError("transition slots require at least two source candidates")
        if self.source_time_seconds is not None and _finite(
            self.source_time_seconds, name="source_time_seconds"
        ) < 0.0:
            raise WavetableContractError("source_time_seconds must not be negative")
        object.__setattr__(
            self,
            "evidence",
            _normalized_entries(self.evidence, name="evidence", allow_empty=False),
        )
        _normalized(self.reason, name="reason")

    @property
    def stored_samples_sha256(self) -> str:
        return stored_samples_sha256(self.stored_samples)

    @property
    def reconstructed_samples_sha256(self) -> str:
        return sha256(
            bytes(sample + 127 for sample in reconstruct_xt_cycle(self.stored_samples))
        ).hexdigest()

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "position": self.position,
            "display_position": self.position + 1,
            "stored_samples": list(self.stored_samples),
            "stored_samples_sha256": self.stored_samples_sha256,
            "reconstructed_samples_sha256": self.reconstructed_samples_sha256,
            "role": self.role.value,
            "origin": self.origin.value,
            "generation_method": self.generation_method.value,
            "metrics": self.metrics.to_dict(),
            "source_candidate_ids": list(self.source_candidate_ids),
            "source_time_seconds": self.source_time_seconds,
            "locked": self.locked,
            "structural": self.structural,
            "transition": self.transition,
            "redundant": self.redundant,
            "real": self.origin.is_real,
            "interpolated": self.origin.is_interpolated,
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def slot_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["slot_sha256"] = self.slot_sha256
        return result


@dataclass(frozen=True, slots=True)
class WavetableBuild:
    schema_version: int
    tool_version: str
    request_sha256: str
    preflight_analysis_sha256: str
    variant_id: str
    status: WavetableBuildStatus
    slots: tuple[WavetableSlot, ...]
    fixed_tail: FixedTailContract
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILD_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported build schema version")
        _normalized(self.tool_version, name="tool_version")
        _hash(self.request_sha256, name="request_sha256")
        _hash(self.preflight_analysis_sha256, name="preflight_analysis_sha256")
        _identifier(self.variant_id, name="variant_id")
        _enum(self.status, WavetableBuildStatus, name="status")
        slots = tuple(self.slots)
        object.__setattr__(self, "slots", slots)
        if any(not isinstance(slot, WavetableSlot) for slot in slots):
            raise WavetableContractError("slots must contain WavetableSlot values")
        if not isinstance(self.fixed_tail, FixedTailContract):
            raise WavetableContractError("fixed_tail must be FixedTailContract")
        object.__setattr__(
            self, "blockers", _normalized_entries(self.blockers, name="blockers")
        )
        object.__setattr__(
            self, "warnings", _normalized_entries(self.warnings, name="warnings")
        )
        _normalized(self.reason, name="reason")
        if self.status is WavetableBuildStatus.COMPLETE:
            if self.blockers:
                raise WavetableContractError("complete build cannot contain blockers")
            if len(self.slots) != USER_POSITION_COUNT:
                raise WavetableContractError("complete build requires exactly 61 slots")
            positions = tuple(slot.position for slot in self.slots)
            if positions != tuple(range(USER_POSITION_COUNT)):
                raise WavetableContractError("slots must use canonical position order 0..60")
            if not self.structural_positions:
                raise WavetableContractError("complete build requires structural positions")
            if not self.essential_positions:
                raise WavetableContractError("complete build requires essential positions")
        else:
            if not self.blockers:
                raise WavetableContractError("rejected build requires explicit blockers")
            if self.slots:
                raise WavetableContractError("rejected build must not expose slots")

    @property
    def structural_positions(self) -> tuple[int, ...]:
        return tuple(slot.position for slot in self.slots if slot.structural)

    @property
    def essential_positions(self) -> tuple[int, ...]:
        return tuple(
            slot.position for slot in self.slots if slot.role is WaveRole.ESSENTIAL
        )

    @property
    def transition_positions(self) -> tuple[int, ...]:
        return tuple(slot.position for slot in self.slots if slot.transition)

    @property
    def redundant_positions(self) -> tuple[int, ...]:
        return tuple(slot.position for slot in self.slots if slot.redundant)

    @property
    def distinct_wave_count(self) -> int:
        return len({slot.stored_samples_sha256 for slot in self.slots})

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "request_sha256": self.request_sha256,
            "preflight_analysis_sha256": self.preflight_analysis_sha256,
            "variant_id": self.variant_id,
            "status": self.status.value,
            "slots": [slot.to_dict() for slot in self.slots],
            "fixed_tail": self.fixed_tail.to_dict(),
            "structural_positions": list(self.structural_positions),
            "essential_positions": list(self.essential_positions),
            "transition_positions": list(self.transition_positions),
            "redundant_positions": list(self.redundant_positions),
            "distinct_wave_count": self.distinct_wave_count,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "reason": self.reason,
            "boundaries": {
                "wctd_materialized": False,
                "xt_memory_allocated": False,
                "sysex_generated": False,
                "midi_opened": False,
                "midi_transmitted": False,
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
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"


@dataclass(frozen=True, slots=True)
class WavetableBuildSet:
    schema_version: int
    request_sha256: str
    builds: tuple[WavetableBuild, ...]
    primary_variant_id: str
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_BUILD_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported build-set schema version")
        _hash(self.request_sha256, name="request_sha256")
        builds = tuple(self.builds)
        object.__setattr__(self, "builds", builds)
        if not builds:
            raise WavetableContractError("build set must contain at least one build")
        if any(not isinstance(build, WavetableBuild) for build in builds):
            raise WavetableContractError("builds must contain WavetableBuild values")
        if any(build.request_sha256 != self.request_sha256 for build in builds):
            raise WavetableContractError("all builds must link to the same request")
        variant_ids = tuple(build.variant_id for build in builds)
        if len(set(variant_ids)) != len(variant_ids):
            raise WavetableContractError("build variant IDs must be unique")
        if self.primary_variant_id not in variant_ids:
            raise WavetableContractError("primary_variant_id is not present")
        primary = next(build for build in builds if build.variant_id == self.primary_variant_id)
        if any(build.status is WavetableBuildStatus.COMPLETE for build in builds) and (
            primary.status is not WavetableBuildStatus.COMPLETE
        ):
            raise WavetableContractError(
                "primary variant must be complete when a complete variant exists"
            )
        _normalized(self.reason, name="reason")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request_sha256,
            "builds": [build.to_dict() for build in self.builds],
            "primary_variant_id": self.primary_variant_id,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"
