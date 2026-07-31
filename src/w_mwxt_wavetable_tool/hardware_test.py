from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .allocation import UserWaveAllocation
from .constants import PATCH_NAME_LENGTH, USER_WAVE_LAST, DumpType
from .destinations import (
    DeviceAddress,
    SoundDestination,
    UserWavetableDestination,
)
from .dump import DumpFile
from .errors import HardwareValidationError
from .hardware_validation import (
    HardwarePreparation,
    HardwarePreparationOutputPaths,
    prepare_hardware_validation,
)
from .message import SysExMessage
from .models import SoundProgram, UserWave, UserWavetable
from .package import (
    PackageBuildResult,
    PackageOutputPaths,
    PackageRequest,
    build_package,
)


@dataclass(frozen=True, slots=True)
class HardwareTestBuildOutputPaths:
    package: PackageOutputPaths
    preflight: HardwarePreparationOutputPaths


@dataclass(frozen=True, slots=True)
class HardwareTestBuild:
    package_result: PackageBuildResult
    preparation: HardwarePreparation
    adjustments: tuple[str, ...]

    @property
    def ready_for_transmission(self) -> bool:
        return self.preparation.report.ready_for_transmission

    def write(
        self,
        directory: str | Path,
        *,
        stem: str = "CODE_V2_C_HARDWARE_TEST",
    ) -> HardwareTestBuildOutputPaths:
        package_paths = self.package_result.write(directory, stem=stem)
        preflight_paths = self.preparation.write(directory, stem=stem)
        return HardwareTestBuildOutputPaths(package_paths, preflight_paths)


def build_hardware_test_from_backup(
    baseline: DumpFile,
    *,
    source_wave_start: int,
    source_wavetable_display: int,
    source_sound: SoundDestination | str,
    target_wave_start: int,
    target_wavetable_display: int,
    target_sound: SoundDestination | str,
    sound_name: str = "V2C READBACK",
    package_name: str = "CODE_V2_C_HARDWARE_TEST",
) -> HardwareTestBuild:
    """Build and preflight a 61-WAVD hardware acceptance package.

    The source backup is never modified. Sixty-one consecutive source User Waves
    are copied into sixty-one separate target destinations. When a copied source
    payload already equals the target payload, one stored sample is changed by one
    int8 step so that an exact read-back can prove that message was actually
    written. The generated Wavetable references all 61 target waves and preserves
    the three fixed-tail references from the selected source Wavetable.

    Source and target destinations must not overlap. Transmission remains manual;
    this function only creates files and evidence.
    """

    if source_wave_start + 60 > USER_WAVE_LAST:
        raise HardwareValidationError(
            "Source User Wave range must fit 61 consecutive waves inside 1000..1249"
        )

    source_sound_destination = _coerce_stored_sound(source_sound, "source_sound")
    target_sound_destination = _coerce_stored_sound(target_sound, "target_sound")
    target_wavetable = UserWavetableDestination(target_wavetable_display)
    source_wavetable = UserWavetableDestination(source_wavetable_display)
    allocation = UserWaveAllocation.complete_table(target_wave_start)

    source_wave_numbers = tuple(range(source_wave_start, source_wave_start + 61))
    target_wave_numbers = allocation.numbers
    overlap = tuple(sorted(set(source_wave_numbers) & set(target_wave_numbers)))
    if overlap:
        raise HardwareValidationError(
            "Source and target User Wave ranges must not overlap; overlap: "
            + f"{overlap[0]}..{overlap[-1]}"
        )
    if source_wavetable.internal_number == target_wavetable.internal_number:
        raise HardwareValidationError(
            "Source and target User Wavetable destinations must be different"
        )
    if source_sound_destination == target_sound_destination:
        raise HardwareValidationError(
            "Source and target Sound destinations must be different"
        )

    if len(baseline.device_ids) != 1:
        raise HardwareValidationError(
            f"Baseline backup must contain one Device ID, got {baseline.device_ids}"
        )
    device = DeviceAddress(baseline.device_ids[0])

    index = _unique_message_index(baseline)
    raw_source_waves = tuple(
        UserWave.from_message(
            _require_message(
                index,
                DumpType.USER_WAVE,
                source_wave_start + offset,
                f"source User Wave {source_wave_start + offset}",
            )
        )
        for offset in range(61)
    )
    target_baseline_waves = tuple(
        UserWave.from_message(
            _require_message(
                index,
                DumpType.USER_WAVE,
                target_wave_start + offset,
                f"target User Wave {target_wave_start + offset}",
            )
        )
        for offset in range(61)
    )
    source_table_model = UserWavetable.from_message(
        _require_message(
            index,
            DumpType.USER_WAVETABLE,
            source_wavetable.internal_number,
            f"source User Wavetable {source_wavetable.display_number:03d}",
        )
    )
    target_table_baseline = UserWavetable.from_message(
        _require_message(
            index,
            DumpType.USER_WAVETABLE,
            target_wavetable.internal_number,
            f"target User Wavetable {target_wavetable.display_number:03d}",
        )
    )
    source_sound_address = source_sound_destination.wire_address
    target_sound_address = target_sound_destination.wire_address
    assert source_sound_address is not None and target_sound_address is not None
    source_sound_model = SoundProgram.from_message(
        _require_message(
            index,
            DumpType.SOUND,
            source_sound_address,
            f"source Sound {source_sound_destination.display_location}",
        )
    )
    target_sound_baseline = SoundProgram.from_message(
        _require_message(
            index,
            DumpType.SOUND,
            target_sound_address,
            f"target Sound {target_sound_destination.display_location}",
        )
    )

    adjustments: list[str] = []
    source_waves: list[UserWave] = []
    for offset, (source_wave, target_wave) in enumerate(
        zip(raw_source_waves, target_baseline_waves, strict=True)
    ):
        selected = source_wave
        if source_wave.payload == target_wave.payload:
            samples = list(source_wave.stored_samples)
            sample_index = offset % len(samples)
            samples[sample_index] = _next_int8(samples[sample_index])
            selected = replace(source_wave, stored_samples=tuple(samples))
            adjustments.append(
                f"User Wave {target_wave.number}: changed stored sample {sample_index} "
                "by one int8 step because source and target payloads were identical"
            )
        source_waves.append(selected)

    table_source_numbers = tuple(wave.number for wave in source_waves)
    target_references = target_wave_numbers + source_table_model.references[61:]
    if target_references == target_table_baseline.references:
        table_source_numbers = table_source_numbers[1:] + table_source_numbers[:1]
        adjustments.append(
            "User Wavetable: rotated the 61 test references by one position because "
            "the initial payload matched the target baseline"
        )
    test_references = table_source_numbers + source_table_model.references[61:]
    test_source_table = UserWavetable(
        device_id=device.value,
        internal_number=source_table_model.internal_number,
        references=test_references,
    )

    package_result = _build(
        device=device,
        source_waves=tuple(source_waves),
        allocation=allocation,
        source_table=test_source_table,
        target_wavetable=target_wavetable,
        source_sound=source_sound_model,
        target_sound=target_sound_destination,
        sound_name=sound_name,
        package_name=package_name,
    )

    generated_sound = SoundProgram.from_message(package_result.dump.messages[-1])
    if generated_sound.data == target_sound_baseline.data:
        alternate_name = _alternate_sound_name(sound_name)
        adjustments.append(
            f"Sound: changed test name from {sound_name!r} to {alternate_name!r} "
            "because the initial payload matched the target baseline"
        )
        package_result = _build(
            device=device,
            source_waves=tuple(source_waves),
            allocation=allocation,
            source_table=test_source_table,
            target_wavetable=target_wavetable,
            source_sound=source_sound_model,
            target_sound=target_sound_destination,
            sound_name=alternate_name,
            package_name=package_name,
        )

    if adjustments:
        package_result = replace(
            package_result,
            manifest=replace(
                package_result.manifest,
                warnings=package_result.manifest.warnings
                + tuple(f"Hardware test marker: {item}" for item in adjustments),
            ),
        )

    preparation = prepare_hardware_validation(
        package_result.dump,
        baseline,
        required_wave_count=61,
    )
    return HardwareTestBuild(package_result, preparation, tuple(adjustments))


def _build(
    *,
    device: DeviceAddress,
    source_waves: tuple[UserWave, ...],
    allocation: UserWaveAllocation,
    source_table: UserWavetable,
    target_wavetable: UserWavetableDestination,
    source_sound: SoundProgram,
    target_sound: SoundDestination,
    sound_name: str,
    package_name: str,
) -> PackageBuildResult:
    request = PackageRequest(
        device=device,
        source_waves=source_waves,
        allocation=allocation,
        source_wavetable=source_table,
        wavetable_destination=target_wavetable,
        source_sound=source_sound,
        sound_destination=target_sound,
        sound_name=sound_name,
        package_name=package_name,
    )
    return build_package(request)


def _next_int8(value: int) -> int:
    return -128 if value == 127 else value + 1


def _alternate_sound_name(name: str) -> str:
    base = name[: PATCH_NAME_LENGTH - 1]
    marker = "!" if not base.endswith("!") else "?"
    return base + marker


def _coerce_stored_sound(
    value: SoundDestination | str,
    field_name: str,
) -> SoundDestination:
    destination = (
        value if isinstance(value, SoundDestination) else SoundDestination.parse(value)
    )
    if destination.is_edit_buffer:
        raise HardwareValidationError(
            f"{field_name} must be a stored Sound destination A001..B128"
        )
    return destination


def _unique_message_index(
    dump: DumpFile,
) -> dict[tuple[int, int], SysExMessage]:
    index: dict[tuple[int, int], SysExMessage] = {}
    duplicates: set[tuple[int, int]] = set()
    for message in dump.messages:
        key = (int(message.dump_type), message.address)
        if key in index:
            duplicates.add(key)
        else:
            index[key] = message
    if duplicates:
        formatted = ", ".join(
            f"type=0x{dump_type:02X} address={address}"
            for dump_type, address in sorted(duplicates)
        )
        raise HardwareValidationError(
            "Baseline backup contains duplicate message destinations: " + formatted
        )
    return index


def _require_message(
    index: dict[tuple[int, int], SysExMessage],
    dump_type: DumpType,
    address: int,
    label: str,
) -> SysExMessage:
    try:
        return index[(int(dump_type), address)]
    except KeyError as exc:
        raise HardwareValidationError(
            f"Baseline backup is missing {label}"
        ) from exc
