from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from .allocation import UserWaveAllocation
from .constants import (
    INTERPOLATED_WAVE_REFERENCE,
    PATCH_NAME_LENGTH,
    PATCH_NAME_OFFSET,
    PATCH_WAVETABLE_OFFSET,
    USER_WAVE_FIRST,
    USER_WAVE_LAST,
    DumpType,
)
from .destinations import (
    DeviceAddress,
    SoundDestination,
    SoundNamePolicy,
    UserWavetableDestination,
    encode_sound_name,
)
from .dump import DumpFile
from .errors import PackageBuildError
from .manifest import ManifestMessage, ManifestWaveMapping, PackageManifest
from .models import SoundProgram, UserWave, UserWavetable
from .safety import (
    CollisionReport,
    MemoryTarget,
    OverwritePlan,
    analyze_collisions,
)

_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_FIXED_POSITION_WARNING = (
    "Wavetable positions 61, 62, and 63 are preserved in the WCTD payload; "
    "the Microwave XT is expected to expose its fixed Triangle, Square/Pulse, and Saw forms there."
)
_READBACK_WARNING = (
    "Hardware write behavior is not validated by package generation; perform a backup, "
    "controlled transmission, redump, and byte comparison."
)


@dataclass(frozen=True, slots=True)
class PackageRequest:
    """All inputs required to plan and build one deterministic XT package."""

    device: DeviceAddress
    source_waves: tuple[UserWave, ...]
    allocation: UserWaveAllocation
    source_wavetable: UserWavetable
    wavetable_destination: UserWavetableDestination
    source_sound: SoundProgram
    sound_destination: SoundDestination
    sound_name: str
    sound_name_policy: SoundNamePolicy | str = SoundNamePolicy.REJECT
    package_name: str = "MICROWAVE_XT_PACKAGE"
    reserved_targets: tuple[MemoryTarget, ...] = ()
    require_self_contained: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_waves", tuple(self.source_waves))
        object.__setattr__(self, "reserved_targets", tuple(self.reserved_targets))
        if not _PACKAGE_NAME_RE.fullmatch(self.package_name):
            raise PackageBuildError(
                "Package name must contain 1..64 characters using letters, digits, '.', '_' or '-'"
            )
        if not all(isinstance(wave, UserWave) for wave in self.source_waves):
            raise PackageBuildError("source_waves must contain only UserWave objects")
        if len(self.source_sound.data) != 256:
            raise PackageBuildError(
                f"Source Sound payload must contain 256 bytes, got {len(self.source_sound.data)}"
            )
        encode_sound_name(self.sound_name, policy=self.sound_name_policy)

    @property
    def overwrite_plan(self) -> OverwritePlan:
        return OverwritePlan(
            user_waves=self.allocation,
            user_wavetable=self.wavetable_destination,
            sound=self.sound_destination,
        )


@dataclass(frozen=True, slots=True)
class PackagePlan:
    request: PackageRequest
    wave_mapping: tuple[tuple[int, int], ...]
    collision_report: CollisionReport
    warnings: tuple[str, ...]

    @property
    def overwrite_plan(self) -> OverwritePlan:
        return self.request.overwrite_plan

    @property
    def message_count(self) -> int:
        return len(self.wave_mapping) + 2

    @property
    def message_order(self) -> tuple[str, ...]:
        wave_labels = tuple(
            f"WAVD {destination}" for _, destination in self.wave_mapping
        )
        return wave_labels + (
            f"WCTD {self.request.wavetable_destination.display_number:03d}",
            f"SNDD {self.request.sound_destination.display_location}",
        )

    def assert_buildable(self) -> None:
        self.collision_report.assert_safe()
        if self.request.sound_destination.is_edit_buffer:
            raise PackageBuildError(
                "Edit Buffer is a valid semantic destination, but its SNDD wire address "
                "has not been confirmed. Build to A001–A128 or B001–B128 until the "
                "hardware address is validated."
            )


@dataclass(frozen=True, slots=True)
class PackageOutputPaths:
    sysex: Path
    json_manifest: Path
    markdown_manifest: Path


@dataclass(frozen=True, slots=True)
class PackageBuildResult:
    request: PackageRequest
    plan: PackagePlan
    dump: DumpFile
    manifest: PackageManifest

    @property
    def package_bytes(self) -> bytes:
        return self.dump.to_bytes()

    @property
    def sha256(self) -> str:
        return sha256(self.package_bytes).hexdigest()

    def write(
        self,
        directory: str | Path,
        *,
        stem: str | None = None,
    ) -> PackageOutputPaths:
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        selected_stem = self.request.package_name if stem is None else stem
        if not _PACKAGE_NAME_RE.fullmatch(selected_stem):
            raise PackageBuildError(
                "Output stem must contain 1..64 characters using letters, digits, '.', '_' or '-'"
            )
        sysex = destination / f"{selected_stem}.syx"
        json_manifest = destination / f"{selected_stem}.manifest.json"
        markdown_manifest = destination / f"{selected_stem}.manifest.md"
        sysex.write_bytes(self.package_bytes)
        json_manifest.write_text(self.manifest.to_json(), encoding="utf-8", newline="\n")
        markdown_manifest.write_text(
            self.manifest.to_markdown(), encoding="utf-8", newline="\n"
        )
        return PackageOutputPaths(sysex, json_manifest, markdown_manifest)


def plan_package(request: PackageRequest) -> PackagePlan:
    if len(request.source_waves) != request.allocation.count:
        raise PackageBuildError(
            f"Wave count mismatch: got {len(request.source_waves)} source waves for "
            f"an allocation of {request.allocation.count}"
        )

    source_numbers = tuple(wave.number for wave in request.source_waves)
    if len(set(source_numbers)) != len(source_numbers):
        raise PackageBuildError("Source User Wave numbers must be unique")

    wave_mapping = tuple(zip(source_numbers, request.allocation.numbers, strict=True))
    collision_report = analyze_collisions(
        request.overwrite_plan.targets,
        reserved=request.reserved_targets,
    )

    warnings = [_FIXED_POSITION_WARNING, _READBACK_WARNING]
    if request.device.is_broadcast:
        warnings.insert(0, "Package uses Device ID 127 broadcast by explicit request.")
    if not request.require_self_contained:
        warnings.insert(
            0,
            "Self-contained validation is disabled; the Wavetable may reference User Waves not included in this package.",
        )
    if request.sound_destination.is_edit_buffer:
        warnings.insert(
            0,
            "Edit Buffer planning is allowed, but binary package generation is blocked until the SNDD wire address is confirmed.",
        )

    return PackagePlan(
        request=request,
        wave_mapping=wave_mapping,
        collision_report=collision_report,
        warnings=tuple(warnings),
    )


def build_package(request: PackageRequest) -> PackageBuildResult:
    plan = plan_package(request)
    plan.assert_buildable()

    source_to_destination = dict(plan.wave_mapping)
    destination_numbers = frozenset(request.allocation.numbers)

    waves = tuple(
        UserWave(
            device_id=request.device.value,
            number=destination_number,
            stored_samples=source_wave.stored_samples,
        )
        for source_wave, destination_number in zip(
            request.source_waves,
            request.allocation.numbers,
            strict=True,
        )
    )

    references = list(request.source_wavetable.references)
    for index in range(61):
        reference = references[index]
        if reference in source_to_destination:
            references[index] = source_to_destination[reference]

    unresolved = tuple(
        sorted(
            {
                reference
                for reference in references[:61]
                if USER_WAVE_FIRST <= reference <= USER_WAVE_LAST
                and reference not in destination_numbers
            }
        )
    )
    if request.require_self_contained and unresolved:
        unresolved_text = ", ".join(str(number) for number in unresolved)
        raise PackageBuildError(
            "Wavetable references User Waves not included in this package: "
            + unresolved_text
        )

    wavetable = UserWavetable(
        device_id=request.device.value,
        internal_number=request.wavetable_destination.internal_number,
        references=tuple(references),
    )

    wire_address = request.sound_destination.wire_address
    if wire_address is None:
        raise PackageBuildError("Sound destination has no confirmed wire address")

    sound_data = bytearray(request.source_sound.data)
    sound_data[PATCH_WAVETABLE_OFFSET] = request.wavetable_destination.internal_number
    sound_data[
        PATCH_NAME_OFFSET : PATCH_NAME_OFFSET + PATCH_NAME_LENGTH
    ] = encode_sound_name(request.sound_name, policy=request.sound_name_policy)
    sound = SoundProgram(
        device_id=request.device.value,
        bank=wire_address >> 7,
        slot=wire_address & 0x7F,
        data=bytes(sound_data),
    )

    messages = tuple(wave.to_message() for wave in waves) + (
        wavetable.to_message(),
        sound.to_message(),
    )
    for message in messages:
        message.assert_valid(strict_length=True)

    dump = DumpFile(messages)
    package_bytes = dump.to_bytes()
    reparsed = DumpFile.from_bytes(package_bytes)
    if reparsed.to_bytes() != package_bytes:
        raise PackageBuildError("Generated package failed strict internal round-trip")

    manifest = _build_manifest(
        request=request,
        plan=plan,
        dump=dump,
        package_bytes=package_bytes,
        sound=sound,
    )
    return PackageBuildResult(request, plan, dump, manifest)


def _build_manifest(
    *,
    request: PackageRequest,
    plan: PackagePlan,
    dump: DumpFile,
    package_bytes: bytes,
    sound: SoundProgram,
) -> PackageManifest:
    message_entries: list[ManifestMessage] = []
    for index, message in enumerate(dump.messages, start=1):
        try:
            dump_type = DumpType(int(message.dump_type))
            type_name = dump_type.name
        except ValueError:
            type_name = f"UNKNOWN_{int(message.dump_type):02X}"

        if int(message.dump_type) == int(DumpType.USER_WAVE):
            destination = f"User Wave {message.address}"
        elif int(message.dump_type) == int(DumpType.USER_WAVETABLE):
            destination = (
                f"User Wavetable {request.wavetable_destination.display_number:03d}"
            )
        elif int(message.dump_type) == int(DumpType.SOUND):
            destination = f"Sound {request.sound_destination.display_location}"
        else:
            destination = str(message.address)

        message_entries.append(
            ManifestMessage(
                index=index,
                dump_type=type_name,
                address=message.address,
                destination=destination,
                byte_length=len(message.to_bytes()),
                checksum=message.computed_checksum,
            )
        )

    return PackageManifest(
        package_name=request.package_name,
        device_id=request.device.value,
        broadcast=request.device.is_broadcast,
        package_bytes=len(package_bytes),
        package_sha256=sha256(package_bytes).hexdigest(),
        message_count=len(dump.messages),
        user_wave_count=request.allocation.count,
        user_wave_range=request.allocation.display_range,
        wavetable_display_number=request.wavetable_destination.display_number,
        wavetable_internal_number=request.wavetable_destination.internal_number,
        sound_destination=request.sound_destination.display_location,
        sound_name=sound.name,
        self_contained=request.require_self_contained,
        overwrite_targets=request.overwrite_plan.labels,
        wave_mapping=tuple(
            ManifestWaveMapping(source, destination)
            for source, destination in plan.wave_mapping
        ),
        messages=tuple(message_entries),
        warnings=plan.warnings,
    )
