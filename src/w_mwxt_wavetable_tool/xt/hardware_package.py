from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..allocation import UserWaveAllocation
from ..constants import (
    PATCH_NAME_LENGTH,
    PATCH_NAME_OFFSET,
    PATCH_WAVETABLE_OFFSET,
    USER_WAVE_FIRST,
    USER_WAVE_LAST,
    DumpType,
)
from ..destinations import (
    DeviceAddress,
    SoundDestination,
    UserWavetableDestination,
    encode_sound_name,
)
from ..dump import DumpFile
from ..errors import AnalysisError, HardwareValidationError, PackageBuildError
from ..message import SysExMessage
from ..models import SoundProgram, UserWave, UserWavetable
from ..version import __version__
from .audio_gate import build_controlled_audio_sound

HARDWARE_PACKAGE_SCHEMA_VERSION = 1
DEFAULT_STEM = "CODE_V7_E_XT_HARDWARE_PACKAGE"
EXPECTED_SLOT_COUNT = 61
EXPECTED_MESSAGE_COUNT = 63
_STEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


def _require_hash(value: str, *, name: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise AnalysisError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _validated_hashed_document(
    document: Mapping[str, Any],
    *,
    expected_schema_name: str,
) -> str:
    recorded = str(document.get("analysis_sha256", ""))
    _require_hash(recorded, name=f"{expected_schema_name}.analysis_sha256")
    content = dict(document)
    del content["analysis_sha256"]
    calculated = _canonical_sha256(content)
    if calculated != recorded:
        raise AnalysisError(
            f"{expected_schema_name} analysis_sha256 mismatch: "
            f"recorded={recorded}, calculated={calculated}"
        )
    return recorded


def _read_json(path: str | Path) -> Mapping[str, Any]:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Unable to read JSON document {source}: {exc}") from exc
    if not isinstance(document, Mapping):
        raise AnalysisError(f"JSON document {source} must contain an object at its root")
    return document


def _validate_stored_samples(values: Sequence[int], *, label: str) -> tuple[int, ...]:
    stored = tuple(int(value) for value in values)
    if len(stored) != 64:
        raise AnalysisError(f"{label} must contain exactly 64 stored samples")
    if any(value < -127 or value > 127 for value in stored):
        raise AnalysisError(f"{label} must stay inside the safe range -127..127")
    if -128 in stored:
        raise AnalysisError(f"{label} contains forbidden -128")
    return stored


def _reconstruct(stored: Sequence[int]) -> tuple[int, ...]:
    values = tuple(int(value) for value in stored)
    return values + tuple(-value for value in reversed(values))


def _validate_trajectory_document(
    document: Mapping[str, Any],
) -> tuple[str, str, tuple[tuple[int, ...], ...]]:
    trajectory_hash = _validated_hashed_document(
        document,
        expected_schema_name="trajectory",
    )
    if int(document.get("schema_version", 0)) != 1:
        raise AnalysisError("CODE V7-E requires CODE V7-C trajectory schema version 1")
    if int(document.get("slot_count", 0)) != EXPECTED_SLOT_COUNT:
        raise AnalysisError("CODE V7-E requires exactly 61 trajectory slots")
    if int(document.get("anchor_count", 0)) <= 0:
        raise AnalysisError("trajectory anchor_count must be positive")
    if document.get("duplicate_adjacent_slot_pairs") not in ([], tuple()):
        raise AnalysisError("trajectory contains adjacent duplicate slots")
    boundaries = document.get("boundaries")
    if not isinstance(boundaries, Mapping):
        raise AnalysisError("trajectory boundaries must be an object")
    if boundaries.get("generates_sysex") is not False:
        raise AnalysisError("trajectory must explicitly declare generates_sysex=false")
    source_projection_hash = str(document.get("source_projection_set_sha256", ""))
    _require_hash(source_projection_hash, name="trajectory.source_projection_set_sha256")

    slots = document.get("slots")
    if not isinstance(slots, list) or len(slots) != EXPECTED_SLOT_COUNT:
        raise AnalysisError("trajectory slots must contain exactly 61 objects")

    stored_slots: list[tuple[int, ...]] = []
    previous: tuple[int, ...] | None = None
    for expected_slot_number, slot in enumerate(slots, start=1):
        if not isinstance(slot, Mapping):
            raise AnalysisError("trajectory slots must be JSON objects")
        if int(slot.get("slot_number", 0)) != expected_slot_number:
            raise AnalysisError("trajectory slot numbers must be contiguous from 1 to 61")
        stored = _validate_stored_samples(
            slot.get("stored_samples", ()),
            label=f"slot {expected_slot_number} stored_samples",
        )
        reconstructed = tuple(int(value) for value in slot.get("reconstructed_samples", ()))
        if reconstructed != _reconstruct(stored):
            raise AnalysisError(
                f"slot {expected_slot_number} reverse-negate reconstruction is invalid"
            )
        if previous == stored:
            raise AnalysisError(
                f"adjacent slots {expected_slot_number - 1} and {expected_slot_number} are identical"
            )
        previous = stored
        stored_slots.append(stored)

    return trajectory_hash, source_projection_hash, tuple(stored_slots)


def _validate_qc_document(
    document: Mapping[str, Any],
    *,
    expected_trajectory_hash: str,
    expected_projection_hash: str,
) -> str:
    qc_hash = _validated_hashed_document(document, expected_schema_name="trajectory_qc")
    if int(document.get("schema_version", 0)) != 1:
        raise AnalysisError("CODE V7-E requires CODE V7-D QC schema version 1")
    if str(document.get("status", "")) != "pass":
        raise AnalysisError("CODE V7-E requires a CODE V7-D QC report with status=pass")
    if str(document.get("source_trajectory_sha256", "")) != expected_trajectory_hash:
        raise AnalysisError("QC report does not match the selected V7-C trajectory")
    if str(document.get("source_projection_set_sha256", "")) != expected_projection_hash:
        raise AnalysisError("QC report does not match the trajectory projection source")
    if int(document.get("flagged_jump_count", -1)) != 0:
        raise AnalysisError("QC report contains flagged adjacent jumps")
    if int(document.get("flagged_curvature_count", -1)) != 0:
        raise AnalysisError("QC report contains flagged curvature points")
    boundaries = document.get("boundaries")
    if not isinstance(boundaries, Mapping):
        raise AnalysisError("QC boundaries must be an object")
    if boundaries.get("modifies_trajectory_slots") is not False:
        raise AnalysisError("QC report must not modify trajectory slots")
    if boundaries.get("generates_sysex") is not False:
        raise AnalysisError("QC report must explicitly declare generates_sysex=false")
    return qc_hash


def _message_index(dump: DumpFile) -> dict[tuple[int, int], SysExMessage]:
    index: dict[tuple[int, int], SysExMessage] = {}
    duplicates: list[tuple[int, int]] = []
    for message in dump.messages:
        key = (int(message.dump_type), message.address)
        if key in index:
            duplicates.append(key)
        else:
            index[key] = message
    if duplicates:
        rendered = ", ".join(
            f"type=0x{dump_type:02X}/address={address}"
            for dump_type, address in sorted(set(duplicates))
        )
        raise HardwareValidationError(
            "Baseline dump contains duplicate destinations: " + rendered
        )
    return index


def _require_message(
    index: Mapping[tuple[int, int], SysExMessage],
    dump_type: DumpType,
    address: int,
    *,
    label: str,
) -> SysExMessage:
    try:
        return index[(int(dump_type), address)]
    except KeyError as exc:
        raise HardwareValidationError(f"Baseline dump is missing {label}") from exc


def _coerce_stored_sound(value: SoundDestination | str, *, field_name: str) -> SoundDestination:
    destination = value if isinstance(value, SoundDestination) else SoundDestination.parse(value)
    if destination.is_edit_buffer:
        raise HardwareValidationError(
            f"{field_name} must be a stored Sound destination A001..B128"
        )
    return destination


def _target_label(message: SysExMessage) -> str:
    if int(message.dump_type) == int(DumpType.USER_WAVE):
        return f"User Wave {message.address}"
    if int(message.dump_type) == int(DumpType.USER_WAVETABLE):
        return f"User Wavetable {message.address + 1:03d}"
    if int(message.dump_type) == int(DumpType.SOUND):
        bank = "A" if message.address < 128 else "B"
        slot = (message.address & 0x7F) + 1
        return f"Sound {bank}{slot:03d}"
    return f"Type 0x{int(message.dump_type):02X} address {message.address}"


class XtHardwarePackageStatus(str, Enum):
    PASS = "pass"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class XtHardwareArtifact:
    file_name: str
    role: str
    byte_length: int
    sha256: str

    def __post_init__(self) -> None:
        if not self.file_name or not self.role:
            raise AnalysisError("artifact file_name and role must not be empty")
        if self.byte_length <= 0:
            raise AnalysisError("artifact byte_length must be positive")
        _require_hash(self.sha256, name="artifact.sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "role": self.role,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class XtHardwareTargetEvidence:
    index: int
    dump_type: str
    address: int
    destination: str
    sent_payload_sha256: str
    baseline_payload_sha256: str
    payload_changed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "dump_type": self.dump_type,
            "address": self.address,
            "destination": self.destination,
            "sent_payload_sha256": self.sent_payload_sha256,
            "baseline_payload_sha256": self.baseline_payload_sha256,
            "payload_changed": self.payload_changed,
        }


@dataclass(frozen=True, slots=True)
class XtHardwarePackageAnalysis:
    schema_version: int
    tool_version: str
    status: XtHardwarePackageStatus
    package_name: str
    source_trajectory_sha256: str
    source_qc_sha256: str
    source_projection_set_sha256: str
    baseline_sha256: str
    device_id: int
    user_wave_start: int
    user_wave_end: int
    wavetable_display_number: int
    wavetable_internal_number: int
    sound_destination: str
    template_sound_destination: str
    sound_name: str
    package_sha256: str
    restore_bundle_sha256: str
    message_count: int
    user_wave_count: int
    sound_parameter_changes: tuple[dict[str, int], ...]
    target_evidence: tuple[XtHardwareTargetEvidence, ...]
    artifacts: tuple[XtHardwareArtifact, ...]
    decision_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != HARDWARE_PACKAGE_SCHEMA_VERSION:
            raise AnalysisError("Unsupported XT hardware package schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise AnalysisError("tool_version must be a normalized non-empty string")
        if not isinstance(self.status, XtHardwarePackageStatus):
            raise AnalysisError("status must be an XtHardwarePackageStatus")
        if not _STEM_RE.fullmatch(self.package_name):
            raise AnalysisError("package_name contains unsupported characters")
        for name in (
            "source_trajectory_sha256",
            "source_qc_sha256",
            "source_projection_set_sha256",
            "baseline_sha256",
            "package_sha256",
            "restore_bundle_sha256",
        ):
            _require_hash(getattr(self, name), name=name)
        DeviceAddress(self.device_id)
        if self.user_wave_end - self.user_wave_start + 1 != EXPECTED_SLOT_COUNT:
            raise AnalysisError("hardware package must cover exactly 61 User Waves")
        if self.message_count != EXPECTED_MESSAGE_COUNT:
            raise AnalysisError("hardware package must contain exactly 63 messages")
        if self.user_wave_count != EXPECTED_SLOT_COUNT:
            raise AnalysisError("user_wave_count must equal 61")
        for change in self.sound_parameter_changes:
            if set(change) != {"index", "before", "after"}:
                raise AnalysisError("sound parameter change entries are invalid")
            if not 0 <= int(change["index"]) < 256:
                raise AnalysisError("sound parameter change index is invalid")
            if not 0 <= int(change["before"]) <= 127 or not 0 <= int(change["after"]) <= 127:
                raise AnalysisError("sound parameter change values must be MIDI-safe")
        if len(self.target_evidence) != EXPECTED_MESSAGE_COUNT:
            raise AnalysisError("target_evidence must contain exactly 63 entries")
        if not self.artifacts:
            raise AnalysisError("hardware package must expose deterministic artifacts")
        if not self.decision_reason:
            raise AnalysisError("decision_reason must not be empty")

    @property
    def unchanged_targets(self) -> tuple[str, ...]:
        return tuple(
            evidence.destination
            for evidence in self.target_evidence
            if not evidence.payload_changed
        )

    @property
    def all_targets_exercised(self) -> bool:
        return not self.unchanged_targets

    @property
    def ready_for_v7_f(self) -> bool:
        return self.status is XtHardwarePackageStatus.PASS and self.all_targets_exercised

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "status": self.status.value,
            "package_name": self.package_name,
            "source_trajectory_sha256": self.source_trajectory_sha256,
            "source_qc_sha256": self.source_qc_sha256,
            "source_projection_set_sha256": self.source_projection_set_sha256,
            "baseline_sha256": self.baseline_sha256,
            "device_id": self.device_id,
            "user_wave_start": self.user_wave_start,
            "user_wave_end": self.user_wave_end,
            "user_wave_range": f"{self.user_wave_start}–{self.user_wave_end}",
            "wavetable_display_number": self.wavetable_display_number,
            "wavetable_internal_number": self.wavetable_internal_number,
            "sound_destination": self.sound_destination,
            "template_sound_destination": self.template_sound_destination,
            "sound_name": self.sound_name,
            "package_sha256": self.package_sha256,
            "restore_bundle_sha256": self.restore_bundle_sha256,
            "message_count": self.message_count,
            "user_wave_count": self.user_wave_count,
            "target_payload_changed_count": sum(
                evidence.payload_changed for evidence in self.target_evidence
            ),
            "unchanged_target_count": len(self.unchanged_targets),
            "unchanged_targets": list(self.unchanged_targets),
            "all_targets_backed_up": True,
            "all_targets_exercised": self.all_targets_exercised,
            "ready_for_v7_f": self.ready_for_v7_f,
            "sound_parameter_change_count": len(self.sound_parameter_changes),
            "sound_parameter_changes": [dict(change) for change in self.sound_parameter_changes],
            "target_evidence": [item.to_dict() for item in self.target_evidence],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "decision_reason": self.decision_reason,
            "boundaries": {
                "generates_sysex": True,
                "transmits_midi": False,
                "opens_midi_ports": False,
                "writes_hardware": False,
                "dry_run_only": True,
                "requires_manual_transmission": True,
                "requires_redump": True,
                "preserves_three_fixed_tail_references": True,
                "allows_negative_128": False,
            },
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
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

    def to_markdown(self) -> str:
        lines = [
            "# CODE V7-E — XT hardware package dry-run",
            "",
            f"- Status: `{self.status.value}`",
            f"- Analysis SHA-256: `{self.analysis_sha256}`",
            f"- Source V7-C trajectory: `{self.source_trajectory_sha256}`",
            f"- Source V7-D QC: `{self.source_qc_sha256}`",
            f"- Baseline backup: `{self.baseline_sha256}`",
            f"- Device ID: `{self.device_id}`",
            f"- User Waves: `{self.user_wave_start}–{self.user_wave_end}`",
            f"- User Wavetable: `{self.wavetable_display_number:03d}`",
            f"- Sound: `{self.sound_destination}`",
            f"- Sound template: `{self.template_sound_destination}`",
            f"- Sound name: `{self.sound_name}`",
            f"- Controlled Sound parameter changes: `{len(self.sound_parameter_changes)}`",
            f"- Messages: `{self.message_count}`",
            f"- Package SHA-256: `{self.package_sha256}`",
            f"- Restore SHA-256: `{self.restore_bundle_sha256}`",
            f"- Unchanged targets: `{len(self.unchanged_targets)}`",
            f"- Ready for CODE V7-F: `{'yes' if self.ready_for_v7_f else 'no'}`",
            "- Automatic MIDI transmission: `no`",
            "",
            "## Ordered transmission files",
            "",
            "1. `01-user-waves.syx` — 61 WAVD messages.",
            "2. `02-user-wavetable.syx` — one WCTD message.",
            "3. `03-sound.syx` — one SNDD message.",
            "4. Redump the written targets and compare them during CODE V7-F.",
            "5. Use `restore.syx` only when restoration is required.",
            "",
            "The all-in-one `package.syx` contains the same 63 messages in that order. "
            "No file is transmitted automatically by CODE V7-E.",
            "",
            "## Target evidence",
            "",
            "| # | Type | Address | Destination | Payload changed |",
            "|---:|---|---:|---|:---:|",
        ]
        for evidence in self.target_evidence:
            lines.append(
                f"| {evidence.index} | {evidence.dump_type} | {evidence.address} | "
                f"{evidence.destination} | {'yes' if evidence.payload_changed else 'no'} |"
            )
        lines.extend(["", "## Controlled Sound changes", "", "The Sound template is converted into the previously validated V7-A.2 controlled audition patch before the destination and name are encoded.", "", "| Byte | Before | After |", "|---:|---:|---:|"])
        for change in self.sound_parameter_changes:
            lines.append(f"| {change['index']} | {change['before']} | {change['after']} |")
        lines.extend(["", "## Artifacts", "", "| File | Role | Bytes | SHA-256 |", "|---|---|---:|---|"])
        for artifact in self.artifacts:
            lines.append(
                f"| `{artifact.file_name}` | {artifact.role} | {artifact.byte_length} | "
                f"`{artifact.sha256}` |"
            )
        if self.unchanged_targets:
            lines.extend(
                [
                    "",
                    "## Review condition",
                    "",
                    "The following destinations already contain the generated payload. "
                    "This is not a collision or data-loss risk, but a later exact read-back "
                    "cannot prove that those particular messages were rewritten:",
                    "",
                ]
            )
            lines.extend(f"- {target}" for target in self.unchanged_targets)
        lines.extend(
            [
                "",
                "## Safety boundary",
                "",
                "CODE V7-E only creates deterministic files. It does not open MIDI ports, "
                "send SysEx, write the Microwave XT, or claim hardware acceptance. Manual "
                "transmission, target redump, exact comparison, and restoration testing belong "
                "to CODE V7-F.",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class XtHardwarePackageOutputPaths:
    package_sysex: Path
    user_waves_sysex: Path
    user_wavetable_sysex: Path
    sound_sysex: Path
    restore_sysex: Path
    analysis_json: Path
    analysis_markdown: Path
    sha256_index: Path


@dataclass(frozen=True, slots=True)
class XtHardwarePackageBuild:
    stem: str
    analysis: XtHardwarePackageAnalysis
    package_dump: DumpFile
    user_waves_dump: DumpFile
    user_wavetable_dump: DumpFile
    sound_dump: DumpFile
    restore_dump: DumpFile

    def write(self, directory: str | Path) -> XtHardwarePackageOutputPaths:
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        paths = XtHardwarePackageOutputPaths(
            package_sysex=destination / f"{self.stem}.package.syx",
            user_waves_sysex=destination / f"{self.stem}.01-user-waves.syx",
            user_wavetable_sysex=destination / f"{self.stem}.02-user-wavetable.syx",
            sound_sysex=destination / f"{self.stem}.03-sound.syx",
            restore_sysex=destination / f"{self.stem}.restore.syx",
            analysis_json=destination / f"{self.stem}.analysis.json",
            analysis_markdown=destination / f"{self.stem}.analysis.md",
            sha256_index=destination / f"{self.stem}.sha256.txt",
        )
        payloads = {
            paths.package_sysex.name: self.package_dump.to_bytes(),
            paths.user_waves_sysex.name: self.user_waves_dump.to_bytes(),
            paths.user_wavetable_sysex.name: self.user_wavetable_dump.to_bytes(),
            paths.sound_sysex.name: self.sound_dump.to_bytes(),
            paths.restore_sysex.name: self.restore_dump.to_bytes(),
        }
        expected = {artifact.file_name: artifact.sha256 for artifact in self.analysis.artifacts}
        if set(payloads) != set(expected):
            raise PackageBuildError("artifact names do not match package payloads")
        for file_name, payload in payloads.items():
            if sha256(payload).hexdigest() != expected[file_name]:
                raise PackageBuildError(f"artifact hash mismatch before writing {file_name}")

        paths.package_sysex.write_bytes(payloads[paths.package_sysex.name])
        paths.user_waves_sysex.write_bytes(payloads[paths.user_waves_sysex.name])
        paths.user_wavetable_sysex.write_bytes(payloads[paths.user_wavetable_sysex.name])
        paths.sound_sysex.write_bytes(payloads[paths.sound_sysex.name])
        paths.restore_sysex.write_bytes(payloads[paths.restore_sysex.name])
        paths.analysis_json.write_text(self.analysis.to_json(), encoding="utf-8", newline="\n")
        paths.analysis_markdown.write_text(
            self.analysis.to_markdown(), encoding="utf-8", newline="\n"
        )
        hash_lines = [
            f"{artifact.sha256}  {artifact.file_name}"
            for artifact in sorted(self.analysis.artifacts, key=lambda item: item.file_name)
        ]
        hash_lines.append(f"{self.analysis.analysis_sha256}  {paths.analysis_json.name}#canonical-analysis")
        paths.sha256_index.write_text("\n".join(hash_lines) + "\n", encoding="utf-8", newline="\n")
        return paths


def build_xt_hardware_package_documents(
    trajectory_document: Mapping[str, Any],
    qc_document: Mapping[str, Any],
    baseline: DumpFile,
    *,
    baseline_sha256: str,
    user_wave_start: int,
    wavetable_display_number: int,
    sound_destination: SoundDestination | str,
    template_sound_destination: SoundDestination | str | None = None,
    sound_name: str,
    stem: str = DEFAULT_STEM,
    tool_version: str = __version__,
) -> XtHardwarePackageBuild:
    if not _STEM_RE.fullmatch(stem):
        raise PackageBuildError(
            "stem must contain 1..64 characters using letters, digits, '.', '_' or '-'"
        )
    _require_hash(baseline_sha256, name="baseline_sha256")
    trajectory_hash, projection_hash, stored_slots = _validate_trajectory_document(
        trajectory_document
    )
    qc_hash = _validate_qc_document(
        qc_document,
        expected_trajectory_hash=trajectory_hash,
        expected_projection_hash=projection_hash,
    )

    allocation = UserWaveAllocation.complete_table(user_wave_start)
    wavetable_destination = UserWavetableDestination(wavetable_display_number)
    target_sound = _coerce_stored_sound(sound_destination, field_name="sound_destination")
    template_sound = (
        target_sound
        if template_sound_destination is None
        else _coerce_stored_sound(
            template_sound_destination,
            field_name="template_sound_destination",
        )
    )
    encode_sound_name(sound_name)

    if len(baseline.device_ids) != 1:
        raise HardwareValidationError(
            f"Baseline dump must contain exactly one Device ID, got {baseline.device_ids}"
        )
    device = DeviceAddress(baseline.device_ids[0])
    if device.is_broadcast:
        raise HardwareValidationError("Baseline Device ID must not be broadcast 127")

    index = _message_index(baseline)
    target_wave_messages = tuple(
        _require_message(
            index,
            DumpType.USER_WAVE,
            number,
            label=f"target User Wave {number}",
        )
        for number in allocation.numbers
    )
    target_table_message = _require_message(
        index,
        DumpType.USER_WAVETABLE,
        wavetable_destination.internal_number,
        label=f"target User Wavetable {wavetable_destination.display_number:03d}",
    )
    target_sound_address = target_sound.wire_address
    template_sound_address = template_sound.wire_address
    assert target_sound_address is not None and template_sound_address is not None
    target_sound_message = _require_message(
        index,
        DumpType.SOUND,
        target_sound_address,
        label=f"target Sound {target_sound.display_location}",
    )
    template_sound_message = _require_message(
        index,
        DumpType.SOUND,
        template_sound_address,
        label=f"template Sound {template_sound.display_location}",
    )

    target_table_baseline = UserWavetable.from_message(target_table_message)
    fixed_tail = target_table_baseline.references[61:]
    if len(fixed_tail) != 3:
        raise HardwareValidationError("target Wavetable does not expose three tail references")

    user_waves = tuple(
        UserWave(
            device_id=device.value,
            number=number,
            stored_samples=stored,
        )
        for number, stored in zip(allocation.numbers, stored_slots, strict=True)
    )
    wavetable = UserWavetable(
        device_id=device.value,
        internal_number=wavetable_destination.internal_number,
        references=allocation.numbers + fixed_tail,
    )
    source_sound = SoundProgram.from_message(template_sound_message)
    sound, sound_changes = build_controlled_audio_sound(
        source_sound,
        device_id=device.value,
        target_bank=target_sound_address >> 7,
        target_slot=target_sound_address & 0x7F,
        target_wavetable_internal=wavetable_destination.internal_number,
        name=sound_name,
    )

    package_messages = tuple(wave.to_message() for wave in user_waves) + (
        wavetable.to_message(),
        sound.to_message(),
    )
    if len(package_messages) != EXPECTED_MESSAGE_COUNT:
        raise PackageBuildError("generated package message count is not 63")
    for message in package_messages:
        message.assert_valid(strict_length=True)

    package_dump = DumpFile(package_messages)
    package_bytes = package_dump.to_bytes()
    if DumpFile.from_bytes(package_bytes).to_bytes() != package_bytes:
        raise PackageBuildError("generated package failed strict round-trip")

    user_waves_dump = DumpFile(package_messages[:61])
    user_wavetable_dump = DumpFile((package_messages[61],))
    sound_dump = DumpFile((package_messages[62],))
    restore_messages = target_wave_messages + (target_table_message, target_sound_message)
    restore_dump = DumpFile(restore_messages)
    restore_bytes = restore_dump.to_bytes()
    if DumpFile.from_bytes(restore_bytes).to_bytes() != restore_bytes:
        raise PackageBuildError("restore bundle failed strict round-trip")

    target_evidence: list[XtHardwareTargetEvidence] = []
    for evidence_index, (sent, original) in enumerate(
        zip(package_messages, restore_messages, strict=True),
        start=1,
    ):
        try:
            type_name = DumpType(int(sent.dump_type)).name
        except ValueError:
            type_name = f"UNKNOWN_{int(sent.dump_type):02X}"
        target_evidence.append(
            XtHardwareTargetEvidence(
                index=evidence_index,
                dump_type=type_name,
                address=sent.address,
                destination=_target_label(sent),
                sent_payload_sha256=sha256(sent.payload).hexdigest(),
                baseline_payload_sha256=sha256(original.payload).hexdigest(),
                payload_changed=sent.payload != original.payload,
            )
        )

    artifact_payloads = (
        (f"{stem}.package.syx", "all-in-one ordered 63-message package", package_bytes),
        (
            f"{stem}.01-user-waves.syx",
            "61 User Wave WAVD messages",
            user_waves_dump.to_bytes(),
        ),
        (
            f"{stem}.02-user-wavetable.syx",
            "one User Wavetable WCTD message",
            user_wavetable_dump.to_bytes(),
        ),
        (f"{stem}.03-sound.syx", "one Sound SNDD message", sound_dump.to_bytes()),
        (f"{stem}.restore.syx", "exact baseline restore bundle", restore_bytes),
    )
    artifacts = tuple(
        XtHardwareArtifact(
            file_name=file_name,
            role=role,
            byte_length=len(payload),
            sha256=sha256(payload).hexdigest(),
        )
        for file_name, role, payload in artifact_payloads
    )
    unchanged = tuple(
        evidence.destination for evidence in target_evidence if not evidence.payload_changed
    )
    status = XtHardwarePackageStatus.PASS if not unchanged else XtHardwarePackageStatus.REVIEW
    decision_reason = (
        "all 63 target payloads differ from the baseline and the dry-run package is ready for CODE V7-F"
        if not unchanged
        else (
            f"{len(unchanged)} target payload(s) already match the baseline; package is safe but "
            "hardware write proof for those targets requires review"
        )
    )
    analysis = XtHardwarePackageAnalysis(
        schema_version=HARDWARE_PACKAGE_SCHEMA_VERSION,
        tool_version=tool_version,
        status=status,
        package_name=stem,
        source_trajectory_sha256=trajectory_hash,
        source_qc_sha256=qc_hash,
        source_projection_set_sha256=projection_hash,
        baseline_sha256=baseline_sha256,
        device_id=device.value,
        user_wave_start=allocation.start_number,
        user_wave_end=allocation.end_number,
        wavetable_display_number=wavetable_destination.display_number,
        wavetable_internal_number=wavetable_destination.internal_number,
        sound_destination=target_sound.display_location,
        template_sound_destination=template_sound.display_location,
        sound_name=sound.name,
        package_sha256=sha256(package_bytes).hexdigest(),
        restore_bundle_sha256=sha256(restore_bytes).hexdigest(),
        message_count=len(package_messages),
        user_wave_count=len(user_waves),
        sound_parameter_changes=tuple(dict(change) for change in sound_changes),
        target_evidence=tuple(target_evidence),
        artifacts=artifacts,
        decision_reason=decision_reason,
    )
    return XtHardwarePackageBuild(
        stem=stem,
        analysis=analysis,
        package_dump=package_dump,
        user_waves_dump=user_waves_dump,
        user_wavetable_dump=user_wavetable_dump,
        sound_dump=sound_dump,
        restore_dump=restore_dump,
    )


def load_and_build_xt_hardware_package(
    trajectory_path: str | Path,
    qc_path: str | Path,
    baseline_path: str | Path,
    *,
    user_wave_start: int,
    wavetable_display_number: int,
    sound_destination: SoundDestination | str,
    template_sound_destination: SoundDestination | str | None = None,
    sound_name: str,
    stem: str = DEFAULT_STEM,
    tool_version: str = __version__,
) -> XtHardwarePackageBuild:
    baseline_source = Path(baseline_path)
    try:
        baseline_bytes = baseline_source.read_bytes()
    except OSError as exc:
        raise HardwareValidationError(
            f"Unable to read baseline dump {baseline_source}: {exc}"
        ) from exc
    baseline = DumpFile.from_bytes(baseline_bytes)
    return build_xt_hardware_package_documents(
        _read_json(trajectory_path),
        _read_json(qc_path),
        baseline,
        baseline_sha256=sha256(baseline_bytes).hexdigest(),
        user_wave_start=user_wave_start,
        wavetable_display_number=wavetable_display_number,
        sound_destination=sound_destination,
        template_sound_destination=template_sound_destination,
        sound_name=sound_name,
        stem=stem,
        tool_version=tool_version,
    )
