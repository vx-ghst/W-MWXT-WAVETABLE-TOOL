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
