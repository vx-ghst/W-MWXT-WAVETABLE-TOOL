from __future__ import annotations

import json

import numpy as np
import pytest

from w_mwxt_wavetable_tool.errors import AnalysisError
from w_mwxt_wavetable_tool.repair import (
    RepairContext,
    RepairDefect,
    RepairPolicy,
    RepairPolicyRule,
    RepairPolicySet,
    RepairThresholds,
    build_repair_policy_set,
    measure_repair_wave,
)

from v8e_helpers import sine_wave


def test_repair_defect_taxonomy_is_exact() -> None:
    assert len(RepairDefect) == 17
    assert tuple(item.value for item in RepairDefect) == (
        "dc_offset",
        "clipping",
        "zero_crossing",
        "loop_discontinuity",
        "derivative_discontinuity",
        "phase_inversion",
        "polarity_inversion",
        "start_end_mismatch",
        "amplitude_inconsistency",
        "cycle_length",
        "pitch_estimate",
        "parasitic_noise",
        "fundamental_loss",
        "spectral_jump",
        "inter_wave_level_mismatch",
        "redundant_wave",
        "excessive_aliasing",
    )


def test_repair_policy_taxonomy_is_exact() -> None:
    assert tuple(item.value for item in RepairPolicy) == (
        "auto",
        "compare",
        "ignore",
        "preserve",
    )


def test_thresholds_are_deterministic_and_json_safe() -> None:
    first = RepairThresholds()
    second = RepairThresholds()
    assert first.analysis_sha256 == second.analysis_sha256
    assert json.dumps(first.to_dict(), allow_nan=False)


@pytest.mark.parametrize(
    "field,value",
    [
        ("dc_ratio", -0.1),
        ("clipping_ratio", 1.1),
        ("polarity_correlation", 0.1),
        ("amplitude_delta_db", 0.0),
        ("pitch_error_cents", float("nan")),
        ("aliasing_risk", float("inf")),
    ],
)
def test_thresholds_reject_invalid_values(field: str, value: float) -> None:
    kwargs = {field: value}
    with pytest.raises(AnalysisError):
        RepairThresholds(**kwargs)


def test_context_hash_links_reference_content() -> None:
    wave = tuple(float(value) for value in sine_wave())
    first = RepairContext(reference_samples=wave)
    second = RepairContext(reference_samples=wave)
    changed = RepairContext(reference_samples=tuple(-value for value in wave))
    assert first.analysis_sha256 == second.analysis_sha256
    assert first.analysis_sha256 != changed.analysis_sha256


@pytest.mark.parametrize(
    "kwargs",
    [
        {"expected_sample_count": 1},
        {"detected_pitch_hz": 0.0},
        {"expected_pitch_hz": -1.0},
        {"target_rms": 1.1},
        {"aliasing_risk": -0.1},
        {"safe_harmonic_limit": 0},
        {"source_label": " bad"},
    ],
)
def test_context_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(AnalysisError):
        RepairContext(**kwargs)


def test_context_rejects_reference_length_mismatch() -> None:
    with pytest.raises(AnalysisError):
        RepairContext(reference_samples=tuple(0.0 for _ in range(64)))


def test_policy_set_uses_default_for_every_defect() -> None:
    policy = build_repair_policy_set(default_policy=RepairPolicy.COMPARE)
    assert set(policy.policy_map.values()) == {"compare"}
    assert all(policy.policy_for(defect) is RepairPolicy.COMPARE for defect in RepairDefect)


def test_policy_set_canonicalizes_mapping_overrides() -> None:
    policy = build_repair_policy_set(
        overrides={
            RepairDefect.EXCESSIVE_ALIASING: RepairPolicy.PRESERVE,
            RepairDefect.DC_OFFSET: RepairPolicy.IGNORE,
        }
    )
    assert tuple(rule.defect for rule in policy.overrides) == (
        RepairDefect.DC_OFFSET,
        RepairDefect.EXCESSIVE_ALIASING,
    )


def test_policy_set_rejects_duplicate_rules() -> None:
    with pytest.raises(AnalysisError):
        RepairPolicySet(
            overrides=(
                RepairPolicyRule(RepairDefect.DC_OFFSET, RepairPolicy.AUTO),
                RepairPolicyRule(RepairDefect.DC_OFFSET, RepairPolicy.IGNORE),
            )
        )


def test_policy_set_rejects_noncanonical_rule_order() -> None:
    with pytest.raises(AnalysisError):
        RepairPolicySet(
            overrides=(
                RepairPolicyRule(RepairDefect.CLIPPING, RepairPolicy.AUTO),
                RepairPolicyRule(RepairDefect.DC_OFFSET, RepairPolicy.IGNORE),
            )
        )


def test_wave_metrics_are_deterministic() -> None:
    wave = sine_wave(amplitude=0.75)
    first = measure_repair_wave(wave)
    second = measure_repair_wave(wave.copy())
    assert first == second
    assert first.sample_count == 128
    assert first.rms > 0.0
    assert first.fundamental_ratio > 0.99


@pytest.mark.parametrize(
    "samples",
    [
        [0.0],
        [0.0, float("nan")],
        [0.0, float("inf")],
        [0.0, 1.1],
    ],
)
def test_wave_metrics_reject_invalid_samples(samples: list[float]) -> None:
    with pytest.raises(AnalysisError):
        measure_repair_wave(samples)


def test_policy_json_contains_all_defects() -> None:
    policy = build_repair_policy_set()
    payload = policy.to_dict()
    assert tuple(payload["policy_map"]) == tuple(item.value for item in RepairDefect)
    assert len(payload["analysis_sha256"]) == 64
