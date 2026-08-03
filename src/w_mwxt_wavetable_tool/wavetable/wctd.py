from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from .factory_style import FactoryStyleAnalysis, FactoryStyleStatus
from .models import (
    FIXED_TAIL_POSITIONS,
    INTERPOLATED_WAVE_REFERENCE,
    USER_POSITION_COUNT,
    WCTD_POSITION_COUNT,
    WavetableBuild,
    WavetableBuildStatus,
    WavetableContractError,
)

WCTD_MODEL_SCHEMA_VERSION = 1


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


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


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


class WctdReferenceKind(str, Enum):
    USER_SLOT = "user_slot"
    FIXED_TAIL = "fixed_tail"


class WctdMaterializationStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class WctdReference:
    schema_version: int
    position: int
    kind: WctdReferenceKind
    reference: int
    resolved: bool
    slot_sha256: str | None
    source_candidate_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WCTD_MODEL_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported WCTD reference schema version")
        if isinstance(self.position, bool) or not isinstance(self.position, int) or not 0 <= self.position < WCTD_POSITION_COUNT:
            raise WavetableContractError("WCTD position must be an integer in 0..63")
        if not isinstance(self.kind, WctdReferenceKind):
            raise WavetableContractError("kind must be WctdReferenceKind")
        if isinstance(self.reference, bool) or not isinstance(self.reference, int) or not 0 <= self.reference <= 0xFFFF:
            raise WavetableContractError("reference must be an unsigned 16-bit integer")
        if not isinstance(self.resolved, bool):
            raise WavetableContractError("resolved must be boolean")
        if self.kind is WctdReferenceKind.USER_SLOT:
            if not 0 <= self.position < USER_POSITION_COUNT:
                raise WavetableContractError("user-slot WCTD reference must target position 0..60")
            if self.slot_sha256 is None:
                raise WavetableContractError("user-slot WCTD reference requires slot_sha256")
            _sha256(self.slot_sha256, name="slot_sha256")
            if self.resolved and self.reference == INTERPOLATED_WAVE_REFERENCE:
                raise WavetableContractError("resolved user reference cannot use the unresolved marker")
            if not self.resolved and self.reference != INTERPOLATED_WAVE_REFERENCE:
                raise WavetableContractError("unresolved user reference must use the unresolved marker")
        else:
            if self.position not in FIXED_TAIL_POSITIONS:
                raise WavetableContractError("fixed-tail WCTD reference must target position 61..63")
            if not self.resolved or self.reference == INTERPOLATED_WAVE_REFERENCE:
                raise WavetableContractError("fixed-tail references must be explicit and resolved")
            if self.slot_sha256 is not None:
                raise WavetableContractError("fixed-tail references do not link to user slots")
        ids = tuple(self.source_candidate_ids)
        object.__setattr__(self, "source_candidate_ids", ids)
        if self.kind is WctdReferenceKind.USER_SLOT and not ids:
            raise WavetableContractError("user-slot references require source candidate IDs")
        if self.kind is WctdReferenceKind.FIXED_TAIL and ids:
            raise WavetableContractError("fixed-tail references cannot claim candidate IDs")
        if len(set(ids)) != len(ids):
            raise WavetableContractError("source candidate IDs must be unique")
        for item in ids:
            _normalized(item, name="source_candidate_id")
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
            "kind": self.kind.value,
            "reference": self.reference,
            "reference_hex": f"0x{self.reference:04X}",
            "resolved": self.resolved,
            "slot_sha256": self.slot_sha256,
            "source_candidate_ids": list(self.source_candidate_ids),
            "evidence": list(self.evidence),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class WctdReferenceModel:
    schema_version: int
    variant_id: str
    build_sha256: str
    fixed_tail_sha256: str
    source_wctd_sha256: str
    entries: tuple[WctdReference, ...]
    reference_payload_sha256: str
    binary_ready: bool
    unresolved_user_positions: tuple[int, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WCTD_MODEL_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported WCTD model schema version")
        _normalized(self.variant_id, name="variant_id")
        for name in ("build_sha256", "fixed_tail_sha256", "source_wctd_sha256", "reference_payload_sha256"):
            _sha256(getattr(self, name), name=name)
        entries = tuple(self.entries)
        object.__setattr__(self, "entries", entries)
        if len(entries) != WCTD_POSITION_COUNT:
            raise WavetableContractError("WCTD model requires exactly 64 reference entries")
        if tuple(item.position for item in entries) != tuple(range(WCTD_POSITION_COUNT)):
            raise WavetableContractError("WCTD references must use canonical position order 0..63")
        if not isinstance(self.binary_ready, bool):
            raise WavetableContractError("binary_ready must be boolean")
        unresolved = tuple(self.unresolved_user_positions)
        object.__setattr__(self, "unresolved_user_positions", unresolved)
        expected = tuple(item.position for item in entries if not item.resolved)
        if unresolved != expected:
            raise WavetableContractError("unresolved_user_positions disagree with entries")
        if any(position >= USER_POSITION_COUNT for position in unresolved):
            raise WavetableContractError("only user positions may remain unresolved")
        if self.binary_ready != (not unresolved):
            raise WavetableContractError("binary_ready disagrees with unresolved references")
        payload = b"".join(item.reference.to_bytes(2, "big") for item in entries)
        if sha256(payload).hexdigest() != self.reference_payload_sha256:
            raise WavetableContractError("reference_payload_sha256 disagrees with entries")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        _normalized(self.reason, name="reason")

    @property
    def user_entries(self) -> tuple[WctdReference, ...]:
        return self.entries[:USER_POSITION_COUNT]

    @property
    def fixed_tail_entries(self) -> tuple[WctdReference, ...]:
        return self.entries[USER_POSITION_COUNT:]

    @property
    def reference_words(self) -> tuple[int, ...]:
        return tuple(item.reference for item in self.entries)

    def reference_payload(self) -> bytes:
        return b"".join(item.to_bytes(2, "big") for item in self.reference_words)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "build_sha256": self.build_sha256,
            "fixed_tail_sha256": self.fixed_tail_sha256,
            "source_wctd_sha256": self.source_wctd_sha256,
            "entries": [item.to_dict() for item in self.entries],
            "reference_words": list(self.reference_words),
            "reference_payload_sha256": self.reference_payload_sha256,
            "binary_ready": self.binary_ready,
            "unresolved_user_positions": list(self.unresolved_user_positions),
            "display_unresolved_user_positions": [item + 1 for item in self.unresolved_user_positions],
            "warnings": list(self.warnings),
            "reason": self.reason,
            "boundaries": {
                "reference_model_only": True,
                "serializes_complete_wctd_dump": False,
                "generates_sysex": False,
                "allocates_xt_memory": False,
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


@dataclass(frozen=True, slots=True)
class WctdMaterializationSet:
    schema_version: int
    status: WctdMaterializationStatus
    factory_style_analysis_sha256: str
    models: tuple[WctdReferenceModel, ...]
    primary_variant_id: str | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WCTD_MODEL_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported WCTD set schema version")
        if not isinstance(self.status, WctdMaterializationStatus):
            raise WavetableContractError("status must be WctdMaterializationStatus")
        _sha256(self.factory_style_analysis_sha256, name="factory_style_analysis_sha256")
        models = tuple(self.models)
        object.__setattr__(self, "models", models)
        if len({item.variant_id for item in models}) != len(models):
            raise WavetableContractError("WCTD model variant IDs must be unique")
        object.__setattr__(self, "warnings", _entries(self.warnings, name="warnings"))
        object.__setattr__(self, "blockers", _entries(self.blockers, name="blockers"))
        _normalized(self.reason, name="reason")
        if self.status is WctdMaterializationStatus.COMPLETE:
            if self.blockers:
                raise WavetableContractError("complete WCTD set cannot contain blockers")
            if not models or self.primary_variant_id is None:
                raise WavetableContractError("complete WCTD set requires models")
            if self.primary_variant_id not in {item.variant_id for item in models}:
                raise WavetableContractError("primary WCTD variant is absent")
        else:
            if not self.blockers:
                raise WavetableContractError("rejected WCTD set requires blockers")
            if models or self.primary_variant_id is not None:
                raise WavetableContractError("rejected WCTD set cannot expose partial models")

    @property
    def primary_model(self) -> WctdReferenceModel | None:
        if self.primary_variant_id is None:
            return None
        return next(item for item in self.models if item.variant_id == self.primary_variant_id)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "factory_style_analysis_sha256": self.factory_style_analysis_sha256,
            "models": [item.to_dict() for item in self.models],
            "primary_variant_id": self.primary_variant_id,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _user_references(values: Sequence[int] | None) -> tuple[int, ...] | None:
    if values is None:
        return None
    result = tuple(values)
    if len(result) != USER_POSITION_COUNT:
        raise WavetableContractError("user_references must contain exactly 61 values")
    for value in result:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF:
            raise WavetableContractError("user reference is outside uint16")
        if value == INTERPOLATED_WAVE_REFERENCE:
            raise WavetableContractError("resolved user references cannot use 0xFFFF")
    if len(set(result)) != len(result):
        raise WavetableContractError("resolved user references must be unique")
    return result


def materialize_wctd_reference_model(
    build: WavetableBuild,
    user_references: Sequence[int] | None = None,
) -> WctdReferenceModel:
    """Materialize one canonical 64-entry WCTD reference model without SysEx."""

    if not isinstance(build, WavetableBuild) or build.status is not WavetableBuildStatus.COMPLETE:
        raise WavetableContractError("WCTD materialization requires a complete build")
    if len(build.slots) != USER_POSITION_COUNT:
        raise WavetableContractError("WCTD materialization requires exactly 61 user slots")
    resolved = _user_references(user_references)
    entries: list[WctdReference] = []
    for slot in build.slots:
        reference = INTERPOLATED_WAVE_REFERENCE if resolved is None else resolved[slot.position]
        entries.append(
            WctdReference(
                schema_version=WCTD_MODEL_SCHEMA_VERSION,
                position=slot.position,
                kind=WctdReferenceKind.USER_SLOT,
                reference=reference,
                resolved=resolved is not None,
                slot_sha256=slot.slot_sha256,
                source_candidate_ids=slot.source_candidate_ids,
                evidence=(f"build {build.analysis_sha256}", f"slot {slot.slot_sha256}"),
                reason=(
                    "Logical user-wave reference awaiting an externally confirmed allocation."
                    if resolved is None
                    else "User-wave reference supplied by an explicit external allocation."
                ),
            )
        )
    for position, reference in zip(FIXED_TAIL_POSITIONS, build.fixed_tail.references):
        entries.append(
            WctdReference(
                schema_version=WCTD_MODEL_SCHEMA_VERSION,
                position=position,
                kind=WctdReferenceKind.FIXED_TAIL,
                reference=reference,
                resolved=True,
                slot_sha256=None,
                source_candidate_ids=(),
                evidence=(
                    f"fixed-tail contract {build.fixed_tail.analysis_sha256}",
                    f"source WCTD {build.fixed_tail.source_wctd_sha256}",
                ),
                reason="Exact fixed-tail reference preserved from the accepted source WCTD contract.",
            )
        )
    entries_tuple = tuple(entries)
    payload = b"".join(item.reference.to_bytes(2, "big") for item in entries_tuple)
    unresolved = tuple(item.position for item in entries_tuple if not item.resolved)
    warnings = () if not unresolved else (
        "61 user-wave references remain logical until an external allocation is supplied",
    )
    return WctdReferenceModel(
        schema_version=WCTD_MODEL_SCHEMA_VERSION,
        variant_id=build.variant_id,
        build_sha256=build.analysis_sha256,
        fixed_tail_sha256=build.fixed_tail.analysis_sha256,
        source_wctd_sha256=build.fixed_tail.source_wctd_sha256,
        entries=entries_tuple,
        reference_payload_sha256=sha256(payload).hexdigest(),
        binary_ready=not unresolved,
        unresolved_user_positions=unresolved,
        warnings=warnings,
        reason="Canonical 64-entry WCTD reference model; not a SysEx packet or memory allocation.",
    )


def materialize_wctd_models(
    factory_style: FactoryStyleAnalysis,
    allocations: Mapping[str, Sequence[int]] | None = None,
) -> WctdMaterializationSet:
    """Materialize WCTD reference models for every complete Factory Style variant."""

    if not isinstance(factory_style, FactoryStyleAnalysis):
        raise WavetableContractError("factory_style must be FactoryStyleAnalysis")
    if allocations is not None and not isinstance(allocations, Mapping):
        raise WavetableContractError("allocations must be a mapping")
    if factory_style.status is not FactoryStyleStatus.COMPLETE:
        return WctdMaterializationSet(
            schema_version=WCTD_MODEL_SCHEMA_VERSION,
            status=WctdMaterializationStatus.REJECTED,
            factory_style_analysis_sha256=factory_style.analysis_sha256,
            models=(),
            primary_variant_id=None,
            warnings=tuple(factory_style.warnings),
            blockers=tuple(factory_style.blockers) or ("Factory Style analysis is rejected",),
            reason="WCTD materialization rejected the input without partial models.",
        )
    allocation_map = {} if allocations is None else dict(allocations)
    unknown = sorted(set(allocation_map) - {item.variant_id for item in factory_style.variants})
    if unknown:
        raise WavetableContractError(f"allocations reference unknown variants: {unknown}")
    models = tuple(
        materialize_wctd_reference_model(
            variant.build,
            allocation_map.get(variant.variant_id),
        )
        for variant in factory_style.variants
    )
    warnings = tuple(dict.fromkeys(factory_style.warnings + tuple(w for model in models for w in model.warnings)))
    return WctdMaterializationSet(
        schema_version=WCTD_MODEL_SCHEMA_VERSION,
        status=WctdMaterializationStatus.COMPLETE,
        factory_style_analysis_sha256=factory_style.analysis_sha256,
        models=models,
        primary_variant_id=factory_style.primary_variant_id,
        warnings=warnings,
        blockers=(),
        reason="Canonical WCTD reference models materialized without SysEx or XT memory access.",
    )


__all__ = [
    "WCTD_MODEL_SCHEMA_VERSION",
    "WctdMaterializationSet",
    "WctdMaterializationStatus",
    "WctdReference",
    "WctdReferenceKind",
    "WctdReferenceModel",
    "materialize_wctd_models",
    "materialize_wctd_reference_model",
]
