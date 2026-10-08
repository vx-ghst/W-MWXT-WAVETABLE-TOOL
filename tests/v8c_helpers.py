from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from w_mwxt_wavetable_tool.analysis.formants import FormantAnalysis, analyze_formants
from w_mwxt_wavetable_tool.analysis.harmonic_perceptual import (
    HarmonicPerceptualAnalysis,
    analyze_harmonic_perceptual,
)
from w_mwxt_wavetable_tool.analysis.signal import (
    SignalAnalysis,
    SignalExtensionAnalysis,
    analyze_signal,
    analyze_signal_extensions,
)
from w_mwxt_wavetable_tool.analysis.spectral import SpectralAnalysis, analyze_spectral
from w_mwxt_wavetable_tool.analysis.spectral_evolution import (
    SpectralEvolutionAnalysis,
    analyze_spectral_evolution,
)
from w_mwxt_wavetable_tool.decision.behavior_classifier import classify_behavior
from w_mwxt_wavetable_tool.decision.models import (
    BehaviorClassification,
    ModeDecision,
    MusicalClassification,
)
from w_mwxt_wavetable_tool.decision.mode_selector import select_conversion_mode
from w_mwxt_wavetable_tool.decision.musical_classifier import classify_musical_source
from w_mwxt_wavetable_tool.perceptual.features import analyze_perceptual_features
from w_mwxt_wavetable_tool.perceptual.models import PerceptualFeatureVector


@dataclass(frozen=True)
class V8CBundle:
    samples: np.ndarray
    sample_rate: int
    signal: SignalAnalysis
    extension: SignalExtensionAnalysis
    spectral: SpectralAnalysis
    harmonic: HarmonicPerceptualAnalysis
    formants: FormantAnalysis
    evolution: SpectralEvolutionAnalysis
    perceptual: PerceptualFeatureVector
    behavior: BehaviorClassification
    musical: MusicalClassification
    mode: ModeDecision


def tone(
    frequencies: tuple[float, ...] = (110.0, 220.0, 330.0),
    amplitudes: tuple[float, ...] = (0.7, 0.25, 0.12),
    *,
    sample_rate: int = 16000,
    duration: float = 1.0,
) -> np.ndarray:
    time = np.arange(int(sample_rate * duration), dtype=np.float64) / sample_rate
    result = np.zeros(time.size, dtype=np.float64)
    for frequency, amplitude in zip(frequencies, amplitudes):
        result += amplitude * np.sin(2.0 * np.pi * frequency * time)
    peak = float(np.max(np.abs(result)))
    return result / max(1.0, peak / 0.9)


def evolving_tone(*, sample_rate: int = 16000, duration: float = 1.0) -> np.ndarray:
    time = np.arange(int(sample_rate * duration), dtype=np.float64) / sample_rate
    progress = np.linspace(0.0, 1.0, time.size, dtype=np.float64)
    low = np.sin(2.0 * np.pi * 110.0 * time)
    mid = np.sin(2.0 * np.pi * 440.0 * time)
    high = np.sin(2.0 * np.pi * 1760.0 * time)
    return 0.55 * low + 0.35 * progress * mid + 0.25 * progress**2 * high


def fm_tone(*, sample_rate: int = 16000, duration: float = 1.0) -> np.ndarray:
    time = np.arange(int(sample_rate * duration), dtype=np.float64) / sample_rate
    phase = 2.0 * np.pi * 220.0 * time + 3.5 * np.sin(2.0 * np.pi * 17.0 * time)
    return 0.8 * np.sin(phase)


def deterministic_noise(*, sample_rate: int = 16000, duration: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(20260803)
    return rng.normal(0.0, 0.18, int(sample_rate * duration)).astype(np.float64)


def transient_signal(*, sample_rate: int = 16000, duration: float = 1.0) -> np.ndarray:
    samples = np.zeros(int(sample_rate * duration), dtype=np.float64)
    width = int(sample_rate * 0.025)
    for center in (0.10, 0.30, 0.55, 0.80):
        start = int(center * sample_rate)
        envelope = np.exp(-np.linspace(0.0, 8.0, width, dtype=np.float64))
        carrier = np.sin(2.0 * np.pi * 600.0 * np.arange(width) / sample_rate)
        samples[start : start + width] += 0.85 * envelope * carrier
    return samples


def formant_like(*, sample_rate: int = 16000, duration: float = 1.0) -> np.ndarray:
    time = np.arange(int(sample_rate * duration), dtype=np.float64) / sample_rate
    result = np.zeros(time.size, dtype=np.float64)
    fundamental = 100.0
    centers = (500.0, 1500.0, 2500.0)
    widths = (180.0, 250.0, 300.0)
    for harmonic in range(1, 55):
        frequency = harmonic * fundamental
        if frequency >= sample_rate / 2.0:
            break
        envelope = sum(
            np.exp(-0.5 * ((frequency - center) / width) ** 2)
            for center, width in zip(centers, widths)
        )
        result += (0.12 * envelope / harmonic**0.25) * np.sin(
            2.0 * np.pi * frequency * time
        )
    peak = float(np.max(np.abs(result)))
    return result / max(1.0e-12, peak) * 0.85


def build_bundle(samples: np.ndarray, sample_rate: int = 16000) -> V8CBundle:
    data = np.ascontiguousarray(samples, dtype=np.float64)
    signal = analyze_signal(
        data,
        sample_rate,
        time_frame_size=512,
        time_hop_size=128,
        pitch_frame_size=1024,
        pitch_hop_size=256,
        minimum_frequency_hz=40.0,
        maximum_frequency_hz=3000.0,
        transient_frame_size=512,
        transient_hop_size=128,
    )
    extension = analyze_signal_extensions(
        data,
        sample_rate,
        signal_analysis=signal,
        saturation_frame_size=512,
        saturation_hop_size=128,
        beating_maximum_frequency_hz=3000.0,
    )
    spectral = analyze_spectral(
        data,
        sample_rate,
        frame_size=1024,
        hop_size=256,
        fft_size=2048,
        low_band_max_hz=250.0,
        mid_band_max_hz=4000.0,
    )
    harmonic = analyze_harmonic_perceptual(
        spectral,
        fundamental_frequency_hz=signal.pitch_periodicity_analysis.frequency_hz,
    )
    formants = analyze_formants(spectral)
    evolution = analyze_spectral_evolution(
        data,
        sample_rate,
        spectral,
        harmonic,
    )
    perceptual = analyze_perceptual_features(
        signal,
        extension,
        spectral,
        harmonic,
        evolution,
        formants,
    )
    behavior = classify_behavior(signal, extension)
    musical = classify_musical_source(behavior, perceptual, formants, extension)
    mode = select_conversion_mode(
        signal,
        extension,
        behavior,
        musical,
        perceptual,
        evolution,
    )
    return V8CBundle(
        samples=data,
        sample_rate=sample_rate,
        signal=signal,
        extension=extension,
        spectral=spectral,
        harmonic=harmonic,
        formants=formants,
        evolution=evolution,
        perceptual=perceptual,
        behavior=behavior,
        musical=musical,
        mode=mode,
    )
