from __future__ import annotations

from dataclasses import asdict, dataclass
import json


MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ManifestWaveMapping:
    source_number: int
    destination_number: int


@dataclass(frozen=True, slots=True)
class ManifestMessage:
    index: int
    dump_type: str
    address: int
    destination: str
    byte_length: int
    checksum: int


@dataclass(frozen=True, slots=True)
class PackageManifest:
    """Public, deterministic description of one generated SysEx package."""

    package_name: str
    device_id: int
    broadcast: bool
    package_bytes: int
    package_sha256: str
    message_count: int
    user_wave_count: int
    user_wave_range: str
    wavetable_display_number: int
    wavetable_internal_number: int
    sound_destination: str
    sound_name: str
    self_contained: bool
    overwrite_targets: tuple[str, ...]
    wave_mapping: tuple[ManifestWaveMapping, ...]
    messages: tuple[ManifestMessage, ...]
    warnings: tuple[str, ...]
    schema_version: int = MANIFEST_SCHEMA_VERSION
    hardware_validation_status: str = "not_performed"
    readback_required: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        ) + "\n"

    def to_markdown(self) -> str:
        lines = [
            f"# {self.package_name}",
            "",
            "## Package identity",
            "",
            f"- Manifest schema: `{self.schema_version}`",
            f"- Device ID: `{self.device_id}`",
            f"- Broadcast: `{'yes' if self.broadcast else 'no'}`",
            f"- Package bytes: `{self.package_bytes}`",
            f"- SHA-256: `{self.package_sha256}`",
            f"- Messages: `{self.message_count}`",
            f"- Self-contained User Wave set: `{'yes' if self.self_contained else 'no'}`",
            f"- Hardware validation: `{self.hardware_validation_status}`",
            f"- Read-back required: `{'yes' if self.readback_required else 'no'}`",
            "",
            "## Destinations",
            "",
            f"- User Waves: `{self.user_wave_range}` ({self.user_wave_count})",
            (
                "- User Wavetable: "
                f"display `{self.wavetable_display_number:03d}`, "
                f"internal `{self.wavetable_internal_number}`"
            ),
            f"- Sound: `{self.sound_destination}`",
            f"- Sound name: `{self.sound_name}`",
            "",
            "## Overwrite targets",
            "",
        ]
        lines.extend(f"- {label}" for label in self.overwrite_targets)
        lines.extend(["", "## User Wave mapping", "", "| Source | Destination |", "|---:|---:|"])
        lines.extend(
            f"| {item.source_number} | {item.destination_number} |"
            for item in self.wave_mapping
        )
        lines.extend(
            [
                "",
                "## Ordered messages",
                "",
                "| # | Type | Address | Destination | Bytes | Checksum |",
                "|---:|---|---:|---|---:|---:|",
            ]
        )
        lines.extend(
            (
                f"| {message.index} | {message.dump_type} | {message.address} | "
                f"{message.destination} | {message.byte_length} | "
                f"`0x{message.checksum:02X}` |"
            )
            for message in self.messages
        )
        lines.extend(["", "## Warnings", ""])
        if self.warnings:
            lines.extend(f"- {warning}" for warning in self.warnings)
        else:
            lines.append("- None")
        return "\n".join(lines) + "\n"
