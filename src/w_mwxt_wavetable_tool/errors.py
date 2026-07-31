from __future__ import annotations


class SysExError(ValueError):
    """Base error for malformed or unsupported SysEx data."""


class FramingError(SysExError):
    """Raised when F0/F7 framing or concatenation is malformed."""


class ProtocolError(SysExError):
    """Raised when Waldorf protocol identifiers or fields are invalid."""


class ChecksumError(SysExError):
    """Raised when the payload checksum is invalid."""


class PayloadLengthError(SysExError):
    """Raised when a known message type has the wrong payload size."""


class DestinationError(ProtocolError):
    """Raised when a user-facing hardware destination is invalid or unsafe."""


class AllocationError(ProtocolError):
    """Raised when a requested hardware-memory allocation cannot fit."""


class SafetyError(ProtocolError):
    """Raised when an overwrite plan contains unresolved collisions."""


class PackageBuildError(ProtocolError):
    """Raised when a safe deterministic package cannot be built."""
