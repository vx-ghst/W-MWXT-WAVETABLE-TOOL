from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

import numpy as np
import numpy.typing as npt

from ..audio import AudioSource
from ..version import __version__
from .models import (
    NoiseAnalysis,
    PhaseMotionAnalysis,
    PitchPeriodicityAnalysis,
    TimeDomainAnalysis,
    TransientChangeAnalysis,
)
from .noise import analyze_noise
from .periodicity import analyze_pitch_periodicity
from .phase_motion import analyze_phase_motion
from .time_domain import analyze_time_domain
from .transients import analyze_transients
from .beating import BeatingAnalysis, analyze_beating
from .complexity import ComplexityAnalysis, analyze_complexity
from .frequency_modulation import (
    FrequencyModulationAnalysis,
    analyze_frequency_modulation,
)
from .saturation import SaturationAnalysis, analyze_saturation


@dataclass(frozen=True, slots=True)
class SignalAnalysis:
    """Complete deterministic CODE V4 signal-analysis contract."""

    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    time_domain_analysis: TimeDomainAnalysis
    pitch_periodicity_analysis: PitchPeriodicityAnalysis
    phase_motion_analysis: PhaseMotionAnalysis
    noise_analysis: NoiseAnalysis
    transient_change_analysis: TransientChangeAnalysis

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported signal-analysis schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise ValueError("tool_version must be a non-empty normalized string")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if len(self.sample_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sample_sha256
        ):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")

        components = (
            self.time_domain_analysis,
            self.pitch_periodicity_analysis,
            self.phase_motion_analysis,
            self.noise_analysis,
            self.transient_change_analysis,
        )
        for component in components:
            if component.sample_rate != self.sample_rate:
                raise ValueError("component sample rate is inconsistent")
            if component.sample_count != self.sample_count:
                raise ValueError("component sample count is inconsistent")
            if component.sample_sha256 != self.sample_sha256:
                raise ValueError("component sample hash is inconsistent")

        pitch = self.pitch_periodicity_analysis
        phase = self.phase_motion_analysis
        noise = self.noise_analysis
        if (phase.frame_size, phase.hop_size) != (pitch.frame_size, pitch.hop_size):
            raise ValueError("phase analysis must reuse the pitch frame grid")
        if (noise.frame_size, noise.hop_size) != (pitch.frame_size, pitch.hop_size):
            raise ValueError("noise analysis must reuse the pitch frame grid")

    @property
    def component_analysis_sha256(self) -> dict[str, str]:
        return {
            "time_domain_analysis": self.time_domain_analysis.analysis_sha256,
            "pitch_periodicity_analysis": self.pitch_periodicity_analysis.analysis_sha256,
            "phase_motion_analysis": self.phase_motion_analysis.analysis_sha256,
            "noise_analysis": self.noise_analysis.analysis_sha256,
            "transient_change_analysis": self.transient_change_analysis.analysis_sha256,
        }

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "component_analysis_sha256": self.component_analysis_sha256,
            "time_domain_analysis": self.time_domain_analysis.to_dict(),
            "pitch_periodicity_analysis": self.pitch_periodicity_analysis.to_dict(),
            "phase_motion_analysis": self.phase_motion_analysis.to_dict(),
            "noise_analysis": self.noise_analysis.to_dict(),
            "transient_change_analysis": self.transient_change_analysis.to_dict(),
        }

    @property
    def analysis_sha256(self) -> str:
        rendered = json.dumps(
            self._content_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(rendered).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def analyze_signal(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    time_frame_size: int = 2048,
    time_hop_size: int = 512,
    clipping_threshold: float = 1.0,
    near_clip_threshold: float = 0.98,
    silence_threshold: float = 1e-12,
    dc_threshold: float = 1e-4,
    active_threshold: float = 1e-8,
    pitch_frame_size: int = 4096,
    pitch_hop_size: int = 1024,
    minimum_frequency_hz: float = 40.0,
    maximum_frequency_hz: float = 2000.0,
    pitch_active_rms_threshold: float = 1e-6,
    confidence_threshold: float = 0.60,
    reference_a4_hz: float = 440.0,
    phase_discontinuity_threshold_degrees: float = 60.0,
    stable_pitch_threshold_cents: float = 15.0,
    glide_slope_threshold_cents_per_second: float = 25.0,
    stepped_pitch_threshold_cents: float = 100.0,
    noise_lower_quantile: float = 0.20,
    minimum_noise_rms: float = 1e-15,
    transient_frame_size: int = 1024,
    transient_hop_size: int = 256,
    transient_sensitivity: float = 6.0,
    minimum_onset_strength: float = 1.0,
    change_energy_threshold_db: float = 6.0,
    change_spectral_flux_threshold: float = 0.35,
    minimum_event_separation_ms: float = 20.0,
) -> SignalAnalysis:
    """Run every accepted CODE V4 analysis using one canonical signal identity."""

    time_domain = analyze_time_domain(
        samples,
        sample_rate,
        frame_size=time_frame_size,
        hop_size=time_hop_size,
        clipping_threshold=clipping_threshold,
        near_clip_threshold=near_clip_threshold,
        silence_threshold=silence_threshold,
        dc_threshold=dc_threshold,
        active_threshold=active_threshold,
    )
    pitch_periodicity = analyze_pitch_periodicity(
        samples,
        sample_rate,
        frame_size=pitch_frame_size,
        hop_size=pitch_hop_size,
        minimum_frequency_hz=minimum_frequency_hz,
        maximum_frequency_hz=maximum_frequency_hz,
        active_rms_threshold=pitch_active_rms_threshold,
        confidence_threshold=confidence_threshold,
        reference_a4_hz=reference_a4_hz,
    )
    phase_motion = analyze_phase_motion(
        samples,
        sample_rate,
        pitch_periodicity=pitch_periodicity,
        phase_discontinuity_threshold_degrees=(
            phase_discontinuity_threshold_degrees
        ),
        stable_pitch_threshold_cents=stable_pitch_threshold_cents,
        glide_slope_threshold_cents_per_second=(
            glide_slope_threshold_cents_per_second
        ),
        stepped_pitch_threshold_cents=stepped_pitch_threshold_cents,
    )
    noise = analyze_noise(
        samples,
        sample_rate,
        pitch_periodicity=pitch_periodicity,
        lower_quantile=noise_lower_quantile,
        silence_threshold=silence_threshold,
        minimum_noise_rms=minimum_noise_rms,
    )
    transient_change = analyze_transients(
        samples,
        sample_rate,
        frame_size=transient_frame_size,
        hop_size=transient_hop_size,
        sensitivity=transient_sensitivity,
        minimum_onset_strength=minimum_onset_strength,
        change_energy_threshold_db=change_energy_threshold_db,
        change_spectral_flux_threshold=change_spectral_flux_threshold,
        minimum_event_separation_ms=minimum_event_separation_ms,
        silence_threshold=silence_threshold,
    )

    return SignalAnalysis(
        schema_version=1,
        tool_version=__version__,
        sample_rate=time_domain.sample_rate,
        sample_count=time_domain.sample_count,
        sample_sha256=time_domain.sample_sha256,
        time_domain_analysis=time_domain,
        pitch_periodicity_analysis=pitch_periodicity,
        phase_motion_analysis=phase_motion,
        noise_analysis=noise,
        transient_change_analysis=transient_change,
    )


def analyze_audio_source_signal(
    source: AudioSource,
    **kwargs: float | int,
) -> SignalAnalysis:
    analysis = analyze_signal(
        source.mono_samples,
        source.metadata.sample_rate,
        **kwargs,
    )
    if analysis.sample_sha256 != source.sample_sha256:
        raise ValueError("signal analysis did not preserve the AudioSource sample hash")
    return analysis


@dataclass(frozen=True, slots=True)
class SignalExtensionAnalysis:
    """V8-0B signal metrics linked to the immutable CODE V4 aggregate."""

    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    signal_analysis_sha256: str
    pitch_periodicity_analysis_sha256: str
    frequency_modulation_analysis: FrequencyModulationAnalysis
    saturation_analysis: SaturationAnalysis
    complexity_analysis: ComplexityAnalysis
    beating_analysis: BeatingAnalysis

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported signal-extension schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise ValueError("tool_version must be a non-empty normalized string")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        for name in (
            "sample_sha256",
            "signal_analysis_sha256",
            "pitch_periodicity_analysis_sha256",
        ):
            value = getattr(self, name)
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if (
            self.frequency_modulation_analysis.pitch_periodicity_analysis_sha256
            != self.pitch_periodicity_analysis_sha256
        ):
            raise ValueError(
                "frequency-modulation analysis does not link to the pitch analysis"
            )
        components = (
            self.frequency_modulation_analysis,
            self.saturation_analysis,
            self.complexity_analysis,
            self.beating_analysis,
        )
        for component in components:
            if component.sample_rate != self.sample_rate:
                raise ValueError("extension component sample rate is inconsistent")
            if component.sample_count != self.sample_count:
                raise ValueError("extension component sample count is inconsistent")
            if component.sample_sha256 != self.sample_sha256:
                raise ValueError("extension component sample hash is inconsistent")

    @property
    def component_analysis_sha256(self) -> dict[str, str]:
        return {
            "frequency_modulation_analysis": (
                self.frequency_modulation_analysis.analysis_sha256
            ),
            "saturation_analysis": self.saturation_analysis.analysis_sha256,
            "complexity_analysis": self.complexity_analysis.analysis_sha256,
            "beating_analysis": self.beating_analysis.analysis_sha256,
        }

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "signal_analysis_sha256": self.signal_analysis_sha256,
            "pitch_periodicity_analysis_sha256": (
                self.pitch_periodicity_analysis_sha256
            ),
            "component_analysis_sha256": self.component_analysis_sha256,
            "frequency_modulation_analysis": (
                self.frequency_modulation_analysis.to_dict()
            ),
            "saturation_analysis": self.saturation_analysis.to_dict(),
            "complexity_analysis": self.complexity_analysis.to_dict(),
            "beating_analysis": self.beating_analysis.to_dict(),
        }

    @property
    def analysis_sha256(self) -> str:
        rendered = json.dumps(
            self._content_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(rendered).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def analyze_signal_extensions(
    samples: npt.ArrayLike,
    sample_rate: int,
    *,
    signal_analysis: SignalAnalysis | None = None,
    saturation_frame_size: int = 2048,
    saturation_hop_size: int = 512,
    complexity_active_threshold: float = 1e-6,
    beating_minimum_frequency_hz: float = 35.0,
    beating_maximum_frequency_hz: float = 2000.0,
) -> SignalExtensionAnalysis:
    base = signal_analysis or analyze_signal(samples, sample_rate)
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 1 or data.size == 0:
        raise ValueError("signal extension analysis expects non-empty mono samples")
    if not bool(np.all(np.isfinite(data))):
        raise ValueError("signal extension analysis requires finite samples")
    canonical_hash = sha256(
        np.ascontiguousarray(data, dtype=np.float64)
        .astype("<f8", copy=False)
        .tobytes(order="C")
    ).hexdigest()
    if int(sample_rate) != base.sample_rate:
        raise ValueError("signal extension sample rate does not match base analysis")
    if int(data.size) != base.sample_count:
        raise ValueError("signal extension sample count does not match base analysis")
    if canonical_hash != base.sample_sha256:
        raise ValueError("signal extension sample hash does not match base analysis")

    frequency_modulation = analyze_frequency_modulation(
        base.pitch_periodicity_analysis
    )
    saturation = analyze_saturation(
        data,
        sample_rate,
        frame_size=saturation_frame_size,
        hop_size=saturation_hop_size,
    )
    complexity = analyze_complexity(
        data,
        sample_rate,
        active_threshold=complexity_active_threshold,
    )
    beating = analyze_beating(
        data,
        sample_rate,
        minimum_frequency_hz=beating_minimum_frequency_hz,
        maximum_frequency_hz=beating_maximum_frequency_hz,
    )

    return SignalExtensionAnalysis(
        schema_version=1,
        tool_version=__version__,
        sample_rate=base.sample_rate,
        sample_count=base.sample_count,
        sample_sha256=base.sample_sha256,
        signal_analysis_sha256=base.analysis_sha256,
        pitch_periodicity_analysis_sha256=(
            base.pitch_periodicity_analysis.analysis_sha256
        ),
        frequency_modulation_analysis=frequency_modulation,
        saturation_analysis=saturation,
        complexity_analysis=complexity,
        beating_analysis=beating,
    )


def analyze_audio_source_signal_extensions(
    source: AudioSource,
    **kwargs: float | int | SignalAnalysis,
) -> SignalExtensionAnalysis:
    base = kwargs.pop("signal_analysis", None)
    if base is not None and not isinstance(base, SignalAnalysis):
        raise TypeError("signal_analysis must be a SignalAnalysis when provided")
    return analyze_signal_extensions(
        source.mono_samples,
        source.metadata.sample_rate,
        signal_analysis=base,
        **kwargs,
    )
