from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

from ..destinations import DeviceAddress
from ..dump import DumpFile
from ..models import UserWave, UserWavetable
from .allocation import AllocationProposal, AllocationProposalStatus
from .consolidation import PhysicalWaveSet
from .materialization import MaterializedWctd, WctdMode
from .models import WavetableContractError

WAVETABLE_PACKAGE_V8K_SCHEMA_VERSION = 1
_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _strings(values: Sequence[str], *, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise WavetableContractError(f"{name} must be a sequence")
    result = tuple(values)
    if any(not isinstance(item, str) or not item for item in result):
        raise WavetableContractError(f"{name} must contain non-empty strings")
    if len(set(result)) != len(result):
        raise WavetableContractError(f"{name} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class WavetablePackageMessage:
    index: int
    kind: str
    destination: str
    byte_length: int
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.index, int) or isinstance(self.index, bool) or self.index < 1:
            raise WavetableContractError("message index must be positive")
        if self.kind not in {"WAVD", "WCTD"}:
            raise WavetableContractError("package message kind must be WAVD or WCTD")
        if not isinstance(self.destination, str) or not self.destination:
            raise WavetableContractError("message destination must not be empty")
        if not isinstance(self.byte_length, int) or self.byte_length <= 0:
            raise WavetableContractError("message byte_length must be positive")
        _sha256(self.sha256, name="message.sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "kind": self.kind,
            "destination": self.destination,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class WavetablePackageManifest:
    schema_version: int
    package_name: str
    mode: WctdMode
    device_id: int
    physical_wave_set_sha256: str
    allocation_sha256: str
    wctd_sha256: str
    package_sha256: str
    package_bytes: int
    user_wave_numbers: tuple[int, ...]
    user_wavetable_display_number: int
    overwrite_wave_numbers: tuple[int, ...]
    messages: tuple[WavetablePackageMessage, ...]
    warnings: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_PACKAGE_V8K_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-K package manifest schema version")
        if not _PACKAGE_RE.fullmatch(self.package_name):
            raise WavetableContractError("package_name must use 1..64 safe filename characters")
        if not isinstance(self.mode, WctdMode):
            raise WavetableContractError("mode must be WctdMode")
        if not 0 <= self.device_id <= 127:
            raise WavetableContractError("device_id must be in 0..127")
        for name in ("physical_wave_set_sha256", "allocation_sha256", "wctd_sha256", "package_sha256"):
            _sha256(getattr(self, name), name=name)
        if not isinstance(self.package_bytes, int) or self.package_bytes <= 0:
            raise WavetableContractError("package_bytes must be positive")
        numbers = tuple(self.user_wave_numbers)
        object.__setattr__(self, "user_wave_numbers", numbers)
        if not numbers or len(set(numbers)) != len(numbers):
            raise WavetableContractError("user_wave_numbers must be unique and non-empty")
        overwrites = tuple(self.overwrite_wave_numbers)
        object.__setattr__(self, "overwrite_wave_numbers", overwrites)
        if tuple(sorted(set(overwrites))) != overwrites:
            raise WavetableContractError("overwrite_wave_numbers must be sorted and unique")
        messages = tuple(self.messages)
        object.__setattr__(self, "messages", messages)
        if len(messages) != len(numbers) + 1:
            raise WavetableContractError("V8-K package must contain N WAVD plus one WCTD")
        if tuple(item.index for item in messages) != tuple(range(1, len(messages) + 1)):
            raise WavetableContractError("package message indices must be canonical")
        if any(item.kind != "WAVD" for item in messages[:-1]) or messages[-1].kind != "WCTD":
            raise WavetableContractError("V8-K package order must be all WAVD then WCTD")
        object.__setattr__(self, "warnings", _strings(self.warnings, name="warnings"))
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "package_name": self.package_name,
            "mode": self.mode.value,
            "device_id": self.device_id,
            "physical_wave_set_sha256": self.physical_wave_set_sha256,
            "allocation_sha256": self.allocation_sha256,
            "wctd_sha256": self.wctd_sha256,
            "package_sha256": self.package_sha256,
            "package_bytes": self.package_bytes,
            "message_count": self.message_count,
            "contract": "N WAVD + 1 WCTD",
            "user_wave_numbers": list(self.user_wave_numbers),
            "user_wavetable_display_number": self.user_wavetable_display_number,
            "overwrite_wave_numbers": list(self.overwrite_wave_numbers),
            "messages": [item.to_dict() for item in self.messages],
            "warnings": list(self.warnings),
            "boundaries": {
                "self_contained": True,
                "contains_sound": False,
                "complete_package_n_plus_2_implemented": False,
                "opens_midi_port": False,
                "transmits_midi": False,
                "writes_memory": False,
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


@dataclass(frozen=True, slots=True)
class WavetablePackage:
    schema_version: int
    physical_wave_set_sha256: str
    allocation_sha256: str
    wctd: MaterializedWctd
    waves: tuple[UserWave, ...]
    wavetable: UserWavetable
    dump: DumpFile
    manifest: WavetablePackageManifest

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_PACKAGE_V8K_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-K package schema version")
        _sha256(self.physical_wave_set_sha256, name="physical_wave_set_sha256")
        _sha256(self.allocation_sha256, name="allocation_sha256")
        if not isinstance(self.wctd, MaterializedWctd):
            raise WavetableContractError("wctd must be MaterializedWctd")
        waves = tuple(self.waves)
        object.__setattr__(self, "waves", waves)
        if not waves or any(not isinstance(item, UserWave) for item in waves):
            raise WavetableContractError("waves must contain UserWave values")
        if not isinstance(self.wavetable, UserWavetable):
            raise WavetableContractError("wavetable must be UserWavetable")
        if not isinstance(self.dump, DumpFile):
            raise WavetableContractError("dump must be DumpFile")
        if not isinstance(self.manifest, WavetablePackageManifest):
            raise WavetableContractError("manifest must be WavetablePackageManifest")
        package_bytes = self.dump.to_bytes()
        if sha256(package_bytes).hexdigest() != self.manifest.package_sha256:
            raise WavetableContractError("package bytes disagree with manifest hash")
        if self.manifest.message_count != len(self.dump.messages):
            raise WavetableContractError("package message count disagrees with manifest")

    @property
    def package_bytes(self) -> bytes:
        return self.dump.to_bytes()

    @property
    def sha256(self) -> str:
        return sha256(self.package_bytes).hexdigest()

    def write(self, directory: str | Path, *, stem: str | None = None) -> tuple[Path, Path]:
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        selected = self.manifest.package_name if stem is None else stem
        if not _PACKAGE_RE.fullmatch(selected):
            raise WavetableContractError("output stem must use 1..64 safe filename characters")
        syx = destination / f"{selected}.syx"
        manifest = destination / f"{selected}.manifest.json"
        syx.write_bytes(self.package_bytes)
        manifest.write_text(self.manifest.to_json(), encoding="utf-8", newline="\n")
        return syx, manifest

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "physical_wave_set_sha256": self.physical_wave_set_sha256,
            "allocation_sha256": self.allocation_sha256,
            "wctd": self.wctd.to_dict(),
            "manifest": self.manifest.to_dict(),
            "package_sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class CompletePackageContract:
    schema_version: int
    wavetable_package_sha256: str
    expected_message_count: int
    implemented_in_stage: str
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != WAVETABLE_PACKAGE_V8K_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported complete-package contract schema version")
        _sha256(self.wavetable_package_sha256, name="wavetable_package_sha256")
        if not isinstance(self.expected_message_count, int) or self.expected_message_count < 3:
            raise WavetableContractError("expected_message_count must represent N+2")
        if self.implemented_in_stage != "V9":
            raise WavetableContractError("Complete package implementation remains assigned to V9")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wavetable_package_sha256": self.wavetable_package_sha256,
            "contract": "N WAVD + 1 WCTD + 1 SNDD",
            "expected_message_count": self.expected_message_count,
            "implemented": False,
            "implemented_in_stage": self.implemented_in_stage,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self.to_dict())


def build_wavetable_package(
    physical_wave_set: PhysicalWaveSet,
    allocation: AllocationProposal,
    wctd: MaterializedWctd,
    device: DeviceAddress,
    *,
    package_name: str,
) -> WavetablePackage:
    if not isinstance(physical_wave_set, PhysicalWaveSet):
        raise WavetableContractError("physical_wave_set must be PhysicalWaveSet")
    if not isinstance(allocation, AllocationProposal) or allocation.status is not AllocationProposalStatus.READY:
        raise WavetableContractError("V8-K package requires a ready AllocationProposal")
    if not isinstance(wctd, MaterializedWctd):
        raise WavetableContractError("wctd must be MaterializedWctd")
    if not isinstance(device, DeviceAddress):
        raise WavetableContractError("device must be DeviceAddress")
    if not _PACKAGE_RE.fullmatch(package_name):
        raise WavetableContractError("package_name must use 1..64 safe filename characters")
    if allocation.physical_wave_set_sha256 != physical_wave_set.analysis_sha256:
        raise WavetableContractError("allocation does not match physical_wave_set")
    if wctd.allocation_sha256 != allocation.analysis_sha256:
        raise WavetableContractError("WCTD does not match allocation")
    if len(allocation.assignments) != physical_wave_set.physical_wave_count:
        raise WavetableContractError("assignment count disagrees with physical wave count")

    waves: list[UserWave] = []
    for physical, assignment in zip(physical_wave_set.waves, allocation.assignments, strict=True):
        if physical.physical_index != assignment.physical_index:
            raise WavetableContractError("physical and allocation indices disagree")
        if physical.analysis_sha256 != assignment.physical_wave_sha256:
            raise WavetableContractError("physical wave hash disagrees with allocation")
        waves.append(UserWave(device.value, assignment.user_wave_number, physical.stored_samples))

    wavetable = wctd.to_user_wavetable(device.value)
    messages = tuple(wave.to_message() for wave in waves) + (wavetable.to_message(),)
    for message in messages:
        message.assert_valid(strict_length=True)
    if len(messages[-1].to_bytes()) != 265:
        raise WavetableContractError("WCTD SysEx message must contain exactly 265 bytes")
    dump = DumpFile(messages)
    package_bytes = dump.to_bytes()
    reparsed = DumpFile.from_bytes(package_bytes)
    if reparsed.to_bytes() != package_bytes:
        raise WavetableContractError("V8-K package failed strict round-trip")

    manifest_messages: list[WavetablePackageMessage] = []
    for index, message in enumerate(messages, start=1):
        raw = message.to_bytes()
        is_wctd = index == len(messages)
        manifest_messages.append(
            WavetablePackageMessage(
                index=index,
                kind="WCTD" if is_wctd else "WAVD",
                destination=(
                    f"User Wavetable {wctd.user_wavetable_destination.display_number:03d}"
                    if is_wctd
                    else f"User Wave {message.address}"
                ),
                byte_length=len(raw),
                sha256=sha256(raw).hexdigest(),
            )
        )
    warnings = list(wctd.warnings)
    warnings.append("Package generation is offline only; backup, controlled transmission, redump and restore remain mandatory.")
    if device.is_broadcast:
        warnings.append("Device ID 127 broadcast was selected explicitly; V8-K does not transmit it.")
    manifest = WavetablePackageManifest(
        schema_version=WAVETABLE_PACKAGE_V8K_SCHEMA_VERSION,
        package_name=package_name,
        mode=wctd.mode,
        device_id=device.value,
        physical_wave_set_sha256=physical_wave_set.analysis_sha256,
        allocation_sha256=allocation.analysis_sha256,
        wctd_sha256=wctd.analysis_sha256,
        package_sha256=sha256(package_bytes).hexdigest(),
        package_bytes=len(package_bytes),
        user_wave_numbers=tuple(item.number for item in waves),
        user_wavetable_display_number=wctd.user_wavetable_destination.display_number,
        overwrite_wave_numbers=allocation.overwrite_wave_numbers,
        messages=tuple(manifest_messages),
        warnings=tuple(warnings),
        reason="V8-K built a deterministic self-contained N+1 package ordered as N WAVD followed by one WCTD.",
    )
    return WavetablePackage(
        schema_version=WAVETABLE_PACKAGE_V8K_SCHEMA_VERSION,
        physical_wave_set_sha256=physical_wave_set.analysis_sha256,
        allocation_sha256=allocation.analysis_sha256,
        wctd=wctd,
        waves=tuple(waves),
        wavetable=wavetable,
        dump=dump,
        manifest=manifest,
    )


def complete_package_contract(package: WavetablePackage) -> CompletePackageContract:
    if not isinstance(package, WavetablePackage):
        raise WavetableContractError("package must be WavetablePackage")
    return CompletePackageContract(
        schema_version=WAVETABLE_PACKAGE_V8K_SCHEMA_VERSION,
        wavetable_package_sha256=package.sha256,
        expected_message_count=len(package.waves) + 2,
        implemented_in_stage="V9",
        reason="V8-K defines the N+2 contract but intentionally does not generate SNDD; Sound integration remains V9.",
    )


__all__ = [
    "WAVETABLE_PACKAGE_V8K_SCHEMA_VERSION",
    "WavetablePackageMessage",
    "WavetablePackageManifest",
    "WavetablePackage",
    "CompletePackageContract",
    "build_wavetable_package",
    "complete_package_contract",
]
