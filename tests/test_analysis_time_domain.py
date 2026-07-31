from __future__ import annotations

import math

import numpy as np
import pytest

from w_mwxt_wavetable_tool.analysis import analyze_audio_source, analyze_time_domain
from w_mwxt_wavetable_tool.audio.models import (
    AudioContainerFormat,
    AudioMeasurements,
    AudioMetadata,
    AudioSource,
    MonoConversionReport,
    MonoPolicy,
    MonoStrategy,
)


def _assert_json_numbers_finite(value: object) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _assert_json_numbers_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_json_numbers_finite(nested)
    elif isinstance(value, float):
        assert math.isfinite(value)


def _audio_source(samples: np.ndarray, sample_rate: int = 44100) -> AudioSource:
    samples = np.asarray(samples, dtype=np.float64)
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples))))
    metadata = AudioMetadata(
        source_path=__file__,
        container=AudioContainerFormat.WAV,
        libsndfile_format="WAV",
        subtype="FLOAT",
        endian="FILE",
        sample_rate=sample_rate,
        channels=1,
        frames=samples.size,
        duration_seconds=samples.size / sample_rate,
        source_bytes=1,
        source_mtime_ns=1,
        source_sha256="1" * 64,
        source_extension=".wav",
        extension_matches_container=True,
    )
    measurements = AudioMeasurements(
        sample_count=samples.size,
        minimum=float(np.min(samples)),
        maximum=float(np.max(samples)),
        peak_absolute=peak,
        rms=rms,
        mean=float(np.mean(samples)),
        dc_offset=float(np.mean(samples)),
        is_silent=peak == 0.0,
        has_dc_offset=False,
        all_finite=True,
    )
    conversion = MonoConversionReport(
        policy=MonoPolicy.AUTO,
        strategy=MonoStrategy.MONO_PASSTHROUGH,
        source_channels=1,
        selected_channel=0,
        channel_rms=(rms,),
        stereo_correlation=None,
        reason="test",
    )
    return AudioSource(metadata, samples, measurements, conversion)


def test_time_domain_hashes_are_stable() -> None:
    samples = np.linspace(-0.5, 0.5, 4096, dtype=np.float64)
    first = analyze_time_domain(samples, 44100, frame_size=512, hop_size=128)
    second = analyze_time_domain(samples, 44100, frame_size=512, hop_size=128)
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256
    assert len(first.analysis_sha256) == 64


def test_time_domain_hash_changes_with_samples() -> None:
    first = analyze_time_domain(np.zeros(64), 44100)
    changed = np.zeros(64)
    changed[0] = 0.001
    second = analyze_time_domain(changed, 44100)
    assert first.sample_sha256 != second.sample_sha256
    assert first.analysis_sha256 != second.analysis_sha256


def test_audio_source_analysis_reuses_canonical_sample_hash() -> None:
    source = _audio_source(np.linspace(-0.25, 0.25, 1024))
    analysis = analyze_audio_source(source, frame_size=128, hop_size=64)
    assert analysis.sample_sha256 == source.sample_sha256
    assert analysis.sample_count == source.metadata.frames
    assert analysis.sample_rate == source.metadata.sample_rate


def test_serialized_time_domain_analysis_contains_no_nan_or_infinity() -> None:
    analysis = analyze_time_domain(np.zeros(1024), 48000)
    payload = analysis.to_dict()
    _assert_json_numbers_finite(payload)
    assert payload["levels"]["peak_dbfs"] is None
    assert payload["levels"]["crest_factor"] is None


def test_analysis_input_is_not_modified() -> None:
    samples = np.linspace(-1.0, 1.0, 1000, dtype=np.float64)
    before = samples.copy()
    analyze_time_domain(samples, 48000)
    assert np.array_equal(samples, before)


def test_analysis_schema_is_explicit() -> None:
    analysis = analyze_time_domain(np.ones(32), 32000)
    assert analysis.schema_version == 1
    assert analysis.to_dict()["schema_version"] == 1
