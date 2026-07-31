from __future__ import annotations

from pathlib import Path

from .models import AudioContainerFormat
from ..errors import UnsupportedAudioFormatError


_LIBSNDFILE_FORMATS: dict[str, AudioContainerFormat] = {
    "WAV": AudioContainerFormat.WAV,
    "WAVEX": AudioContainerFormat.WAV,
    "RF64": AudioContainerFormat.WAV,
    "AIFF": AudioContainerFormat.AIFF,
    "FLAC": AudioContainerFormat.FLAC,
}

_EXTENSION_FORMATS: dict[str, AudioContainerFormat] = {
    ".wav": AudioContainerFormat.WAV,
    ".wave": AudioContainerFormat.WAV,
    ".aif": AudioContainerFormat.AIFF,
    ".aiff": AudioContainerFormat.AIFF,
    ".aifc": AudioContainerFormat.AIFF,
    ".flac": AudioContainerFormat.FLAC,
}


def normalize_container_format(libsndfile_format: str) -> AudioContainerFormat:
    normalized = libsndfile_format.strip().upper()
    try:
        return _LIBSNDFILE_FORMATS[normalized]
    except KeyError as exc:
        raise UnsupportedAudioFormatError(
            f"Unsupported audio container reported by libsndfile: {libsndfile_format!r}; "
            "expected WAV, AIFF, or FLAC"
        ) from exc


def extension_matches(path: Path, container: AudioContainerFormat) -> bool:
    expected = _EXTENSION_FORMATS.get(path.suffix.lower())
    return expected is container


def supported_extensions() -> tuple[str, ...]:
    return tuple(sorted(_EXTENSION_FORMATS))
