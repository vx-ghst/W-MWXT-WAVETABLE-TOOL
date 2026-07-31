from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from w_mwxt_wavetable_tool.audio import (
    AudioContainerFormat,
    InvalidSamplePolicy,
    MonoStrategy,
    fingerprint_file,
    import_audio,
)
from w_mwxt_wavetable_tool.errors import (
    AudioImportError,
    InvalidAudioDataError,
    SourceChangedError,
    UnsupportedAudioFormatError,
)


def _tone(frames: int = 256, frequency: float = 5.0) -> np.ndarray:
    phase = np.arange(frames, dtype=np.float64) / frames
    return 0.75 * np.sin(2.0 * np.pi * frequency * phase)


def test_import_pcm_wav(tmp_path: Path) -> None:
    path = tmp_path / "source.wav"
    sf.write(path, _tone(), 48000, format="WAV", subtype="PCM_16")
    source = import_audio(path)
    assert source.metadata.container is AudioContainerFormat.WAV
    assert source.metadata.sample_rate == 48000
    assert source.metadata.channels == 1
    assert source.metadata.frames == 256
    assert source.mono_conversion.strategy is MonoStrategy.MONO_PASSTHROUGH
    assert source.mono_samples.dtype == np.float64
    assert not source.mono_samples.flags.writeable


def test_import_float_wav_preserves_values_outside_unit_range(tmp_path: Path) -> None:
    path = tmp_path / "wide.wav"
    samples = np.array([-1.5, -0.25, 0.25, 1.5], dtype=np.float64)
    sf.write(path, samples, 44100, format="WAV", subtype="DOUBLE")
    source = import_audio(path)
    np.testing.assert_allclose(source.mono_samples, samples, atol=0.0, rtol=0.0)


def test_import_aiff(tmp_path: Path) -> None:
    path = tmp_path / "source.aiff"
    sf.write(path, _tone(), 44100, format="AIFF", subtype="PCM_16")
    source = import_audio(path)
    assert source.metadata.container is AudioContainerFormat.AIFF
    assert source.metadata.extension_matches_container


def test_import_flac(tmp_path: Path) -> None:
    path = tmp_path / "source.flac"
    sf.write(path, _tone(), 44100, format="FLAC", subtype="PCM_16")
    source = import_audio(path)
    assert source.metadata.container is AudioContainerFormat.FLAC
    assert source.metadata.subtype == "PCM_16"


def test_actual_container_wins_over_extension(tmp_path: Path) -> None:
    path = tmp_path / "renamed.data"
    sf.write(path, _tone(), 44100, format="WAV", subtype="PCM_16")
    source = import_audio(path)
    assert source.metadata.container is AudioContainerFormat.WAV
    assert not source.metadata.extension_matches_container


def test_unsupported_decodable_container_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "source.ogg"
    try:
        sf.write(path, _tone(), 44100, format="OGG", subtype="VORBIS")
    except (RuntimeError, ValueError):
        pytest.skip("libsndfile build does not support OGG/Vorbis")
    with pytest.raises(UnsupportedAudioFormatError):
        import_audio(path)


def test_missing_source_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(AudioImportError, match="does not exist"):
        import_audio(tmp_path / "missing.wav")


def test_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(AudioImportError, match="regular file"):
        import_audio(tmp_path)


def test_unicode_and_long_path(tmp_path: Path) -> None:
    nested = tmp_path / ("échantillons_" + "x" * 80)
    nested.mkdir()
    path = nested / "chœur_à_61_positions.wav"
    sf.write(path, _tone(), 32000, format="WAV", subtype="PCM_24")
    source = import_audio(path)
    assert source.metadata.source_path == path.resolve()
    assert source.metadata.frames == 256


def test_identical_stereo_import_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    wave = _tone()
    sf.write(path, np.column_stack((wave, wave)), 48000, subtype="PCM_24")
    first = import_audio(path)
    second = import_audio(path)
    assert first.sample_sha256 == second.sample_sha256
    assert first.state_sha256 == second.state_sha256
    assert first.to_summary() == second.to_summary()
    assert first.mono_conversion.strategy is MonoStrategy.IDENTICAL_CHANNELS


def test_antiphase_import_does_not_collapse_to_silence(tmp_path: Path) -> None:
    path = tmp_path / "antiphase.wav"
    wave = _tone()
    sf.write(path, np.column_stack((wave, -wave)), 48000, subtype="FLOAT")
    source = import_audio(path)
    assert source.mono_conversion.strategy is MonoStrategy.ANTIPHASE_CHANNEL_SELECTED
    assert source.measurements.rms > 0.1


def test_silent_channel_import_selects_active_channel(tmp_path: Path) -> None:
    path = tmp_path / "silent_channel.wav"
    wave = _tone()
    sf.write(path, np.column_stack((np.zeros_like(wave), wave)), 48000, subtype="FLOAT")
    source = import_audio(path)
    assert source.mono_conversion.strategy is MonoStrategy.SILENT_CHANNEL_REMOVED
    assert source.mono_conversion.selected_channel == 1


def test_silence_and_dc_are_measured(tmp_path: Path) -> None:
    silence = tmp_path / "silence.wav"
    dc = tmp_path / "dc.wav"
    sf.write(silence, np.zeros(64), 44100, subtype="FLOAT")
    sf.write(dc, np.full(64, 0.2), 44100, subtype="FLOAT")
    assert import_audio(silence).measurements.is_silent
    assert import_audio(dc).measurements.has_dc_offset


def test_source_fingerprint_matches_file_bytes(tmp_path: Path) -> None:
    path = tmp_path / "source.wav"
    sf.write(path, _tone(), 44100, subtype="PCM_16")
    expected = sha256(path.read_bytes()).hexdigest()
    source = import_audio(path)
    assert source.metadata.source_sha256 == expected
    assert fingerprint_file(path) == expected


def test_import_does_not_modify_source_file(tmp_path: Path) -> None:
    path = tmp_path / "source.wav"
    sf.write(path, _tone(), 44100, subtype="PCM_16")
    before = path.read_bytes()
    import_audio(path)
    assert path.read_bytes() == before


def test_non_finite_float_file_is_rejected_or_zeroed(tmp_path: Path) -> None:
    path = tmp_path / "invalid.wav"
    samples = np.array([0.0, np.nan, np.inf, -np.inf], dtype=np.float64)
    sf.write(path, samples, 44100, format="WAV", subtype="DOUBLE")
    with pytest.raises(InvalidAudioDataError):
        import_audio(path)
    source = import_audio(path, invalid_sample_policy=InvalidSamplePolicy.ZERO)
    np.testing.assert_array_equal(source.mono_samples, np.zeros(4))


def test_source_change_during_import_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "source.wav"
    sf.write(path, _tone(), 44100, subtype="PCM_16")

    import w_mwxt_wavetable_tool.audio.importers as module

    original_read = module.sf.read

    def changing_read(*args: object, **kwargs: object):
        result = original_read(*args, **kwargs)
        with path.open("ab") as handle:
            handle.write(b"X")
        return result

    monkeypatch.setattr(module.sf, "read", changing_read)
    with pytest.raises(SourceChangedError):
        import_audio(path)
