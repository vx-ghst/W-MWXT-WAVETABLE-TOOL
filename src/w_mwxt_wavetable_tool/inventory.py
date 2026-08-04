from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from .constants import (
    INTERPOLATED_WAVE_REFERENCE,
    USER_WAVE_CAPACITY,
    USER_WAVE_FIRST,
    USER_WAVE_LAST,
    USER_WAVETABLE_DISPLAY_FIRST,
    USER_WAVETABLE_DISPLAY_LAST,
    DumpType,
)
from .dump import DumpFile
from .errors import ProtocolError
from .models import UserWave, UserWavetable

XT_MEMORY_INVENTORY_SCHEMA_VERSION = 1


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
        raise ProtocolError(f"{name} must be a normalized non-empty string")
    return value


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ProtocolError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _strings(values: Sequence[str], *, name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise ProtocolError(f"{name} must be a sequence")
    result = tuple(values)
    if not allow_empty and not result:
        raise ProtocolError(f"{name} must not be empty")
    if any(not isinstance(item, str) or not item for item in result):
        raise ProtocolError(f"{name} must contain non-empty strings")
    if len(set(result)) != len(result):
        raise ProtocolError(f"{name} must not contain duplicates")
    return result


def _samples_hash(samples: Sequence[int]) -> str:
    values = tuple(samples)
    if len(values) != 64 or any(
        isinstance(item, bool) or not isinstance(item, int) or not -128 <= item <= 127
        for item in values
    ):
        raise ProtocolError("empty-wave signature must contain 64 int8 samples")
    return sha256(bytes((value + 256) % 256 for value in values)).hexdigest()


class InventoryState(str, Enum):
    USED = "used"
    SAFE_FREE = "safe_free"
    ORPHANED = "orphaned"
    UNKNOWN = "unknown"


class InventorySourceKind(str, Enum):
    BACKUP_EVERYTHING = "backup_everything"
    ALL_WAVETABLES_WAVES = "all_wavetables_waves"
    CURRENT_EXTERNAL_CAPTURE = "current_external_capture"
    OTHER_EXTERNAL_DUMP = "other_external_dump"


class InventoryPresence(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    CONFLICTED = "conflicted"


@dataclass(frozen=True, slots=True)
class InventoryDumpSource:
    source_id: str
    source_kind: InventorySourceKind
    dump: DumpFile
    captured_current_state: bool = False

    def __post_init__(self) -> None:
        _normalized(self.source_id, name="source_id")
        if not isinstance(self.source_kind, InventorySourceKind):
            raise ProtocolError("source_kind must be InventorySourceKind")
        if not isinstance(self.dump, DumpFile):
            raise ProtocolError("dump must be DumpFile")
        if not isinstance(self.captured_current_state, bool):
            raise ProtocolError("captured_current_state must be boolean")

    @property
    def dump_sha256(self) -> str:
        return sha256(self.dump.to_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class InventorySourceEvidence:
    schema_version: int
    source_id: str
    source_kind: InventorySourceKind
    dump_sha256: str
    message_count: int
    user_wave_numbers: tuple[int, ...]
    user_wavetable_display_numbers: tuple[int, ...]
    captured_current_state: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != XT_MEMORY_INVENTORY_SCHEMA_VERSION:
            raise ProtocolError("Unsupported inventory source evidence schema version")
        _normalized(self.source_id, name="source_id")
        if not isinstance(self.source_kind, InventorySourceKind):
            raise ProtocolError("source_kind must be InventorySourceKind")
        _sha256(self.dump_sha256, name="dump_sha256")
        if isinstance(self.message_count, bool) or not isinstance(self.message_count, int) or self.message_count < 0:
            raise ProtocolError("message_count must be a non-negative integer")
        waves = tuple(self.user_wave_numbers)
        tables = tuple(self.user_wavetable_display_numbers)
        object.__setattr__(self, "user_wave_numbers", waves)
        object.__setattr__(self, "user_wavetable_display_numbers", tables)
        if tuple(sorted(set(waves))) != waves or any(not USER_WAVE_FIRST <= item <= USER_WAVE_LAST for item in waves):
            raise ProtocolError("user_wave_numbers must be sorted unique XT User Wave numbers")
        if tuple(sorted(set(tables))) != tables or any(
            not USER_WAVETABLE_DISPLAY_FIRST <= item <= USER_WAVETABLE_DISPLAY_LAST for item in tables
        ):
            raise ProtocolError("user_wavetable_display_numbers must be sorted unique display numbers")
        if not isinstance(self.captured_current_state, bool):
            raise ProtocolError("captured_current_state must be boolean")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "dump_sha256": self.dump_sha256,
            "message_count": self.message_count,
            "user_wave_numbers": list(self.user_wave_numbers),
            "user_wavetable_display_numbers": list(self.user_wavetable_display_numbers),
            "captured_current_state": self.captured_current_state,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ValidatedEmptyWaveSignature:
    schema_version: int
    stored_samples: tuple[int, ...]
    hardware_evidence_sha256: str
    evidence_ids: tuple[str, ...]
    validated_on_hardware: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != XT_MEMORY_INVENTORY_SCHEMA_VERSION:
            raise ProtocolError("Unsupported empty-wave signature schema version")
        values = tuple(self.stored_samples)
        _samples_hash(values)
        object.__setattr__(self, "stored_samples", values)
        _sha256(self.hardware_evidence_sha256, name="hardware_evidence_sha256")
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids, name="evidence_ids", allow_empty=False))
        if not isinstance(self.validated_on_hardware, bool):
            raise ProtocolError("validated_on_hardware must be boolean")
        _normalized(self.reason, name="reason")

    @property
    def stored_samples_sha256(self) -> str:
        return _samples_hash(self.stored_samples)

    @property
    def safe_free_eligible(self) -> bool:
        return self.validated_on_hardware

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "stored_samples_sha256": self.stored_samples_sha256,
            "hardware_evidence_sha256": self.hardware_evidence_sha256,
            "evidence_ids": list(self.evidence_ids),
            "validated_on_hardware": self.validated_on_hardware,
            "safe_free_eligible": self.safe_free_eligible,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class InventoryEvidenceStatus:
    schema_version: int
    user_wave_coverage_complete: bool
    user_wavetable_coverage_complete: bool
    user_wave_conflicts: tuple[int, ...]
    user_wavetable_conflicts: tuple[int, ...]
    empty_signature_validated: bool
    safe_free_enabled: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != XT_MEMORY_INVENTORY_SCHEMA_VERSION:
            raise ProtocolError("Unsupported inventory evidence status schema version")
        for name in (
            "user_wave_coverage_complete",
            "user_wavetable_coverage_complete",
            "empty_signature_validated",
            "safe_free_enabled",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ProtocolError(f"{name} must be boolean")
        wave_conflicts = tuple(self.user_wave_conflicts)
        table_conflicts = tuple(self.user_wavetable_conflicts)
        object.__setattr__(self, "user_wave_conflicts", wave_conflicts)
        object.__setattr__(self, "user_wavetable_conflicts", table_conflicts)
        if tuple(sorted(set(wave_conflicts))) != wave_conflicts:
            raise ProtocolError("user_wave_conflicts must be sorted and unique")
        if tuple(sorted(set(table_conflicts))) != table_conflicts:
            raise ProtocolError("user_wavetable_conflicts must be sorted and unique")
        object.__setattr__(self, "blockers", _strings(self.blockers, name="blockers"))
        object.__setattr__(self, "warnings", _strings(self.warnings, name="warnings"))
        expected_safe = (
            self.user_wave_coverage_complete
            and self.user_wavetable_coverage_complete
            and not wave_conflicts
            and not table_conflicts
            and self.empty_signature_validated
        )
        if self.safe_free_enabled != expected_safe:
            raise ProtocolError("safe_free_enabled disagrees with coverage, conflict and signature evidence")
        _normalized(self.reason, name="reason")

    @property
    def reference_coverage_complete(self) -> bool:
        return self.user_wavetable_coverage_complete and not self.user_wavetable_conflicts

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "user_wave_coverage_complete": self.user_wave_coverage_complete,
            "user_wavetable_coverage_complete": self.user_wavetable_coverage_complete,
            "reference_coverage_complete": self.reference_coverage_complete,
            "user_wave_conflicts": list(self.user_wave_conflicts),
            "user_wavetable_conflicts": list(self.user_wavetable_conflicts),
            "empty_signature_validated": self.empty_signature_validated,
            "safe_free_enabled": self.safe_free_enabled,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class UserWaveInventoryEntry:
    schema_version: int
    number: int
    state: InventoryState
    presence: InventoryPresence
    stored_samples_sha256: str | None
    referenced_by_wavetables: tuple[int, ...]
    source_ids: tuple[str, ...]
    conflict_sha256s: tuple[str, ...]
    matches_validated_empty_signature: bool
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != XT_MEMORY_INVENTORY_SCHEMA_VERSION:
            raise ProtocolError("Unsupported User Wave inventory entry schema version")
        if not USER_WAVE_FIRST <= self.number <= USER_WAVE_LAST:
            raise ProtocolError("User Wave inventory number out of range")
        if not isinstance(self.state, InventoryState):
            raise ProtocolError("state must be InventoryState")
        if not isinstance(self.presence, InventoryPresence):
            raise ProtocolError("presence must be InventoryPresence")
        if self.stored_samples_sha256 is not None:
            _sha256(self.stored_samples_sha256, name="stored_samples_sha256")
        references = tuple(self.referenced_by_wavetables)
        object.__setattr__(self, "referenced_by_wavetables", references)
        if tuple(sorted(set(references))) != references or any(
            not USER_WAVETABLE_DISPLAY_FIRST <= item <= USER_WAVETABLE_DISPLAY_LAST for item in references
        ):
            raise ProtocolError("referenced_by_wavetables must be sorted unique display numbers")
        object.__setattr__(self, "source_ids", _strings(self.source_ids, name="source_ids"))
        conflicts = tuple(self.conflict_sha256s)
        object.__setattr__(self, "conflict_sha256s", conflicts)
        if tuple(sorted(set(conflicts))) != conflicts:
            raise ProtocolError("conflict_sha256s must be sorted and unique")
        for value in conflicts:
            _sha256(value, name="conflict_sha256")
        if self.presence is InventoryPresence.CONFLICTED and len(conflicts) < 2:
            raise ProtocolError("conflicted entries require at least two hashes")
        if self.presence is not InventoryPresence.CONFLICTED and conflicts:
            raise ProtocolError("non-conflicted entries cannot expose conflict hashes")
        if self.state is InventoryState.SAFE_FREE and not self.matches_validated_empty_signature:
            raise ProtocolError("SAFE_FREE requires a validated empty signature match")
        if self.state is InventoryState.USED and not references:
            raise ProtocolError("USED requires at least one Wavetable reference")
        if self.state is InventoryState.ORPHANED and (references or self.presence is not InventoryPresence.PRESENT):
            raise ProtocolError("ORPHANED requires present unreferenced content")
        if not isinstance(self.matches_validated_empty_signature, bool):
            raise ProtocolError("matches_validated_empty_signature must be boolean")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "number": self.number,
            "state": self.state.value,
            "presence": self.presence.value,
            "stored_samples_sha256": self.stored_samples_sha256,
            "referenced_by_wavetables": list(self.referenced_by_wavetables),
            "source_ids": list(self.source_ids),
            "conflict_sha256s": list(self.conflict_sha256s),
            "matches_validated_empty_signature": self.matches_validated_empty_signature,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class UserWavetableInventoryEntry:
    schema_version: int
    display_number: int
    internal_number: int
    presence: InventoryPresence
    reference_payload_sha256: str | None
    user_wave_references: tuple[int, ...]
    unresolved_reference_count: int
    source_ids: tuple[str, ...]
    conflict_sha256s: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != XT_MEMORY_INVENTORY_SCHEMA_VERSION:
            raise ProtocolError("Unsupported User Wavetable inventory entry schema version")
        if not USER_WAVETABLE_DISPLAY_FIRST <= self.display_number <= USER_WAVETABLE_DISPLAY_LAST:
            raise ProtocolError("User Wavetable display number out of range")
        if self.internal_number != self.display_number - 1:
            raise ProtocolError("User Wavetable display/internal numbers disagree")
        if not isinstance(self.presence, InventoryPresence):
            raise ProtocolError("presence must be InventoryPresence")
        if self.reference_payload_sha256 is not None:
            _sha256(self.reference_payload_sha256, name="reference_payload_sha256")
        refs = tuple(self.user_wave_references)
        object.__setattr__(self, "user_wave_references", refs)
        if tuple(sorted(set(refs))) != refs or any(not USER_WAVE_FIRST <= item <= USER_WAVE_LAST for item in refs):
            raise ProtocolError("user_wave_references must be sorted unique User Wave numbers")
        if isinstance(self.unresolved_reference_count, bool) or not isinstance(self.unresolved_reference_count, int) or self.unresolved_reference_count < 0:
            raise ProtocolError("unresolved_reference_count must be a non-negative integer")
        object.__setattr__(self, "source_ids", _strings(self.source_ids, name="source_ids"))
        conflicts = tuple(self.conflict_sha256s)
        object.__setattr__(self, "conflict_sha256s", conflicts)
        if tuple(sorted(set(conflicts))) != conflicts:
            raise ProtocolError("conflict_sha256s must be sorted and unique")
        for value in conflicts:
            _sha256(value, name="conflict_sha256")
        if self.presence is InventoryPresence.CONFLICTED and len(conflicts) < 2:
            raise ProtocolError("conflicted Wavetables require at least two hashes")
        if self.presence is not InventoryPresence.CONFLICTED and conflicts:
            raise ProtocolError("non-conflicted Wavetables cannot expose conflict hashes")
        _normalized(self.reason, name="reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "display_number": self.display_number,
            "internal_number": self.internal_number,
            "presence": self.presence.value,
            "reference_payload_sha256": self.reference_payload_sha256,
            "user_wave_references": list(self.user_wave_references),
            "unresolved_reference_count": self.unresolved_reference_count,
            "source_ids": list(self.source_ids),
            "conflict_sha256s": list(self.conflict_sha256s),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class XtMemoryInventory:
    schema_version: int
    sources: tuple[InventorySourceEvidence, ...]
    evidence_status: InventoryEvidenceStatus
    user_waves: tuple[UserWaveInventoryEntry, ...]
    user_wavetables: tuple[UserWavetableInventoryEntry, ...]
    empty_wave_signature: ValidatedEmptyWaveSignature | None
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != XT_MEMORY_INVENTORY_SCHEMA_VERSION:
            raise ProtocolError("Unsupported XT memory inventory schema version")
        sources = tuple(self.sources)
        waves = tuple(self.user_waves)
        tables = tuple(self.user_wavetables)
        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "user_waves", waves)
        object.__setattr__(self, "user_wavetables", tables)
        if not sources or any(not isinstance(item, InventorySourceEvidence) for item in sources):
            raise ProtocolError("inventory requires at least one source evidence record")
        if len({item.source_id for item in sources}) != len(sources):
            raise ProtocolError("inventory source IDs must be unique")
        if not isinstance(self.evidence_status, InventoryEvidenceStatus):
            raise ProtocolError("evidence_status must be InventoryEvidenceStatus")
        if len(waves) != USER_WAVE_CAPACITY or tuple(item.number for item in waves) != tuple(range(USER_WAVE_FIRST, USER_WAVE_LAST + 1)):
            raise ProtocolError("inventory must classify all 250 User Waves in canonical order")
        if len(tables) != 32 or tuple(item.display_number for item in tables) != tuple(range(USER_WAVETABLE_DISPLAY_FIRST, USER_WAVETABLE_DISPLAY_LAST + 1)):
            raise ProtocolError("inventory must classify all 32 User Wavetables in canonical order")
        if self.empty_wave_signature is not None and not isinstance(self.empty_wave_signature, ValidatedEmptyWaveSignature):
            raise ProtocolError("empty_wave_signature must be ValidatedEmptyWaveSignature")
        safe_count = sum(item.state is InventoryState.SAFE_FREE for item in waves)
        if safe_count and not self.evidence_status.safe_free_enabled:
            raise ProtocolError("SAFE_FREE entries require safe_free_enabled evidence")
        _normalized(self.reason, name="reason")

    @property
    def state_counts(self) -> dict[str, int]:
        return {
            state.value: sum(item.state is state for item in self.user_waves)
            for state in InventoryState
        }

    def wave_entry(self, number: int) -> UserWaveInventoryEntry:
        if not USER_WAVE_FIRST <= number <= USER_WAVE_LAST:
            raise ProtocolError("User Wave number out of range")
        return self.user_waves[number - USER_WAVE_FIRST]

    def wavetable_entry(self, display_number: int) -> UserWavetableInventoryEntry:
        if not USER_WAVETABLE_DISPLAY_FIRST <= display_number <= USER_WAVETABLE_DISPLAY_LAST:
            raise ProtocolError("User Wavetable display number out of range")
        return self.user_wavetables[display_number - USER_WAVETABLE_DISPLAY_FIRST]

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sources": [item.to_dict() for item in self.sources],
            "evidence_status": self.evidence_status.to_dict(),
            "state_counts": self.state_counts,
            "user_waves": [item.to_dict() for item in self.user_waves],
            "user_wavetables": [item.to_dict() for item in self.user_wavetables],
            "empty_wave_signature": None if self.empty_wave_signature is None else self.empty_wave_signature.to_dict(),
            "boundaries": {
                "midi_opened": False,
                "midi_transmitted": False,
                "memory_written": False,
                "safe_free_inferred_without_proof": False,
            },
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
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _wave_hash(wave: UserWave) -> str:
    return _samples_hash(wave.stored_samples)


def _table_hash(table: UserWavetable) -> str:
    payload = b"".join(reference.to_bytes(2, "big") for reference in table.references)
    return sha256(payload).hexdigest()


def analyze_xt_memory_inventory(
    sources: Sequence[InventoryDumpSource],
    *,
    empty_wave_signature: ValidatedEmptyWaveSignature | None = None,
) -> XtMemoryInventory:
    """Build a conservative 250-wave/32-table inventory from external dumps.

    Any observed Wavetable reference proves ``USED``.  Absence of a reference
    can prove ``ORPHANED`` only with complete, conflict-free Wavetable coverage.
    ``SAFE_FREE`` additionally requires complete wave coverage and a hardware-
    validated empty-wave signature.  Partial or conflicting evidence remains
    ``UNKNOWN`` and is never silently promoted.
    """

    source_values = tuple(sources)
    if not source_values:
        raise ProtocolError("at least one inventory dump source is required")
    if any(not isinstance(item, InventoryDumpSource) for item in source_values):
        raise ProtocolError("sources must contain InventoryDumpSource values")
    if len({item.source_id for item in source_values}) != len(source_values):
        raise ProtocolError("inventory dump source IDs must be unique")
    if empty_wave_signature is not None and not isinstance(empty_wave_signature, ValidatedEmptyWaveSignature):
        raise ProtocolError("empty_wave_signature must be ValidatedEmptyWaveSignature")

    wave_versions: dict[int, list[tuple[str, UserWave]]] = {number: [] for number in range(USER_WAVE_FIRST, USER_WAVE_LAST + 1)}
    table_versions: dict[int, list[tuple[str, UserWavetable]]] = {
        number: [] for number in range(USER_WAVETABLE_DISPLAY_FIRST, USER_WAVETABLE_DISPLAY_LAST + 1)
    }
    source_evidence: list[InventorySourceEvidence] = []

    for source in source_values:
        wave_numbers: set[int] = set()
        table_numbers: set[int] = set()
        for message in source.dump:
            if int(message.dump_type) == int(DumpType.USER_WAVE):
                wave = UserWave.from_message(message)
                wave_versions[wave.number].append((source.source_id, wave))
                wave_numbers.add(wave.number)
            elif int(message.dump_type) == int(DumpType.USER_WAVETABLE):
                table = UserWavetable.from_message(message)
                table_versions[table.display_number].append((source.source_id, table))
                table_numbers.add(table.display_number)
        source_evidence.append(
            InventorySourceEvidence(
                schema_version=XT_MEMORY_INVENTORY_SCHEMA_VERSION,
                source_id=source.source_id,
                source_kind=source.source_kind,
                dump_sha256=source.dump_sha256,
                message_count=len(source.dump),
                user_wave_numbers=tuple(sorted(wave_numbers)),
                user_wavetable_display_numbers=tuple(sorted(table_numbers)),
                captured_current_state=source.captured_current_state,
                reason="External dump parsed without opening a MIDI port or mutating instrument memory.",
            )
        )

    wave_conflicts = tuple(
        number
        for number, versions in wave_versions.items()
        if len({_wave_hash(wave) for _, wave in versions}) > 1
    )
    table_conflicts = tuple(
        number
        for number, versions in table_versions.items()
        if len({_table_hash(table) for _, table in versions}) > 1
    )
    wave_complete = all(wave_versions[number] for number in range(USER_WAVE_FIRST, USER_WAVE_LAST + 1)) and not wave_conflicts
    table_complete = all(
        table_versions[number]
        for number in range(USER_WAVETABLE_DISPLAY_FIRST, USER_WAVETABLE_DISPLAY_LAST + 1)
    ) and not table_conflicts
    signature_valid = bool(empty_wave_signature and empty_wave_signature.safe_free_eligible)
    safe_enabled = wave_complete and table_complete and signature_valid

    blockers: list[str] = []
    warnings: list[str] = []
    if not wave_complete:
        blockers.append("Complete conflict-free coverage of all 250 User Waves is not proven.")
    if not table_complete:
        blockers.append("Complete conflict-free coverage of all 32 User Wavetables is not proven.")
    if not signature_valid:
        blockers.append("No hardware-validated empty User Wave signature is available; SAFE_FREE remains disabled.")
    if wave_conflicts:
        warnings.append("Conflicting User Wave payloads were observed across inventory sources.")
    if table_conflicts:
        warnings.append("Conflicting User Wavetable reference payloads were observed across inventory sources.")

    evidence_status = InventoryEvidenceStatus(
        schema_version=XT_MEMORY_INVENTORY_SCHEMA_VERSION,
        user_wave_coverage_complete=wave_complete,
        user_wavetable_coverage_complete=table_complete,
        user_wave_conflicts=wave_conflicts,
        user_wavetable_conflicts=table_conflicts,
        empty_signature_validated=signature_valid,
        safe_free_enabled=safe_enabled,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        reason=(
            "SAFE_FREE is enabled only by complete, conflict-free coverage and a hardware-validated empty signature."
            if safe_enabled
            else "Inventory remains conservative; missing proof cannot create SAFE_FREE destinations."
        ),
    )

    table_entries: list[UserWavetableInventoryEntry] = []
    referenced_by: dict[int, set[int]] = {number: set() for number in range(USER_WAVE_FIRST, USER_WAVE_LAST + 1)}
    for display_number in range(USER_WAVETABLE_DISPLAY_FIRST, USER_WAVETABLE_DISPLAY_LAST + 1):
        versions = table_versions[display_number]
        hashes = sorted({_table_hash(table) for _, table in versions})
        source_ids = tuple(dict.fromkeys(source_id for source_id, _ in versions))
        if not versions:
            presence = InventoryPresence.MISSING
            payload_hash = None
            user_refs: tuple[int, ...] = ()
            unresolved_count = 0
            conflicts: tuple[str, ...] = ()
            reason = "No evidence for this User Wavetable; references are unknown."
        elif len(hashes) > 1:
            presence = InventoryPresence.CONFLICTED
            payload_hash = None
            user_refs = tuple(sorted({
                reference
                for _, table in versions
                for reference in table.references
                if USER_WAVE_FIRST <= reference <= USER_WAVE_LAST
            }))
            unresolved_count = max(
                sum(reference == INTERPOLATED_WAVE_REFERENCE for reference in table.references)
                for _, table in versions
            )
            conflicts = tuple(hashes)
            reason = "Conflicting Wavetable payloads were retained as ambiguous evidence."
        else:
            presence = InventoryPresence.PRESENT
            table = versions[0][1]
            payload_hash = hashes[0]
            user_refs = tuple(sorted({
                reference for reference in table.references if USER_WAVE_FIRST <= reference <= USER_WAVE_LAST
            }))
            unresolved_count = sum(reference == INTERPOLATED_WAVE_REFERENCE for reference in table.references)
            conflicts = ()
            reason = "User Wavetable references were decoded from external dump evidence."
        for number in user_refs:
            referenced_by[number].add(display_number)
        table_entries.append(
            UserWavetableInventoryEntry(
                schema_version=XT_MEMORY_INVENTORY_SCHEMA_VERSION,
                display_number=display_number,
                internal_number=display_number - 1,
                presence=presence,
                reference_payload_sha256=payload_hash,
                user_wave_references=user_refs,
                unresolved_reference_count=unresolved_count,
                source_ids=source_ids,
                conflict_sha256s=conflicts,
                reason=reason,
            )
        )

    wave_entries: list[UserWaveInventoryEntry] = []
    signature_samples = None if empty_wave_signature is None else empty_wave_signature.stored_samples
    reference_complete = evidence_status.reference_coverage_complete
    for number in range(USER_WAVE_FIRST, USER_WAVE_LAST + 1):
        versions = wave_versions[number]
        hashes = sorted({_wave_hash(wave) for _, wave in versions})
        source_ids = tuple(dict.fromkeys(source_id for source_id, _ in versions))
        refs = tuple(sorted(referenced_by[number]))
        matches_empty = bool(
            safe_enabled
            and versions
            and len(hashes) == 1
            and signature_samples is not None
            and versions[0][1].stored_samples == signature_samples
        )
        if not versions:
            presence = InventoryPresence.MISSING
            sample_hash = None
            conflicts = ()
            state = InventoryState.USED if refs else InventoryState.UNKNOWN
            reason = (
                "A Wavetable reference proves use, but the User Wave payload is absent."
                if refs
                else "No User Wave payload or complete reference evidence is available."
            )
        elif len(hashes) > 1:
            presence = InventoryPresence.CONFLICTED
            sample_hash = None
            conflicts = tuple(hashes)
            state = InventoryState.USED if refs else InventoryState.UNKNOWN
            reason = (
                "A Wavetable reference proves use despite conflicting wave payloads."
                if refs
                else "Conflicting User Wave payloads prevent a safe availability classification."
            )
        else:
            presence = InventoryPresence.PRESENT
            sample_hash = hashes[0]
            conflicts = ()
            if refs:
                state = InventoryState.USED
                reason = "At least one observed User Wavetable explicitly references this User Wave."
            elif not reference_complete:
                state = InventoryState.UNKNOWN
                reason = "Absence of references is not proven because Wavetable coverage is incomplete or conflicted."
            elif matches_empty:
                state = InventoryState.SAFE_FREE
                reason = "Complete coverage and validated empty signature prove this destination safe and free."
            else:
                state = InventoryState.ORPHANED
                reason = "Content is present and complete Wavetable coverage proves no current reference."
        wave_entries.append(
            UserWaveInventoryEntry(
                schema_version=XT_MEMORY_INVENTORY_SCHEMA_VERSION,
                number=number,
                state=state,
                presence=presence,
                stored_samples_sha256=sample_hash,
                referenced_by_wavetables=refs,
                source_ids=source_ids,
                conflict_sha256s=conflicts,
                matches_validated_empty_signature=matches_empty,
                reason=reason,
            )
        )

    return XtMemoryInventory(
        schema_version=XT_MEMORY_INVENTORY_SCHEMA_VERSION,
        sources=tuple(source_evidence),
        evidence_status=evidence_status,
        user_waves=tuple(wave_entries),
        user_wavetables=tuple(table_entries),
        empty_wave_signature=empty_wave_signature,
        reason="Conservative XT memory inventory built from externally supplied dumps only.",
    )


__all__ = [
    "XT_MEMORY_INVENTORY_SCHEMA_VERSION",
    "InventoryState",
    "InventorySourceKind",
    "InventoryPresence",
    "InventoryDumpSource",
    "InventorySourceEvidence",
    "ValidatedEmptyWaveSignature",
    "InventoryEvidenceStatus",
    "UserWaveInventoryEntry",
    "UserWavetableInventoryEntry",
    "XtMemoryInventory",
    "analyze_xt_memory_inventory",
]
