from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.analysis import code_v6
from w_mwxt_wavetable_tool.analysis.code_v6 import (
    CodeV6Analysis,
    analyze_audio_source_code_v6,
    assemble_code_v6_analysis,
)

VERSION = "0.7.0"
SAMPLE = "a" * 64


def digest(character: str) -> str:
    return character * 64


class Component:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.analysis_sha256 = value
        self.sample_rate = 48000
        self.sample_count = 96000
        self.sample_sha256 = SAMPLE
        self.tool_version = VERSION

    def to_dict(self):
        return {
            "name": self.name,
            "analysis_sha256": self.analysis_sha256,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "tool_version": self.tool_version,
        }


def chain():
    code5 = Component("code5", digest("1"))
    pitch = SimpleNamespace(analysis_sha256=digest("0"))
    signal = SimpleNamespace(analysis_sha256=digest("9"), pitch_periodicity_analysis=pitch)
    code5.signal_analysis = signal

    plan = Component("plan", digest("2"))
    plan.pitch_periodicity_analysis_sha256 = pitch.analysis_sha256

    segmentation = Component("segmentation", digest("3"))
    segmentation.signal_analysis_sha256 = signal.analysis_sha256
    segmentation.working_pitch_plan_sha256 = plan.analysis_sha256

    cycles = Component("cycles", digest("4"))
    cycles.segmentation_analysis_sha256 = segmentation.analysis_sha256
    cycles.working_pitch_plan_sha256 = plan.analysis_sha256

    entry = SimpleNamespace(
        selected=True,
        candidate_index=7,
        candidate_sha256=digest("7"),
        ranking_sha256=digest("8"),
    )
    selected = Component("selected", digest("5"))
    selected.cycle_discovery_analysis_sha256 = cycles.analysis_sha256
    selected.ranked_candidates = (entry,)
    selected.selected_candidate_indices = (7,)
    selected.selected_candidate_sha256 = (digest("7"),)
    selected.selected_ranking_sha256 = (digest("8"),)

    reconstructed = Component("reconstructed", digest("6"))
    reconstructed.cycle_discovery_analysis_sha256 = cycles.analysis_sha256
    reconstructed.selected_cycle_set_sha256 = selected.analysis_sha256
    reconstructed.selected_candidate_indices = (7,)
    reconstructed.selected_candidate_sha256 = (digest("7"),)
    reconstructed.selected_ranking_sha256 = (digest("8"),)

    return code5, plan, segmentation, cycles, selected, reconstructed


def make_analysis() -> CodeV6Analysis:
    return assemble_code_v6_analysis(*chain())


def test_identity():
    result = make_analysis()
    assert result.schema_version == 1
    assert result.tool_version == VERSION
    assert result.sample_rate == 48000
    assert result.sample_count == 96000
    assert result.sample_sha256 == SAMPLE


def test_component_hash_map():
    assert make_analysis().component_sha256 == {
        "code_v5_analysis": digest("1"),
        "working_pitch_plan": digest("2"),
        "segmentation_analysis": digest("3"),
        "cycle_discovery_analysis": digest("4"),
        "selected_cycle_set": digest("5"),
        "reconstructed_wave_set": digest("6"),
    }


def test_to_dict_contains_complete_chain():
    payload = make_analysis().to_dict()
    assert set(payload) == {
        "schema_version", "tool_version", "sample_rate", "sample_count",
        "sample_sha256", "component_sha256", "code_v5_analysis",
        "working_pitch_plan", "segmentation_analysis", "cycle_discovery_analysis",
        "selected_cycle_set", "reconstructed_wave_set", "analysis_sha256",
    }


def test_hash_is_deterministic():
    assert make_analysis().analysis_sha256 == make_analysis().analysis_sha256


def test_aggregate_is_frozen():
    result = make_analysis()
    with pytest.raises(FrozenInstanceError):
        result.sample_rate = 44100


def test_rejects_schema():
    with pytest.raises(ValueError, match="schema"):
        replace(make_analysis(), schema_version=2)


def test_rejects_non_normalized_version():
    with pytest.raises(ValueError, match="tool_version"):
        replace(make_analysis(), tool_version=" 0.7.0")


@pytest.mark.parametrize("field", ["sample_rate", "sample_count", "sample_sha256"])
def test_rejects_component_identity_mismatch(field):
    components = list(chain())
    setattr(components[3], field, 1 if field != "sample_sha256" else digest("f"))
    with pytest.raises(ValueError, match="inconsistent"):
        assemble_code_v6_analysis(*components)


@pytest.mark.parametrize("index", range(6))
def test_rejects_component_version_mismatch(index):
    components = list(chain())
    components[index].tool_version = "9.9.9"
    with pytest.raises(ValueError, match="versions"):
        assemble_code_v6_analysis(*components)


@pytest.mark.parametrize(
    "case",
    ["pitch", "signal", "segment-plan", "cycle-segment", "cycle-plan", "selection-cycle", "reconstruction-cycle", "reconstruction-selection"],
)
def test_rejects_broken_hash_links(case):
    components = list(chain())
    code5, plan, segmentation, cycles, selected, reconstructed = components
    wrong = digest("f")
    if case == "pitch":
        plan.pitch_periodicity_analysis_sha256 = wrong
    elif case == "signal":
        segmentation.signal_analysis_sha256 = wrong
    elif case == "segment-plan":
        segmentation.working_pitch_plan_sha256 = wrong
    elif case == "cycle-segment":
        cycles.segmentation_analysis_sha256 = wrong
    elif case == "cycle-plan":
        cycles.working_pitch_plan_sha256 = wrong
    elif case == "selection-cycle":
        selected.cycle_discovery_analysis_sha256 = wrong
    elif case == "reconstruction-cycle":
        reconstructed.cycle_discovery_analysis_sha256 = wrong
    else:
        reconstructed.selected_cycle_set_sha256 = wrong
    with pytest.raises(ValueError, match="link"):
        assemble_code_v6_analysis(*components)


def test_rejects_selection_array_mismatch():
    components = list(chain())
    components[5].selected_candidate_indices = (99,)
    with pytest.raises(ValueError, match="candidate indexes"):
        assemble_code_v6_analysis(*components)


def test_empty_selection_and_reconstruction_are_valid():
    components = list(chain())
    selected, reconstructed = components[4], components[5]
    selected.ranked_candidates = ()
    selected.selected_candidate_indices = ()
    selected.selected_candidate_sha256 = ()
    selected.selected_ranking_sha256 = ()
    reconstructed.selected_candidate_indices = ()
    reconstructed.selected_candidate_sha256 = ()
    reconstructed.selected_ranking_sha256 = ()
    assert assemble_code_v6_analysis(*components).reconstructed_wave_set is reconstructed


def test_assembler_uses_code_v5_identity():
    components = chain()
    result = assemble_code_v6_analysis(*components)
    assert result.code_v5_analysis is components[0]


def test_analyzer_orchestrates_complete_chain(monkeypatch):
    components = chain()
    code5, plan, segmentation, cycles, selected, reconstructed = components
    source = SimpleNamespace(mono_samples=object())
    calls = []
    monkeypatch.setattr(code_v6, "analyze_audio_source_code_v5", lambda value: calls.append("v5") or code5)
    monkeypatch.setattr(code_v6, "plan_working_pitch", lambda *a, **k: calls.append("plan") or plan)
    monkeypatch.setattr(code_v6, "segment_source", lambda *a, **k: calls.append("segment") or segmentation)
    monkeypatch.setattr(code_v6, "discover_cycles", lambda *a, **k: calls.append("cycles") or cycles)
    monkeypatch.setattr(code_v6, "select_representative_cycles", lambda *a, **k: calls.append("select") or selected)
    monkeypatch.setattr(code_v6, "reconstruct_selected_cycles", lambda *a, **k: calls.append("reconstruct") or reconstructed)
    result = analyze_audio_source_code_v6(source)
    assert calls == ["v5", "plan", "segment", "cycles", "select", "reconstruct"]
    assert result.analysis_sha256


def test_analyzer_forwards_authoritative_policies(monkeypatch):
    components = chain()
    code5, plan, segmentation, cycles, selected, reconstructed = components
    source = SimpleNamespace(mono_samples=object())
    captured = {}

    def capture(name, result):
        def wrapped(*args, **kwargs):
            captured[name] = kwargs
            return result
        return wrapped

    monkeypatch.setattr(code_v6, "analyze_audio_source_code_v5", lambda value: code5)
    monkeypatch.setattr(code_v6, "plan_working_pitch", capture("plan", plan))
    monkeypatch.setattr(code_v6, "segment_source", capture("segment", segmentation))
    monkeypatch.setattr(code_v6, "discover_cycles", capture("cycles", cycles))
    monkeypatch.setattr(code_v6, "select_representative_cycles", capture("select", selected))
    monkeypatch.setattr(code_v6, "reconstruct_selected_cycles", capture("reconstruct", reconstructed))
    analyze_audio_source_code_v6(
        source,
        working_pitch_policy="lock",
        locked_frequency_hz=330.0,
        attack_policy="keep",
        selection_policy="force",
        top_n=8,
        forced_candidate_index=7,
        reconstruction_strategy="hybrid",
    )
    assert captured["plan"]["policy"] == "lock"
    assert captured["plan"]["locked_frequency_hz"] == 330.0
    assert captured["segment"]["attack_policy"] == "keep"
    assert captured["select"]["policy"] == "force"
    assert captured["select"]["top_n"] == 8
    assert captured["reconstruct"]["strategy"] == "hybrid"
