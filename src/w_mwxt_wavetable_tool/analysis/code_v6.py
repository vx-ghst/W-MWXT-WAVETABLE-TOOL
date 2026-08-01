from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from ..version import __version__
from .code_v5 import CodeV5Analysis, analyze_audio_source_code_v5
from .cycle_detection import CycleDiscoveryAnalysis, discover_cycles
from .cycle_selection import (
    CycleSelectionPolicy,
    SelectedCycleSet,
    select_representative_cycles,
)
from .reconstruction import (
    ReconstructionStrategy,
    ReconstructedWaveSet,
    reconstruct_selected_cycles,
)
from .repitch import WorkingPitchPlan, WorkingPitchPolicy, plan_working_pitch
from .segmentation import AttackPolicy, SegmentationAnalysis, segment_source


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _normalized_version(value: str) -> str:
    if not value or value.strip() != value:
        raise ValueError("tool_version must be a non-empty normalized string")
    return value


@dataclass(frozen=True, slots=True)
class CodeV6Analysis:
    """Immutable aggregate contract for the complete accepted CODE V6 pipeline."""

    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    code_v5_analysis: CodeV5Analysis
    working_pitch_plan: WorkingPitchPlan
    segmentation_analysis: SegmentationAnalysis
    cycle_discovery_analysis: CycleDiscoveryAnalysis
    selected_cycle_set: SelectedCycleSet
    reconstructed_wave_set: ReconstructedWaveSet

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported CODE V6 aggregate schema version")
        _normalized_version(self.tool_version)
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if not _hash_is_valid(self.sample_sha256):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")

        components = (
            self.code_v5_analysis,
            self.working_pitch_plan,
            self.segmentation_analysis,
            self.cycle_discovery_analysis,
            self.selected_cycle_set,
            self.reconstructed_wave_set,
        )
        if any(component.sample_rate != self.sample_rate for component in components):
            raise ValueError("CODE V6 components have inconsistent sample rates")
        if any(component.sample_count != self.sample_count for component in components):
            raise ValueError("CODE V6 components have inconsistent sample counts")
        if any(component.sample_sha256 != self.sample_sha256 for component in components):
            raise ValueError("CODE V6 components have inconsistent sample hashes")
        if any(component.tool_version != self.tool_version for component in components):
            raise ValueError("CODE V6 components have inconsistent tool versions")

        for name, digest in self.component_sha256.items():
            if not _hash_is_valid(digest):
                raise ValueError(f"{name} component hash must be a lowercase SHA-256 digest")

        pitch_hash = (
            self.code_v5_analysis.signal_analysis
            .pitch_periodicity_analysis.analysis_sha256
        )
        if self.working_pitch_plan.pitch_periodicity_analysis_sha256 != pitch_hash:
            raise ValueError("working-pitch plan does not link to CODE V5 pitch analysis")
        if (
            self.segmentation_analysis.signal_analysis_sha256
            != self.code_v5_analysis.signal_analysis.analysis_sha256
        ):
            raise ValueError("segmentation does not link to CODE V5 signal analysis")
        if (
            self.segmentation_analysis.working_pitch_plan_sha256
            != self.working_pitch_plan.analysis_sha256
        ):
            raise ValueError("segmentation does not link to working-pitch plan")
        if (
            self.cycle_discovery_analysis.segmentation_analysis_sha256
            != self.segmentation_analysis.analysis_sha256
        ):
            raise ValueError("cycle discovery does not link to segmentation")
        if (
            self.cycle_discovery_analysis.working_pitch_plan_sha256
            != self.working_pitch_plan.analysis_sha256
        ):
            raise ValueError("cycle discovery does not link to working-pitch plan")
        if (
            self.selected_cycle_set.cycle_discovery_analysis_sha256
            != self.cycle_discovery_analysis.analysis_sha256
        ):
            raise ValueError("cycle selection does not link to cycle discovery")
        if (
            self.reconstructed_wave_set.cycle_discovery_analysis_sha256
            != self.cycle_discovery_analysis.analysis_sha256
        ):
            raise ValueError("reconstruction does not link to cycle discovery")
        if (
            self.reconstructed_wave_set.selected_cycle_set_sha256
            != self.selected_cycle_set.analysis_sha256
        ):
            raise ValueError("reconstruction does not link to selected cycle set")

        selected_entries = tuple(
            entry for entry in self.selected_cycle_set.ranked_candidates if entry.selected
        )
        selected_indexes = tuple(entry.candidate_index for entry in selected_entries)
        selected_candidate_hashes = tuple(entry.candidate_sha256 for entry in selected_entries)
        selected_ranking_hashes = tuple(entry.ranking_sha256 for entry in selected_entries)
        if self.selected_cycle_set.selected_candidate_indices != selected_indexes:
            raise ValueError("selected candidate indexes are inconsistent")
        if self.selected_cycle_set.selected_candidate_sha256 != selected_candidate_hashes:
            raise ValueError("selected candidate hashes are inconsistent")
        if self.selected_cycle_set.selected_ranking_sha256 != selected_ranking_hashes:
            raise ValueError("selected ranking hashes are inconsistent")
        if self.reconstructed_wave_set.selected_candidate_indices != selected_indexes:
            raise ValueError("reconstructed candidate indexes do not match selection")
        if self.reconstructed_wave_set.selected_candidate_sha256 != selected_candidate_hashes:
            raise ValueError("reconstructed candidate hashes do not match selection")
        if self.reconstructed_wave_set.selected_ranking_sha256 != selected_ranking_hashes:
            raise ValueError("reconstructed ranking hashes do not match selection")

    @property
    def component_sha256(self) -> dict[str, str]:
        return {
            "code_v5_analysis": self.code_v5_analysis.analysis_sha256,
            "working_pitch_plan": self.working_pitch_plan.analysis_sha256,
            "segmentation_analysis": self.segmentation_analysis.analysis_sha256,
            "cycle_discovery_analysis": self.cycle_discovery_analysis.analysis_sha256,
            "selected_cycle_set": self.selected_cycle_set.analysis_sha256,
            "reconstructed_wave_set": self.reconstructed_wave_set.analysis_sha256,
        }

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "component_sha256": self.component_sha256,
            "code_v5_analysis": self.code_v5_analysis.to_dict(),
            "working_pitch_plan": self.working_pitch_plan.to_dict(),
            "segmentation_analysis": self.segmentation_analysis.to_dict(),
            "cycle_discovery_analysis": self.cycle_discovery_analysis.to_dict(),
            "selected_cycle_set": self.selected_cycle_set.to_dict(),
            "reconstructed_wave_set": self.reconstructed_wave_set.to_dict(),
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


def assemble_code_v6_analysis(
    code_v5_analysis: CodeV5Analysis,
    working_pitch_plan: WorkingPitchPlan,
    segmentation_analysis: SegmentationAnalysis,
    cycle_discovery_analysis: CycleDiscoveryAnalysis,
    selected_cycle_set: SelectedCycleSet,
    reconstructed_wave_set: ReconstructedWaveSet,
    *,
    tool_version: str = __version__,
) -> CodeV6Analysis:
    """Assemble and validate precomputed CODE V5 and CODE V6 components."""

    return CodeV6Analysis(
        schema_version=1,
        tool_version=tool_version,
        sample_rate=code_v5_analysis.sample_rate,
        sample_count=code_v5_analysis.sample_count,
        sample_sha256=code_v5_analysis.sample_sha256,
        code_v5_analysis=code_v5_analysis,
        working_pitch_plan=working_pitch_plan,
        segmentation_analysis=segmentation_analysis,
        cycle_discovery_analysis=cycle_discovery_analysis,
        selected_cycle_set=selected_cycle_set,
        reconstructed_wave_set=reconstructed_wave_set,
    )


def analyze_audio_source_code_v6(
    source: Any,
    *,
    working_pitch_policy: WorkingPitchPolicy | str = WorkingPitchPolicy.AUTO,
    locked_frequency_hz: float | None = None,
    attack_policy: AttackPolicy | str = AttackPolicy.AUTO,
    selection_policy: CycleSelectionPolicy | str = CycleSelectionPolicy.AUTO,
    top_n: int = 16,
    forced_candidate_index: int | None = None,
    allow_rejected_forced_candidate: bool = False,
    reconstruction_strategy: ReconstructionStrategy | str = ReconstructionStrategy.AUTO,
    working_pitch_kwargs: dict[str, float | int] | None = None,
    segmentation_kwargs: dict[str, float | int] | None = None,
    cycle_discovery_kwargs: dict[str, float | int] | None = None,
    selection_kwargs: dict[str, float] | None = None,
    reconstruction_kwargs: dict[str, float | int | bool] | None = None,
) -> CodeV6Analysis:
    """Run the canonical deterministic CODE V5 plus CODE V6 chain for one source."""

    code_v5_analysis = analyze_audio_source_code_v5(source)
    working_pitch_plan = plan_working_pitch(
        code_v5_analysis.signal_analysis.pitch_periodicity_analysis,
        policy=working_pitch_policy,
        locked_frequency_hz=locked_frequency_hz,
        tool_version=__version__,
        **dict(working_pitch_kwargs or {}),
    )
    segmentation_analysis = segment_source(
        code_v5_analysis.signal_analysis,
        working_pitch_plan,
        attack_policy=attack_policy,
        tool_version=__version__,
        **dict(segmentation_kwargs or {}),
    )
    cycle_discovery_analysis = discover_cycles(
        source.mono_samples,
        segmentation_analysis,
        working_pitch_plan,
        tool_version=__version__,
        **dict(cycle_discovery_kwargs or {}),
    )
    selected_cycle_set = select_representative_cycles(
        cycle_discovery_analysis,
        policy=selection_policy,
        top_n=top_n,
        forced_candidate_index=forced_candidate_index,
        allow_rejected_forced_candidate=allow_rejected_forced_candidate,
        tool_version=__version__,
        **dict(selection_kwargs or {}),
    )
    reconstructed_wave_set = reconstruct_selected_cycles(
        source.mono_samples,
        cycle_discovery_analysis,
        selected_cycle_set,
        strategy=reconstruction_strategy,
        tool_version=__version__,
        **dict(reconstruction_kwargs or {}),
    )
    return assemble_code_v6_analysis(
        code_v5_analysis,
        working_pitch_plan,
        segmentation_analysis,
        cycle_discovery_analysis,
        selected_cycle_set,
        reconstructed_wave_set,
        tool_version=__version__,
    )
