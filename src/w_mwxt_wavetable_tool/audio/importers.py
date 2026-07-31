from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import soundfile as sf

from .formats import extension_matches, normalize_container_format
from .measurements import measure_mono
from .models import (
    AudioMetadata,
    AudioSource,
    InvalidSamplePolicy,
    MonoPolicy,
)
from .mono import convert_to_mono
from .preprocessing import normalize_float_samples
from ..errors import AudioImportError, SourceChangedError


def fingerprint_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    source = Path(path)
    digest = sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def import_audio(
    path: str | Path,
    *,
    mono_policy: MonoPolicy | str = MonoPolicy.AUTO,
    invalid_sample_policy: InvalidSamplePolicy | str = InvalidSamplePolicy.REJECT,
    silence_threshold: float = 1e-12,
    dc_threshold: float = 1e-4,
) -> AudioSource:
    source = Path(path).expanduser()
    if not source.exists():
        raise AudioImportError(f"Audio source does not exist: {source}")
    if not source.is_file():
        raise AudioImportError(f"Audio source is not a regular file: {source}")

    resolved = source.resolve(strict=True)
    before = resolved.stat()
    source_sha256 = fingerprint_file(resolved)

    try:
        info = sf.info(str(resolved))
        decoded, sample_rate = sf.read(
            str(resolved),
            dtype="float64",
            always_2d=True,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        raise AudioImportError(f"Could not decode audio source {resolved}: {exc}") from exc

    after = resolved.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise SourceChangedError(
            "Audio source changed while it was being imported; retry with a stable file"
        )

    container = normalize_container_format(info.format)
    normalized = normalize_float_samples(decoded, policy=invalid_sample_policy)
    if int(sample_rate) != int(info.samplerate):
        raise AudioImportError(
            f"Decoder sample-rate mismatch: read={sample_rate}, metadata={info.samplerate}"
        )
    if normalized.shape[0] != int(info.frames):
        raise AudioImportError(
            f"Decoder frame-count mismatch: read={normalized.shape[0]}, metadata={info.frames}"
        )
    if normalized.shape[1] != int(info.channels):
        raise AudioImportError(
            "Decoder channel-count mismatch: "
            f"read={normalized.shape[1]}, metadata={info.channels}"
        )

    mono, mono_report = convert_to_mono(
        normalized,
        policy=mono_policy,
        silence_threshold=silence_threshold,
    )
    measurements = measure_mono(
        mono,
        silence_threshold=silence_threshold,
        dc_threshold=dc_threshold,
    )
    metadata = AudioMetadata(
        source_path=resolved,
        container=container,
        libsndfile_format=info.format,
        subtype=info.subtype,
        endian=info.endian,
        sample_rate=int(info.samplerate),
        channels=int(info.channels),
        frames=int(info.frames),
        duration_seconds=float(info.frames / info.samplerate),
        source_bytes=int(before.st_size),
        source_mtime_ns=int(before.st_mtime_ns),
        source_sha256=source_sha256,
        source_extension=resolved.suffix.lower(),
        extension_matches_container=extension_matches(resolved, container),
    )
    return AudioSource(
        metadata=metadata,
        mono_samples=mono,
        measurements=measurements,
        mono_conversion=mono_report,
    )
