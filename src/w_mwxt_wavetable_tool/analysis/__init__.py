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
from .signal import SignalAnalysis, analyze_audio_source_signal, analyze_signal
from .classification import (
    ClassificationFeature,
    SourceClass,
    SourceClassScore,
    SourceClassification,
    classify_source,
)
from .decisions import (
    DecisionStatus,
    EngineeringDecision,
    EngineeringRecommendation,
    RecommendationCode,
    RecommendationPriority,
    decide_wavetable_readiness,
)
from .harmonic_perceptual import (
    HarmonicPeak,
    HarmonicPerceptualAnalysis,
    analyze_audio_source_harmonic_perceptual,
    analyze_harmonic_perceptual,
)
from .spectral import (
    SpectralAnalysis,
    SpectralFrameAnalysis,
    analyze_audio_source_spectral,
    analyze_spectral,
)
from .time_domain import analyze_audio_source, analyze_time_domain
from .transients import analyze_audio_source_transients, analyze_transients

__all__ = [
    "ChangePointEvent",
    "ClassificationFeature",
    "DecisionStatus",
    "EngineeringDecision",
    "EngineeringRecommendation",
    "EnvelopeAnalysis",
    "HarmonicPeak",
    "HarmonicPerceptualAnalysis",
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
    "SignalAnalysis",
    "SourceClass",
    "SourceClassScore",
    "SourceClassification",
    "RecommendationCode",
    "RecommendationPriority",
    "SpectralAnalysis",
    "SpectralFrameAnalysis",
    "TimeDomainAnalysis",
    "TransientChangeAnalysis",
    "TransientChangeClass",
    "TransientEvent",
    "TransientFrameAnalysis",
    "analyze_audio_source",
    "analyze_audio_source_harmonic_perceptual",
    "analyze_audio_source_signal",
    "analyze_audio_source_noise",
    "analyze_audio_source_phase_motion",
    "analyze_audio_source_pitch_periodicity",
    "analyze_audio_source_transients",
    "analyze_envelope",
    "analyze_levels",
    "analyze_noise",
    "analyze_phase_motion",
    "analyze_pitch_periodicity",
    "analyze_signal",
    "classify_source",
    "decide_wavetable_readiness",
    "analyze_harmonic_perceptual",
    "analyze_spectral",
    "analyze_audio_source_spectral",
    "analyze_time_domain",
    "analyze_transients",
    "describe_frequency",
    "frequency_to_midi",
    "midi_note_name",
    "midi_to_frequency",
    "nearest_midi_note",
]
