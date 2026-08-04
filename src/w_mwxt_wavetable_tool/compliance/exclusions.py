from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


EXCLUSION_CONTRACT_SCHEMA_VERSION = 1


class ExclusionKind(str, Enum):
    MANUAL_TIME_SELECTION = "manual_time_selection"
    MP3_IMPORT = "mp3_import"
    POST_MONO_STEREO_ANALYSIS = "post_mono_stereo_analysis"
    OTHER_SYNTH_TARGETS = "other_synth_targets"
    GENERIC_PPG_PROFILES = "generic_ppg_profiles"
    REESE_ONLY_ARCHITECTURE = "reese_only_architecture"
    REQUIRED_WAVEEDIT_DEPENDENCY = "required_waveedit_dependency"
    OPAQUE_AI_DECISIONS = "opaque_ai_decisions"


@dataclass(frozen=True, slots=True)
class ExclusionGate:
    requirement_id: str
    kind: ExclusionKind
    assertion: str

    def __post_init__(self) -> None:
        if not self.requirement_id.startswith("CDC-"):
            raise ValueError("Exclusion requirement ID must start with CDC-")
        if not self.assertion or self.assertion.strip() != self.assertion:
            raise ValueError("Exclusion assertion must be a normalized non-empty string")


EXCLUSION_GATES: tuple[ExclusionGate, ...] = (
    ExclusionGate(
        "CDC-IMP-008",
        ExclusionKind.MANUAL_TIME_SELECTION,
        "The public prototype does not expose arbitrary manual temporal-region selection.",
    ),
    ExclusionGate(
        "CDC-IMP-010",
        ExclusionKind.MP3_IMPORT,
        "The supported import contract contains WAV, AIFF and FLAC only.",
    ),
    ExclusionGate(
        "CDC-SIG-012",
        ExclusionKind.POST_MONO_STEREO_ANALYSIS,
        "DSP contracts consume one-dimensional mono samples after import.",
    ),
    ExclusionGate(
        "CDC-MODE-010",
        ExclusionKind.MANUAL_TIME_SELECTION,
        "Conversion modes cannot force an arbitrary manual source-time range.",
    ),
    ExclusionGate(
        "CDC-EXC-001",
        ExclusionKind.OTHER_SYNTH_TARGETS,
        "The executable target remains the Waldorf Microwave XT protocol only.",
    ),
    ExclusionGate(
        "CDC-EXC-002",
        ExclusionKind.GENERIC_PPG_PROFILES,
        "No generic PPG export or profile is exposed by the prototype.",
    ),
    ExclusionGate(
        "CDC-EXC-003",
        ExclusionKind.REESE_ONLY_ARCHITECTURE,
        "Reese is not an autonomous application architecture or conversion mode.",
    ),
    ExclusionGate(
        "CDC-EXC-004",
        ExclusionKind.REQUIRED_WAVEEDIT_DEPENDENCY,
        "WaveEdit is not a required runtime or development dependency.",
    ),
    ExclusionGate(
        "CDC-EXC-005",
        ExclusionKind.OPAQUE_AI_DECISIONS,
        "Automatic decisions remain deterministic, measurable and explainable.",
    ),
)
