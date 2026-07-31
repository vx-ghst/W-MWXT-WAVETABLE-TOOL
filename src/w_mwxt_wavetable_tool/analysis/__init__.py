"""Deterministic DSP analysis for CODE V4."""

from .envelope import analyze_envelope
from .levels import analyze_levels
from .models import (
    ChangePointEvent,
    EnvelopeAnalysis,
    LevelAnalysis,
    NoiseAnalysis,
    NoiseClass,
    NoiseFrameAnalysis,
    PeriodicityClass,
    PhaseContinuityClass,
    PhaseFrameAnalysis,
    PhaseMotionAnalysis,
    PhaseTransitionAnalysis,
    PitchMotionClass,
    PitchFrameAnalysis,
    PitchPeriodicityAnalysis,
    TimeDomainAnalysis,
    TransientChangeAnalysis,
    TransientChangeClass,
    TransientEvent,
    TransientFrameAnalysis,
)
from .noise import analyze_audio_source_noise, analyze_noise
from .periodicity import analyze_audio_source_pitch_periodicity, analyze_pitch_periodicity
from .phase_motion import analyze_audio_source_phase_motion, analyze_phase_motion
from .pitch import (
    describe_frequency,
    frequency_to_midi,
    midi_note_name,
    midi_to_frequency,
    nearest_midi_note,
)
from .time_domain import analyze_audio_source, analyze_time_domain
from .transients import analyze_audio_source_transients, analyze_transients

__all__ = [
    "ChangePointEvent",
    "EnvelopeAnalysis",
    "LevelAnalysis",
    "NoiseAnalysis",
    "NoiseClass",
    "NoiseFrameAnalysis",
    "PeriodicityClass",
    "PhaseContinuityClass",
    "PhaseFrameAnalysis",
    "PhaseMotionAnalysis",
    "PhaseTransitionAnalysis",
    "PitchMotionClass",
    "PitchFrameAnalysis",
    "PitchPeriodicityAnalysis",
    "TimeDomainAnalysis",
    "TransientChangeAnalysis",
    "TransientChangeClass",
    "TransientEvent",
    "TransientFrameAnalysis",
    "analyze_audio_source",
    "analyze_audio_source_noise",
    "analyze_audio_source_phase_motion",
    "analyze_audio_source_pitch_periodicity",
    "analyze_audio_source_transients",
    "analyze_envelope",
    "analyze_levels",
    "analyze_noise",
    "analyze_phase_motion",
    "analyze_pitch_periodicity",
    "analyze_time_domain",
    "analyze_transients",
    "describe_frequency",
    "frequency_to_midi",
    "midi_note_name",
    "midi_to_frequency",
    "nearest_midi_note",
]
