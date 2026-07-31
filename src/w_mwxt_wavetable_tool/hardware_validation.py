from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
import json
import re
from typing import Iterable

from .constants import (
    PATCH_WAVETABLE_OFFSET,
    USER_WAVE_FIRST,
    USER_WAVE_LAST,
    USER_WAVETABLE_INTERNAL_FIRST,
    USER_WAVETABLE_INTERNAL_LAST,
    DumpType,
)
from .dump import DumpFile
from .errors import HardwareValidationError
from .message import SysExMessage
from .models import SoundProgram, UserWavetable

_OUTPUT_STEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ComparisonStatus(str, Enum):
    EXACT = "exact"
    DEVICE_ID_CHANGED = "device_id_changed"
    ADDRESS_CHANGED = "address_changed"
    ADDRESS_AND_DEVICE_ID_CHANGED = "address_and_device_id_changed"
    PAYLOAD_CHANGED = "payload_changed"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    AMBIGUOUS_RELOCATION = "ambiguous_relocation"


class HardwareValidationStatus(str, Enum):
    PASS_EXACT = "pass_exact"
    REVIEW_NORMALIZATION = "review_normalization"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class MessageIdentity:
    dump_type: int
    address: int

    @property
    def type_name(self) -> str:
        try:
            return DumpType(self.dump_type).name
        except ValueError:
            return f"UNKNOWN_{self.dump_type:02X}"

    @property
    def label(self) -> str:
        if self.dump_type == int(DumpType.USER_WAVE):
            return f"User Wave {self.address}"
        if self.dump_type == int(DumpType.USER_WAVETABLE):
            return f"User Wavetable {self.address + 1:03d}"
        if self.dump_type == int(DumpType.SOUND):
            bank = "A" if self.address < 128 else "B"
            slot = (self.address & 0x7F) + 1
            return f"Sound {bank}{slot:03d}"
        return f"{self.type_name} {self.address}"


@dataclass(frozen=True, slots=True)
class HardwarePackageProfile:
    device_id: int
    wave_addresses: tuple[int, ...]
    wavetable_internal_number: int
    sound_address: int
    message_count: int
    required_wave_count: int | None

    @property
    def wavetable_display_number(self) -> int:
        return self.wavetable_internal_number + 1

    @property
    def sound_location(self) -> str:
        bank = "A" if self.sound_address < 128 else "B"
        slot = (self.sound_address & 0x7F) + 1
        return f"{bank}{slot:03d}"

    @property
    def wave_range(self) -> str:
        return f"{self.wave_addresses[0]}–{self.wave_addresses[-1]}"

    @property
    def target_identities(self) -> tuple[MessageIdentity, ...]:
        waves = tuple(
            MessageIdentity(int(DumpType.USER_WAVE), address)
            for address in self.wave_addresses
        )
        return waves + (
            MessageIdentity(
                int(DumpType.USER_WAVETABLE), self.wavetable_internal_number
            ),
            MessageIdentity(int(DumpType.SOUND), self.sound_address),
        )


@dataclass(frozen=True, slots=True)
class BaselineTargetEvidence:
    index: int
    identity: MessageIdentity
    sent_payload_sha256: str
    baseline_payload_sha256: str
    payload_changed: bool

    @property
    def label(self) -> str:
        return self.identity.label

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "dump_type": self.identity.type_name,
            "address": self.identity.address,
            "destination": self.identity.label,
            "sent_payload_sha256": self.sent_payload_sha256,
            "baseline_payload_sha256": self.baseline_payload_sha256,
            "payload_changed": self.payload_changed,
        }


@dataclass(frozen=True, slots=True)
class HardwarePreflightReport:
    sent_package_sha256: str
    baseline_sha256: str
    restore_bundle_sha256: str
    profile: HardwarePackageProfile
    targets: tuple[BaselineTargetEvidence, ...]
    all_targets_backed_up: bool = True

    @property
    def unchanged_payload_targets(self) -> tuple[str, ...]:
        return tuple(item.label for item in self.targets if not item.payload_changed)

    @property
    def all_targets_exercised(self) -> bool:
        return not self.unchanged_payload_targets

    @property
    def ready_for_transmission(self) -> bool:
        return self.all_targets_backed_up and self.all_targets_exercised

    def assert_ready_for_transmission(self) -> None:
        if not self.all_targets_backed_up:
            raise HardwareValidationError(
                "The baseline backup does not cover every destination in the package"
            )
        if self.unchanged_payload_targets:
            raise HardwareValidationError(
                "The package does not exercise every target; payload already matches the "
                "baseline at: " + ", ".join(self.unchanged_payload_targets)
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "sent_package_sha256": self.sent_package_sha256,
            "baseline_sha256": self.baseline_sha256,
            "restore_bundle_sha256": self.restore_bundle_sha256,
            "device_id": self.profile.device_id,
            "message_count": self.profile.message_count,
            "required_wave_count": self.profile.required_wave_count,
            "user_wave_count": len(self.profile.wave_addresses),
            "user_wave_range": self.profile.wave_range,
            "wavetable_display_number": self.profile.wavetable_display_number,
            "wavetable_internal_number": self.profile.wavetable_internal_number,
            "sound_destination": self.profile.sound_location,
            "all_targets_backed_up": self.all_targets_backed_up,
            "all_targets_exercised": self.all_targets_exercised,
            "ready_for_transmission": self.ready_for_transmission,
            "unchanged_payload_targets": list(self.unchanged_payload_targets),
            "targets": [target.to_dict() for target in self.targets],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        state = "READY" if self.ready_for_transmission else "BLOCKED"
        lines = [
            "# CODE V2-C hardware preflight",
            "",
            f"- Status: **{state}**",
            f"- Sent package SHA-256: `{self.sent_package_sha256}`",
            f"- Baseline SHA-256: `{self.baseline_sha256}`",
            f"- Restore bundle SHA-256: `{self.restore_bundle_sha256}`",
            f"- Device ID: `{self.profile.device_id}`",
            f"- Messages: `{self.profile.message_count}`",
            f"- User Waves: `{self.profile.wave_range}` ({len(self.profile.wave_addresses)})",
            (
                "- User Wavetable: "
                f"display `{self.profile.wavetable_display_number:03d}`, "
                f"internal `{self.profile.wavetable_internal_number}`"
            ),
            f"- Sound: `{self.profile.sound_location}`",
            f"- Every destination backed up: `{'yes' if self.all_targets_backed_up else 'no'}`",
            f"- Every destination payload changed: `{'yes' if self.all_targets_exercised else 'no'}`",
            "",
            "## Destination evidence",
            "",
            "| # | Type | Address | Destination | Payload differs from baseline |",
            "|---:|---|---:|---|---|",
        ]
        lines.extend(
            (
                f"| {item.index} | {item.identity.type_name} | "
                f"{item.identity.address} | {item.identity.label} | "
                f"{'yes' if item.payload_changed else 'no'} |"
            )
            for item in self.targets
        )
        if self.unchanged_payload_targets:
            lines.extend(
                [
                    "",
                    "## Blocking condition",
                    "",
                    "The following destinations already contain the same payload. An exact "
                    "read-back would not prove that those messages were written:",
                    "",
                ]
            )
            lines.extend(f"- {label}" for label in self.unchanged_payload_targets)
        return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class HardwarePreparationOutputPaths:
    restore_bundle: Path
    json_report: Path
    markdown_report: Path


@dataclass(frozen=True, slots=True)
class HardwarePreparation:
    sent_package: DumpFile
    baseline: DumpFile
    restore_bundle: DumpFile
    report: HardwarePreflightReport

    def write(
        self,
        directory: str | Path,
        *,
        stem: str = "CODE_V2_C_HARDWARE_TEST",
    ) -> HardwarePreparationOutputPaths:
        _validate_output_stem(stem)
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        restore_path = destination / f"{stem}.restore.syx"
        json_path = destination / f"{stem}.preflight.json"
        markdown_path = destination / f"{stem}.preflight.md"
        restore_path.write_bytes(self.restore_bundle.to_bytes())
        json_path.write_text(self.report.to_json(), encoding="utf-8", newline="\n")
        markdown_path.write_text(
            self.report.to_markdown(), encoding="utf-8", newline="\n"
        )
        return HardwarePreparationOutputPaths(
            restore_path, json_path, markdown_path
        )


@dataclass(frozen=True, slots=True)
class MessageComparison:
    index: int
    identity: MessageIdentity
    status: ComparisonStatus
    expected_device_id: int
    observed_device_id: int | None
    observed_address: int | None
    expected_message_sha256: str
    observed_message_sha256: str | None
    differing_payload_offsets: tuple[int, ...] = ()
    note: str = ""

    @property
    def label(self) -> str:
        return self.identity.label

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "dump_type": self.identity.type_name,
            "expected_address": self.identity.address,
            "destination": self.identity.label,
            "status": self.status.value,
            "expected_device_id": self.expected_device_id,
            "observed_device_id": self.observed_device_id,
            "observed_address": self.observed_address,
            "expected_message_sha256": self.expected_message_sha256,
            "observed_message_sha256": self.observed_message_sha256,
            "differing_payload_offsets": list(self.differing_payload_offsets),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class HardwareReadbackReport:
    expected_sha256: str
    readback_sha256: str
    profile: HardwarePackageProfile
    comparisons: tuple[MessageComparison, ...]

    @property
    def status_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in ComparisonStatus}
        for comparison in self.comparisons:
            counts[comparison.status.value] += 1
        return {key: value for key, value in counts.items() if value}

    @property
    def exact_count(self) -> int:
        return sum(
            comparison.status is ComparisonStatus.EXACT
            for comparison in self.comparisons
        )

    @property
    def status(self) -> HardwareValidationStatus:
        statuses = {comparison.status for comparison in self.comparisons}
        if statuses == {ComparisonStatus.EXACT}:
            return HardwareValidationStatus.PASS_EXACT
        review_only = {
            ComparisonStatus.EXACT,
            ComparisonStatus.DEVICE_ID_CHANGED,
            ComparisonStatus.ADDRESS_CHANGED,
            ComparisonStatus.ADDRESS_AND_DEVICE_ID_CHANGED,
        }
        if statuses and statuses <= review_only:
            return HardwareValidationStatus.REVIEW_NORMALIZATION
        return HardwareValidationStatus.FAIL

    @property
    def passed_exactly(self) -> bool:
        return self.status is HardwareValidationStatus.PASS_EXACT

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "hardware_validation_status": self.status.value,
            "expected_sha256": self.expected_sha256,
            "readback_sha256": self.readback_sha256,
            "device_id": self.profile.device_id,
            "message_count": self.profile.message_count,
            "user_wave_count": len(self.profile.wave_addresses),
            "user_wave_range": self.profile.wave_range,
            "wavetable_display_number": self.profile.wavetable_display_number,
            "wavetable_internal_number": self.profile.wavetable_internal_number,
            "sound_destination": self.profile.sound_location,
            "exact_count": self.exact_count,
            "status_counts": self.status_counts,
            "comparisons": [item.to_dict() for item in self.comparisons],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# CODE V2-C read-back comparison",
            "",
            f"- Status: **{self.status.value}**",
            f"- Expected SHA-256: `{self.expected_sha256}`",
            f"- Read-back SHA-256: `{self.readback_sha256}`",
            f"- Expected messages: `{self.profile.message_count}`",
            f"- Exact matches: `{self.exact_count}`",
            f"- User Waves: `{self.profile.wave_range}` ({len(self.profile.wave_addresses)})",
            (
                "- User Wavetable: "
                f"display `{self.profile.wavetable_display_number:03d}`, "
                f"internal `{self.profile.wavetable_internal_number}`"
            ),
            f"- Sound: `{self.profile.sound_location}`",
            "",
            "## Status counts",
            "",
        ]
        lines.extend(
            f"- `{name}`: {count}" for name, count in self.status_counts.items()
        )
        lines.extend(
            [
                "",
                "## Message comparison",
                "",
                "| # | Type | Expected address | Destination | Status | Observed address | Payload offsets |",
                "|---:|---|---:|---|---|---:|---|",
            ]
        )
        for item in self.comparisons:
            offsets = ", ".join(str(offset) for offset in item.differing_payload_offsets)
            observed = "" if item.observed_address is None else str(item.observed_address)
            lines.append(
                f"| {item.index} | {item.identity.type_name} | {item.identity.address} | "
                f"{item.identity.label} | {item.status.value} | {observed} | {offsets} |"
            )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class HardwareReadbackOutputPaths:
    json_report: Path
    markdown_report: Path
    extracted_targets: Path


@dataclass(frozen=True, slots=True)
class HardwareReadbackResult:
    expected: DumpFile
    readback: DumpFile
    extracted_targets: DumpFile
    report: HardwareReadbackReport

    def write(
        self,
        directory: str | Path,
        *,
        stem: str = "CODE_V2_C_READBACK",
    ) -> HardwareReadbackOutputPaths:
        _validate_output_stem(stem)
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        json_path = destination / f"{stem}.comparison.json"
        markdown_path = destination / f"{stem}.comparison.md"
        extracted_path = destination / f"{stem}.readback-targets.syx"
        json_path.write_text(self.report.to_json(), encoding="utf-8", newline="\n")
        markdown_path.write_text(
            self.report.to_markdown(), encoding="utf-8", newline="\n"
        )
        extracted_path.write_bytes(self.extracted_targets.to_bytes())
        return HardwareReadbackOutputPaths(
            json_path, markdown_path, extracted_path
        )


def inspect_hardware_package(
    package: DumpFile,
    *,
    required_wave_count: int | None = 61,
    require_package_links: bool = True,
) -> HardwarePackageProfile:
    if not package.messages:
        raise HardwareValidationError("Hardware package is empty")

    issues = package.validate()
    if issues:
        raise HardwareValidationError(
            "Hardware package contains invalid messages: " + "; ".join(issues)
        )

    device_ids = package.device_ids
    if len(device_ids) != 1:
        raise HardwareValidationError(
            f"Hardware package must use one Device ID, got {device_ids}"
        )
    device_id = device_ids[0]
    if not 0 <= device_id <= 126:
        raise HardwareValidationError(
            "Hardware validation packages must target one direct Device ID in 0..126; "
            f"got {device_id}"
        )

    wave_messages = tuple(
        message
        for message in package.messages
        if int(message.dump_type) == int(DumpType.USER_WAVE)
    )
    table_messages = tuple(
        message
        for message in package.messages
        if int(message.dump_type) == int(DumpType.USER_WAVETABLE)
    )
    sound_messages = tuple(
        message
        for message in package.messages
        if int(message.dump_type) == int(DumpType.SOUND)
    )

    allowed_count = len(wave_messages) + len(table_messages) + len(sound_messages)
    if allowed_count != len(package.messages):
        raise HardwareValidationError(
            "Hardware package may contain only USER_WAVE, USER_WAVETABLE, and SOUND messages"
        )
    if len(table_messages) != 1 or len(sound_messages) != 1:
        raise HardwareValidationError(
            "Hardware package must contain exactly one USER_WAVETABLE and one SOUND message"
        )
    if required_wave_count is not None and len(wave_messages) != required_wave_count:
        raise HardwareValidationError(
            f"Hardware package must contain {required_wave_count} USER_WAVE messages, "
            f"got {len(wave_messages)}"
        )
    if not wave_messages:
        raise HardwareValidationError("Hardware package must contain at least one USER_WAVE")

    expected_order = (
        (int(DumpType.USER_WAVE),) * len(wave_messages)
        + (int(DumpType.USER_WAVETABLE), int(DumpType.SOUND))
    )
    actual_order = tuple(int(message.dump_type) for message in package.messages)
    if actual_order != expected_order:
        raise HardwareValidationError(
            "Hardware package order must be USER_WAVE... → USER_WAVETABLE → SOUND"
        )

    wave_addresses = tuple(message.address for message in wave_messages)
    if len(set(wave_addresses)) != len(wave_addresses):
        raise HardwareValidationError("USER_WAVE destination addresses must be unique")
    if any(
        not USER_WAVE_FIRST <= address <= USER_WAVE_LAST
        for address in wave_addresses
    ):
        raise HardwareValidationError("USER_WAVE destination outside 1000..1249")
    expected_addresses = tuple(
        range(wave_addresses[0], wave_addresses[0] + len(wave_addresses))
    )
    if wave_addresses != expected_addresses:
        raise HardwareValidationError(
            "USER_WAVE destination addresses must be consecutive and ordered"
        )

    table_message = table_messages[0]
    if not (
        USER_WAVETABLE_INTERNAL_FIRST
        <= table_message.address
        <= USER_WAVETABLE_INTERNAL_LAST
    ):
        raise HardwareValidationError(
            f"USER_WAVETABLE internal address out of range: {table_message.address}"
        )
    wavetable = UserWavetable.from_message(table_message)
    destination_set = set(wave_addresses)
    if require_package_links:
        unresolved_user_waves = tuple(
            sorted(
                {
                    reference
                    for reference in wavetable.references[:61]
                    if USER_WAVE_FIRST <= reference <= USER_WAVE_LAST
                    and reference not in destination_set
                }
            )
        )
        if unresolved_user_waves:
            raise HardwareValidationError(
                "USER_WAVETABLE references USER_WAVE destinations not present in the package: "
                + ", ".join(str(value) for value in unresolved_user_waves)
            )

    sound_message = sound_messages[0]
    if not 0 <= sound_message.address <= 255:
        raise HardwareValidationError(
            f"SOUND destination outside A001..B128: {sound_message.address}"
        )
    sound = SoundProgram.from_message(sound_message)
    if (
        require_package_links
        and sound.data[PATCH_WAVETABLE_OFFSET] != table_message.address
    ):
        raise HardwareValidationError(
            "SOUND Wavetable parameter does not point to the packaged USER_WAVETABLE"
        )

    identities = tuple(
        MessageIdentity(int(message.dump_type), message.address)
        for message in package.messages
    )
    if len(set(identities)) != len(identities):
        raise HardwareValidationError("Hardware package contains duplicate destinations")

    return HardwarePackageProfile(
        device_id=device_id,
        wave_addresses=wave_addresses,
        wavetable_internal_number=table_message.address,
        sound_address=sound_message.address,
        message_count=len(package.messages),
        required_wave_count=required_wave_count,
    )


def prepare_hardware_validation(
    sent_package: DumpFile,
    baseline: DumpFile,
    *,
    required_wave_count: int | None = 61,
) -> HardwarePreparation:
    profile = inspect_hardware_package(
        sent_package, required_wave_count=required_wave_count
    )
    baseline_index = _index_messages(baseline.messages)

    restore_messages: list[SysExMessage] = []
    evidence: list[BaselineTargetEvidence] = []
    for index, sent_message in enumerate(sent_package.messages, start=1):
        identity = MessageIdentity(int(sent_message.dump_type), sent_message.address)
        matches = baseline_index.get(identity, ())
        if not matches:
            raise HardwareValidationError(
                f"Baseline backup is missing {identity.label}"
            )
        if len(matches) != 1:
            raise HardwareValidationError(
                f"Baseline backup contains {len(matches)} copies of {identity.label}"
            )
        baseline_message = matches[0]
        restore_messages.append(baseline_message)
        evidence.append(
            BaselineTargetEvidence(
                index=index,
                identity=identity,
                sent_payload_sha256=_payload_sha256(sent_message),
                baseline_payload_sha256=_payload_sha256(baseline_message),
                payload_changed=sent_message.payload != baseline_message.payload,
            )
        )

    restore_bundle = DumpFile(tuple(restore_messages))
    restore_bytes = restore_bundle.to_bytes()
    reparsed_restore = DumpFile.from_bytes(restore_bytes)
    if reparsed_restore.to_bytes() != restore_bytes:
        raise HardwareValidationError(
            "Generated restore bundle failed strict internal round-trip"
        )

    sent_bytes = sent_package.to_bytes()
    baseline_bytes = baseline.to_bytes()
    report = HardwarePreflightReport(
        sent_package_sha256=sha256(sent_bytes).hexdigest(),
        baseline_sha256=sha256(baseline_bytes).hexdigest(),
        restore_bundle_sha256=sha256(restore_bytes).hexdigest(),
        profile=profile,
        targets=tuple(evidence),
    )
    return HardwarePreparation(sent_package, baseline, restore_bundle, report)


def compare_hardware_readback(
    expected: DumpFile,
    readback: DumpFile,
    *,
    required_wave_count: int | None = 61,
    require_package_links: bool = True,
) -> HardwareReadbackResult:
    profile = inspect_hardware_package(
        expected,
        required_wave_count=required_wave_count,
        require_package_links=require_package_links,
    )
    readback_index = _index_messages(readback.messages)
    comparisons: list[MessageComparison] = []
    extracted: list[SysExMessage] = []

    for index, expected_message in enumerate(expected.messages, start=1):
        identity = MessageIdentity(
            int(expected_message.dump_type), expected_message.address
        )
        direct_matches = readback_index.get(identity, ())

        if len(direct_matches) > 1:
            comparisons.append(
                _comparison(
                    index,
                    identity,
                    expected_message,
                    ComparisonStatus.DUPLICATE,
                    note=f"Read-back contains {len(direct_matches)} copies at the expected destination",
                )
            )
            continue

        if len(direct_matches) == 1:
            observed = direct_matches[0]
            extracted.append(observed)
            if expected_message.to_bytes() == observed.to_bytes():
                status = ComparisonStatus.EXACT
                offsets: tuple[int, ...] = ()
                note = ""
            elif expected_message.payload == observed.payload:
                status = ComparisonStatus.DEVICE_ID_CHANGED
                offsets = ()
                note = "Payload and destination match; Device ID differs"
            else:
                status = ComparisonStatus.PAYLOAD_CHANGED
                offsets = _differing_offsets(
                    expected_message.payload, observed.payload
                )
                note = "Payload differs at the expected destination"
            comparisons.append(
                _comparison(
                    index,
                    identity,
                    expected_message,
                    status,
                    observed=observed,
                    differing_payload_offsets=offsets,
                    note=note,
                )
            )
            continue

        relocation_candidates = tuple(
            message
            for message in readback.messages
            if int(message.dump_type) == identity.dump_type
            and message.payload == expected_message.payload
        )
        if len(relocation_candidates) == 1:
            observed = relocation_candidates[0]
            extracted.append(observed)
            status = (
                ComparisonStatus.ADDRESS_CHANGED
                if observed.device_id == expected_message.device_id
                else ComparisonStatus.ADDRESS_AND_DEVICE_ID_CHANGED
            )
            comparisons.append(
                _comparison(
                    index,
                    identity,
                    expected_message,
                    status,
                    observed=observed,
                    note="Matching payload found at a different address",
                )
            )
        elif len(relocation_candidates) > 1:
            comparisons.append(
                _comparison(
                    index,
                    identity,
                    expected_message,
                    ComparisonStatus.AMBIGUOUS_RELOCATION,
                    note=(
                        f"Matching payload found at {len(relocation_candidates)} different addresses"
                    ),
                )
            )
        else:
            comparisons.append(
                _comparison(
                    index,
                    identity,
                    expected_message,
                    ComparisonStatus.MISSING,
                    note="No message found at the expected destination and no unique payload relocation found",
                )
            )

    report = HardwareReadbackReport(
        expected_sha256=sha256(expected.to_bytes()).hexdigest(),
        readback_sha256=sha256(readback.to_bytes()).hexdigest(),
        profile=profile,
        comparisons=tuple(comparisons),
    )
    return HardwareReadbackResult(
        expected=expected,
        readback=readback,
        extracted_targets=DumpFile(tuple(extracted)),
        report=report,
    )


def _index_messages(
    messages: Iterable[SysExMessage],
) -> dict[MessageIdentity, tuple[SysExMessage, ...]]:
    grouped: dict[MessageIdentity, list[SysExMessage]] = defaultdict(list)
    for message in messages:
        identity = MessageIdentity(int(message.dump_type), message.address)
        grouped[identity].append(message)
    return {identity: tuple(values) for identity, values in grouped.items()}


def _comparison(
    index: int,
    identity: MessageIdentity,
    expected: SysExMessage,
    status: ComparisonStatus,
    *,
    observed: SysExMessage | None = None,
    differing_payload_offsets: tuple[int, ...] = (),
    note: str = "",
) -> MessageComparison:
    return MessageComparison(
        index=index,
        identity=identity,
        status=status,
        expected_device_id=expected.device_id,
        observed_device_id=None if observed is None else observed.device_id,
        observed_address=None if observed is None else observed.address,
        expected_message_sha256=_message_sha256(expected),
        observed_message_sha256=(
            None if observed is None else _message_sha256(observed)
        ),
        differing_payload_offsets=differing_payload_offsets,
        note=note,
    )


def _differing_offsets(expected: bytes, observed: bytes) -> tuple[int, ...]:
    common = min(len(expected), len(observed))
    offsets = [index for index in range(common) if expected[index] != observed[index]]
    offsets.extend(range(common, max(len(expected), len(observed))))
    return tuple(offsets)


def _payload_sha256(message: SysExMessage) -> str:
    return sha256(message.payload).hexdigest()


def _message_sha256(message: SysExMessage) -> str:
    return sha256(message.to_bytes()).hexdigest()


def _validate_output_stem(stem: str) -> None:
    if not _OUTPUT_STEM_RE.fullmatch(stem):
        raise HardwareValidationError(
            "Output stem must contain 1..64 characters using letters, digits, '.', '_' or '-'"
        )
