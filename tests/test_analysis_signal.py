from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pytest

from w_mwxt_wavetable_tool import __version__
from w_mwxt_wavetable_tool.analysis import SignalAnalysis, analyze_signal
from w_mwxt_wavetable_tool.audio.models import (
    AudioContainerFormat,
    AudioMeasurements,
    AudioMetadata,
    AudioSource,
    MonoConversionReport,
    MonoPolicy,
    MonoStrategy,
)
from w_mwxt_wavetable_tool.analysis import analyze_audio_source_signal


def _tone(frequency: float = 440.0, *, sample_rate: int = 16000, seconds: float = 0.5) -> np.ndarray:
    time = np.arange(int(sample_rate * seconds), dtype=np.float64) / sample_rate
    return 0.5 * np.sin(2.0 * np.pi * frequency * time)


def _source(samples: np.ndarray, sample_rate: int = 16000) -> AudioSource:
    samples = np.asarray(samples, dtype=np.float64)
    rms = float(np.sqrt(np.mean(np.square(samples))))
    peak = float(np.max(np.abs(samples)))
    return AudioSource(
        AudioMetadata(
            source_path=__file__, container=AudioContainerFormat.WAV,
            libsndfile_format="WAV", subtype="FLOAT", endian="FILE",
            sample_rate=sample_rate, channels=1, frames=samples.size,
            duration_seconds=samples.size / sample_rate, source_bytes=1,
            source_mtime_ns=1, source_sha256="1" * 64,
            source_extension=".wav", extension_matches_container=True,
        ),
        samples,
        AudioMeasurements(
            sample_count=samples.size, minimum=float(np.min(samples)),
            maximum=float(np.max(samples)), peak_absolute=peak, rms=rms,
            mean=float(np.mean(samples)), dc_offset=float(np.mean(samples)),
            is_silent=peak == 0.0, has_dc_offset=False, all_finite=True,
        ),
        MonoConversionReport(
            policy=MonoPolicy.AUTO, strategy=MonoStrategy.MONO_PASSTHROUGH,
            source_channels=1, selected_channel=0, channel_rms=(rms,),
            stereo_correlation=None, reason="test",
        ),
    )


def _analyze(samples: np.ndarray | None = None) -> SignalAnalysis:
    return analyze_signal(
        _tone() if samples is None else samples,
        16000,
        time_frame_size=512,
        time_hop_size=128,
        pitch_frame_size=1024,
        pitch_hop_size=256,
        maximum_frequency_hz=2000.0,
        transient_frame_size=256,
        transient_hop_size=64,
    )


def _assert_finite(value: object) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _assert_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_finite(nested)
    elif isinstance(value, float):
        assert math.isfinite(value)


def test_signal_analysis_combines_every_code_v4_component() -> None:
    analysis = _analyze()
    assert analysis.schema_version == 1
    assert analysis.tool_version == __version__
    assert analysis.time_domain_analysis.sample_count == analysis.sample_count
    assert analysis.pitch_periodicity_analysis.sample_count == analysis.sample_count
    assert analysis.phase_motion_analysis.sample_count == analysis.sample_count
    assert analysis.noise_analysis.sample_count == analysis.sample_count
    assert analysis.transient_change_analysis.sample_count == analysis.sample_count


def test_all_components_share_one_canonical_sample_identity() -> None:
    analysis = _analyze()
    hashes = {
        analysis.sample_sha256,
        analysis.time_domain_analysis.sample_sha256,
        analysis.pitch_periodicity_analysis.sample_sha256,
        analysis.phase_motion_analysis.sample_sha256,
        analysis.noise_analysis.sample_sha256,
        analysis.transient_change_analysis.sample_sha256,
    }
    assert len(hashes) == 1


def test_aggregate_and_component_hashes_are_deterministic() -> None:
    first = _analyze()
    second = _analyze()
    assert first == second
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.component_analysis_sha256 == second.component_analysis_sha256
    assert len(first.analysis_sha256) == 64
    assert all(len(value) == 64 for value in first.component_analysis_sha256.values())


def test_aggregate_hash_changes_when_samples_change() -> None:
    first_samples = _tone()
    second_samples = first_samples.copy()
    second_samples[100] += 0.01
    assert _analyze(first_samples).analysis_sha256 != _analyze(second_samples).analysis_sha256


def test_to_dict_exposes_complete_contract() -> None:
    payload = _analyze().to_dict()
    assert payload["schema_version"] == 1
    assert payload["tool_version"] == __version__
    assert set(payload["component_analysis_sha256"]) == {
        "time_domain_analysis", "pitch_periodicity_analysis",
        "phase_motion_analysis", "noise_analysis",
        "transient_change_analysis",
    }
    assert len(payload["analysis_sha256"]) == 64


def test_serialized_contract_never_contains_nan_or_infinity() -> None:
    _assert_finite(_analyze(np.zeros(4096, dtype=np.float64)).to_dict())


def test_signal_analysis_does_not_modify_input() -> None:
    samples = _tone()
    before = samples.copy()
    _analyze(samples)
    assert np.array_equal(samples, before)


def test_stable_tone_produces_voiced_aggregate() -> None:
    analysis = _analyze()
    assert analysis.pitch_periodicity_analysis.note_name == "A4"
    assert analysis.pitch_periodicity_analysis.periodicity_score > 0.9
    assert analysis.noise_analysis.snr_db is not None


def test_silence_is_supported_across_every_component() -> None:
    analysis = _analyze(np.zeros(4096, dtype=np.float64))
    assert analysis.time_domain_analysis.levels.is_silent
    assert analysis.pitch_periodicity_analysis.periodicity_class.value == "silent"
    assert analysis.noise_analysis.noise_class.value == "silent"
    assert analysis.transient_change_analysis.transient_change_class.value == "silent"


def test_custom_frame_grids_propagate_to_components() -> None:
    analysis = _analyze()
    assert analysis.time_domain_analysis.envelope.frame_size == 512
    assert analysis.pitch_periodicity_analysis.frame_size == 1024
    assert analysis.phase_motion_analysis.frame_size == 1024
    assert analysis.noise_analysis.frame_size == 1024
    assert analysis.transient_change_analysis.frame_size == 256


def test_audio_source_wrapper_preserves_imported_sample_hash() -> None:
    source = _source(_tone())
    analysis = analyze_audio_source_signal(
        source,
        time_frame_size=512, time_hop_size=128,
        pitch_frame_size=1024, pitch_hop_size=256,
        maximum_frequency_hz=2000.0,
        transient_frame_size=256, transient_hop_size=64,
    )
    assert analysis.sample_sha256 == source.sample_sha256


def test_rejects_non_positive_sample_rate() -> None:
    with pytest.raises(Exception, match="sample_rate"):
        analyze_signal(np.ones(32), 0)


def test_rejects_invalid_pitch_frequency_range() -> None:
    with pytest.raises(Exception, match="frequency"):
        analyze_signal(np.ones(256), 16000, minimum_frequency_hz=1000, maximum_frequency_hz=500)


def test_rejects_invalid_transient_frame_configuration() -> None:
    with pytest.raises(Exception, match="frame_size"):
        analyze_signal(np.ones(256), 16000, transient_frame_size=0)


def test_contract_rejects_mismatched_sample_hash() -> None:
    analysis = _analyze()
    with pytest.raises(ValueError, match="sample hash"):
        replace(analysis, sample_sha256="0" * 64)


def test_contract_rejects_mismatched_sample_rate() -> None:
    analysis = _analyze()
    with pytest.raises(ValueError, match="sample rate"):
        replace(analysis, sample_rate=analysis.sample_rate + 1)


def test_contract_rejects_mismatched_sample_count() -> None:
    analysis = _analyze()
    with pytest.raises(ValueError, match="sample count"):
        replace(analysis, sample_count=analysis.sample_count + 1)


def test_contract_rejects_invalid_schema_version() -> None:
    with pytest.raises(ValueError, match="schema"):
        replace(_analyze(), schema_version=2)


def test_contract_rejects_empty_tool_version() -> None:
    with pytest.raises(ValueError, match="tool_version"):
        replace(_analyze(), tool_version="")
