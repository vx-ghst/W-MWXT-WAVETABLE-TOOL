from __future__ import annotations

from dataclasses import replace

from v8d_placement_helpers import variants_context
from v8e_transition_helpers import smooth_candidates

from w_mwxt_wavetable_tool.analysis.regions import (
    InterestRegion,
    RegionInterestAnalysis,
    RegionKind,
)
from w_mwxt_wavetable_tool.wavetable import CodeV8DStatus


def _region(
    index: int,
    kind: RegionKind,
    *,
    start: int,
    end: int,
    useful: bool,
    useful_score: float,
    redundancy: float,
    interest: float,
    complexity: float,
    saturation: float,
    allocation_weight: float,
) -> InterestRegion:
    return InterestRegion(
        index=index,
        source_segment_index=index,
        start_sample=start,
        end_sample=end,
        sample_rate=48000,
        kind=kind,
        mean_rms=0.25,
        voiced_frame_ratio=0.8,
        mean_spectral_flux=0.2,
        saturation_score=saturation,
        complexity_score=complexity,
        useful_change_score=useful_score,
        redundancy_score=redundancy,
        interest_score=interest,
        allocation_weight=allocation_weight,
        useful_change=useful,
        reason="Synthetic V8-G region.",
    )


def region_analysis(*, evolving_index: int = 1) -> RegionInterestAnalysis:
    kinds = [
        RegionKind.SUSTAIN,
        RegionKind.EVOLUTION,
        RegionKind.REDUNDANCY,
        RegionKind.SATURATION,
    ]
    if evolving_index == 3:
        kinds[1], kinds[3] = kinds[3], kinds[1]
    weights = (0.15, 0.45, 0.10, 0.30)
    regions = []
    for index, kind in enumerate(kinds):
        useful = kind in {RegionKind.EVOLUTION, RegionKind.SATURATION}
        regions.append(
            _region(
                index,
                kind,
                start=index * 24000,
                end=(index + 1) * 24000,
                useful=useful,
                useful_score=0.9 if useful else 0.05,
                redundancy=0.95 if kind is RegionKind.REDUNDANCY else 0.05,
                interest=0.9 if useful else 0.2,
                complexity=0.85 if useful else 0.1,
                saturation=0.85 if kind is RegionKind.SATURATION else 0.0,
                allocation_weight=weights[index],
            )
        )
    return RegionInterestAnalysis(
        schema_version=1,
        sample_rate=48000,
        sample_count=96000,
        sample_sha256="d" * 64,
        signal_analysis_sha256="1" * 64,
        signal_extension_analysis_sha256="2" * 64,
        segmentation_analysis_sha256="3" * 64,
        redundancy_minimum_duration_ms=100.0,
        redundancy_flux_threshold=0.2,
        useful_change_threshold=0.5,
        regions=tuple(regions),
        useful_region_indices=tuple(item.index for item in regions if item.useful_change),
        redundant_region_indices=tuple(
            item.index for item in regions if item.kind is RegionKind.REDUNDANCY
        ),
        reason="Synthetic V8-G region analysis.",
    )


def v8g_context(count: int = 3):
    items = smooth_candidates(count)
    request, v8b, v8c, v8d = variants_context(
        count,
        candidates=items,
        requested_variants=1,
    )
    return request, v8b, v8c, v8d, region_analysis()


def rejected_v8d(v8d):
    return replace(
        v8d,
        status=CodeV8DStatus.REJECTED,
        variants=(),
        primary_variant_id=None,
        blockers=("synthetic V8-D rejection",),
        reason="Synthetic rejected V8-D for V8-G tests.",
    )
