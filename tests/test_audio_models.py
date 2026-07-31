from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from w_mwxt_wavetable_tool.audio.models import (
    AudioContainerFormat,
    AudioMeasurements,
    AudioMetadata,
    AudioSource,
    MonoConversionReport,
    MonoPolicy,
    MonoStrategy,
)


def _source(samples: np.ndarray) -> AudioSource:
    metadata = AudioMetadata(
        source_path=Path("source.wav"),
        container=AudioContainerFormat.WAV,
        libsndfile_format="WAV",
        subtype="FLOAT",
        endian="FILE",
        sample_rate=48000,
        channels=1,
        frames=samples.size,
        duration_seconds=samples.size / 48000,
        source_bytes=100,
        source_mtime_ns=123,
        source_sha256="a" * 64,
        source_extension=".wav",
        extension_matches_container=True,
    )
    measurements = AudioMeasurements(
        sample_count=samples.size,
        minimum=float(np.min(samples)),
        maximum=float(np.max(samples)),
        peak_absolute=float(np.max(np.abs(samples))),
        rms=float(np.sqrt(np.mean(np.square(samples)))),
        mean=float(np.mean(samples)),
        dc_offset=float(np.mean(samples)),
        is_silent=False,
        has_dc_offset=False,
        all_finite=True,
    )
    report = MonoConversionReport(
        policy=MonoPolicy.AUTO,
        strategy=MonoStrategy.MONO_PASSTHROUGH,
        source_channels=1,
        selected_channel=0,
        channel_rms=(measurements.rms,),
        stereo_correlation=None,
        reason="mono",
    )
    return AudioSource(metadata, samples, measurements, report)


def test_audio_source_copies_and_freezes_sample_array() -> None:
    original = np.array([0.0, 0.5, -0.5])
    source = _source(original)
    original[0] = 1.0
    assert source.mono_samples[0] == 0.0
    assert not source.mono_samples.flags.writeable
    with pytest.raises(ValueError):
        source.mono_samples[0] = 2.0


def test_audio_source_hashes_are_stable() -> None:
    first = _source(np.array([0.0, 0.5, -0.5]))
    second = _source(np.array([0.0, 0.5, -0.5]))
    assert first.sample_sha256 == second.sample_sha256
    assert first.state_sha256 == second.state_sha256


def test_audio_source_hash_changes_with_samples() -> None:
    first = _source(np.array([0.0, 0.5, -0.5]))
    second = _source(np.array([0.0, 0.5, -0.4]))
    assert first.sample_sha256 != second.sample_sha256
    assert first.state_sha256 != second.state_sha256


def test_audio_source_rejects_frame_count_mismatch() -> None:
    source = _source(np.array([0.0, 0.5]))
    metadata = source.metadata
    bad_metadata = AudioMetadata(
        source_path=metadata.source_path,
        container=metadata.container,
        libsndfile_format=metadata.libsndfile_format,
        subtype=metadata.subtype,
        endian=metadata.endian,
        sample_rate=metadata.sample_rate,
        channels=metadata.channels,
        frames=3,
        duration_seconds=metadata.duration_seconds,
        source_bytes=metadata.source_bytes,
        source_mtime_ns=metadata.source_mtime_ns,
        source_sha256=metadata.source_sha256,
        source_extension=metadata.source_extension,
        extension_matches_container=metadata.extension_matches_container,
    )
    with pytest.raises(ValueError, match="sample count"):
        AudioSource(bad_metadata, source.mono_samples, source.measurements, source.mono_conversion)
