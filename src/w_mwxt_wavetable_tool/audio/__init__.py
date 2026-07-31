"""Deterministic audio import and mono normalization for CODE V3-A."""

from .formats import supported_extensions
from .importers import fingerprint_file, import_audio
from .measurements import channel_rms, measure_mono, stereo_correlation
from .models import (
    AudioContainerFormat,
    AudioMeasurements,
    AudioMetadata,
    AudioSource,
    InvalidSamplePolicy,
    MonoConversionReport,
    MonoPolicy,
    MonoStrategy,
)
from .mono import convert_to_mono
from .preprocessing import normalize_float_samples

__all__ = [
    "AudioContainerFormat",
    "AudioMeasurements",
    "AudioMetadata",
    "AudioSource",
    "InvalidSamplePolicy",
    "MonoConversionReport",
    "MonoPolicy",
    "MonoStrategy",
    "channel_rms",
    "convert_to_mono",
    "fingerprint_file",
    "import_audio",
    "measure_mono",
    "normalize_float_samples",
    "stereo_correlation",
    "supported_extensions",
]
