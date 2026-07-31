from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any

from ..version import __version__
from .classification import SourceClassification, classify_source
from .decisions import EngineeringDecision, decide_wavetable_readiness
from .harmonic_perceptual import HarmonicPerceptualAnalysis, analyze_harmonic_perceptual
from .signal import SignalAnalysis, analyze_audio_source_signal
from .spectral import SpectralAnalysis, analyze_audio_source_spectral


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _normalized_version(value: str) -> str:
    if not value or value.strip() != value:
        raise ValueError("tool_version must be a non-empty normalized string")
    return value


def _same_optional_frequency(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-9)


@dataclass(frozen=True, slots=True)
class CodeV5Analysis:
    """Immutable aggregate contract for the complete accepted CODE V5 pipeline."""

    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    signal_analysis: SignalAnalysis
    spectral_analysis: SpectralAnalysis
    harmonic_perceptual_analysis: HarmonicPerceptualAnalysis
    source_classification: SourceClassification
    engineering_decision: EngineeringDecision

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported CODE V5 aggregate schema version")
        _normalized_version(self.tool_version)
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if not _hash_is_valid(self.sample_sha256):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")

        components = (
            self.signal_analysis,
            self.spectral_analysis,
            self.harmonic_perceptual_analysis,
            self.source_classification,
            self.engineering_decision,
        )
        if any(component.sample_rate != self.sample_rate for component in components):
            raise ValueError("CODE V5 components have inconsistent sample rates")
        if any(component.sample_count != self.sample_count for component in components):
            raise ValueError("CODE V5 components have inconsistent sample counts")
        if any(component.sample_sha256 != self.sample_sha256 for component in components):
            raise ValueError("CODE V5 components have inconsistent sample hashes")

        for name, digest in self.component_sha256.items():
            if not _hash_is_valid(digest):
                raise ValueError(f"{name} component hash must be a lowercase SHA-256 digest")

        if (
            self.harmonic_perceptual_analysis.spectral_analysis_sha256
            != self.spectral_analysis.analysis_sha256
        ):
            raise ValueError("harmonic/perceptual analysis does not link to spectral analysis")
        if self.source_classification.signal_analysis_sha256 != self.signal_analysis.analysis_sha256:
            raise ValueError("source classification does not link to signal analysis")
        if self.source_classification.spectral_analysis_sha256 != self.spectral_analysis.analysis_sha256:
            raise ValueError("source classification does not link to spectral analysis")
        if (
            self.source_classification.harmonic_perceptual_analysis_sha256
            != self.harmonic_perceptual_analysis.analysis_sha256
        ):
            raise ValueError("source classification does not link to harmonic/perceptual analysis")
        if (
            self.engineering_decision.source_classification_sha256
            != self.source_classification.analysis_sha256
        ):
            raise ValueError("engineering decision does not link to source classification")

        pitch_frequency = self.signal_analysis.pitch_periodicity_analysis.frequency_hz
        harmonic_frequency = self.harmonic_perceptual_analysis.fundamental_frequency_hz
        if not _same_optional_frequency(pitch_frequency, harmonic_frequency):
            raise ValueError("harmonic fundamental does not match signal pitch analysis")

    @property
    def component_sha256(self) -> dict[str, str]:
        return {
            "signal_analysis": self.signal_analysis.analysis_sha256,
            "spectral_analysis": self.spectral_analysis.analysis_sha256,
            "harmonic_perceptual_analysis": self.harmonic_perceptual_analysis.analysis_sha256,
            "source_classification": self.source_classification.analysis_sha256,
            "engineering_decision": self.engineering_decision.analysis_sha256,
        }

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "component_sha256": self.component_sha256,
            "signal_analysis": self.signal_analysis.to_dict(),
            "spectral_analysis": self.spectral_analysis.to_dict(),
            "harmonic_perceptual_analysis": self.harmonic_perceptual_analysis.to_dict(),
            "source_classification": self.source_classification.to_dict(),
            "engineering_decision": self.engineering_decision.to_dict(),
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


def assemble_code_v5_analysis(
    signal_analysis: SignalAnalysis,
    spectral_analysis: SpectralAnalysis,
    harmonic_perceptual_analysis: HarmonicPerceptualAnalysis,
    source_classification: SourceClassification,
    engineering_decision: EngineeringDecision,
    *,
    tool_version: str = __version__,
) -> CodeV5Analysis:
    """Assemble and validate precomputed CODE V5 components."""

    return CodeV5Analysis(
        schema_version=1,
        tool_version=tool_version,
        sample_rate=signal_analysis.sample_rate,
        sample_count=signal_analysis.sample_count,
        sample_sha256=signal_analysis.sample_sha256,
        signal_analysis=signal_analysis,
        spectral_analysis=spectral_analysis,
        harmonic_perceptual_analysis=harmonic_perceptual_analysis,
        source_classification=source_classification,
        engineering_decision=engineering_decision,
    )


def analyze_audio_source_code_v5(source: Any) -> CodeV5Analysis:
    """Run the canonical deterministic CODE V5 analysis pipeline for one audio source."""

    signal_analysis = analyze_audio_source_signal(source)
    spectral_analysis = analyze_audio_source_spectral(source)
    harmonic_perceptual_analysis = analyze_harmonic_perceptual(
        spectral_analysis,
        fundamental_frequency_hz=(
            signal_analysis.pitch_periodicity_analysis.frequency_hz
        ),
    )
    source_classification = classify_source(
        signal_analysis,
        spectral_analysis,
        harmonic_perceptual_analysis,
    )
    engineering_decision = decide_wavetable_readiness(source_classification)
    return assemble_code_v5_analysis(
        signal_analysis,
        spectral_analysis,
        harmonic_perceptual_analysis,
        source_classification,
        engineering_decision,
    )
