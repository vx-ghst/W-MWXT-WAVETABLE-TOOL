from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Iterator, Self

from .constants import SYSEX_END, SYSEX_START, DumpType
from .errors import FramingError
from .message import SysExMessage


@dataclass(frozen=True, slots=True)
class DumpFile:
    messages: tuple[SysExMessage, ...]

    @classmethod
    def from_bytes(
        cls,
        data: bytes | bytearray | memoryview,
        *,
        validate_checksum: bool = True,
        strict_length: bool = True,
    ) -> Self:
        raw = bytes(data)
        frames = tuple(split_sysex_stream(raw))
        messages = tuple(
            SysExMessage.from_bytes(
                frame,
                validate_checksum=validate_checksum,
                strict_length=strict_length,
            )
            for frame in frames
        )
        return cls(messages)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        validate_checksum: bool = True,
        strict_length: bool = True,
    ) -> Self:
        return cls.from_bytes(
            Path(path).read_bytes(),
            validate_checksum=validate_checksum,
            strict_length=strict_length,
        )

    def to_bytes(self, *, recompute_checksum: bool = True) -> bytes:
        return b"".join(
            message.to_bytes(recompute_checksum=recompute_checksum)
            for message in self.messages
        )

    def write(self, path: str | Path, *, recompute_checksum: bool = True) -> Path:
        destination = Path(path)
        destination.write_bytes(self.to_bytes(recompute_checksum=recompute_checksum))
        return destination

    def validate(self, *, strict_length: bool = True) -> tuple[str, ...]:
        issues: list[str] = []
        for index, message in enumerate(self.messages):
            for issue in message.validate(strict_length=strict_length):
                issues.append(f"message {index}: {issue}")
        return tuple(issues)

    @property
    def type_counts(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for message in self.messages:
            try:
                label = DumpType(int(message.dump_type)).name
            except ValueError:
                label = f"UNKNOWN_{int(message.dump_type):02X}"
            counts[label] += 1
        return dict(sorted(counts.items()))

    @property
    def device_ids(self) -> tuple[int, ...]:
        return tuple(sorted({message.device_id for message in self.messages}))

    @property
    def address_ranges(self) -> dict[str, tuple[int, int]]:
        grouped: dict[str, list[int]] = defaultdict(list)
        for message in self.messages:
            try:
                label = DumpType(int(message.dump_type)).name
            except ValueError:
                label = f"UNKNOWN_{int(message.dump_type):02X}"
            grouped[label].append(message.address)
        return {label: (min(values), max(values)) for label, values in sorted(grouped.items())}

    def summary(self, *, source_bytes: bytes | None = None) -> dict[str, object]:
        serialized = self.to_bytes()
        original = serialized if source_bytes is None else source_bytes
        return {
            "bytes": len(original),
            "sha256": sha256(original).hexdigest(),
            "message_count": len(self.messages),
            "device_ids": list(self.device_ids),
            "type_counts": self.type_counts,
            "address_ranges": {
                key: [value[0], value[1]] for key, value in self.address_ranges.items()
            },
            "roundtrip_identical": serialized == original,
            "validation_issues": list(self.validate()),
        }

    def __iter__(self) -> Iterator[SysExMessage]:
        return iter(self.messages)

    def __len__(self) -> int:
        return len(self.messages)


def split_sysex_stream(data: bytes | bytearray | memoryview) -> Iterable[bytes]:
    """Split a strictly concatenated binary SysEx stream.

    V1 intentionally rejects bytes outside F0..F7 frames. This prevents silent
    corruption and guarantees deterministic round trips for archival dumps.
    """
    raw = bytes(data)
    cursor = 0
    while cursor < len(raw):
        if raw[cursor] != SYSEX_START:
            raise FramingError(
                f"Unexpected byte outside SysEx frame at offset {cursor}: {raw[cursor]:#04x}"
            )
        try:
            end = raw.index(SYSEX_END, cursor + 1)
        except ValueError as exc:
            raise FramingError(f"Unterminated SysEx frame starting at offset {cursor}") from exc
        frame = raw[cursor : end + 1]
        if SYSEX_START in frame[1:-1]:
            raise FramingError(f"Nested F0 byte in frame starting at offset {cursor}")
        yield frame
        cursor = end + 1
