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


class HardwareValidationError(ProtocolError):
    """Raised when a hardware preflight or read-back comparison is unsafe or invalid."""


class AudioImportError(ValueError):
    """Base error for unsupported, unreadable, or inconsistent audio sources."""


class UnsupportedAudioFormatError(AudioImportError):
    """Raised when a decoded source is not WAV, AIFF, or FLAC."""


class InvalidAudioDataError(AudioImportError):
    """Raised when decoded audio has an invalid shape or sample value."""


class SourceChangedError(AudioImportError):
    """Raised when a source file changes during deterministic import."""


class ProjectError(ValueError):
    """Base error for minimal project schema and persistence failures."""


class ProjectFormatError(ProjectError):
    """Raised when a project container or manifest has an invalid structure."""


class ProjectIntegrityError(ProjectError):
    """Raised when project content does not match its recorded hashes or lengths."""


class ProjectSourceError(ProjectError):
    """Raised when strict source validation finds a missing or changed source."""


class ProjectExistsError(ProjectError):
    """Raised when a project save would overwrite an existing file without opt-in."""


class AnalysisError(ValueError):
    """Raised when deterministic DSP analysis cannot be completed safely."""
