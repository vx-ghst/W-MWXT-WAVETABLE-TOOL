from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from w_mwxt_wavetable_tool.analysis import code_v5
from w_mwxt_wavetable_tool.analysis.code_v5 import (
    CodeV5Analysis,
    analyze_audio_source_code_v5,
    assemble_code_v5_analysis,
)


SAMPLE_HASH = "a" * 64
SIGNAL_HASH = "1" * 64
SPECTRAL_HASH = "2" * 64
HARMONIC_HASH = "3" * 64
CLASSIFICATION_HASH = "4" * 64
DECISION_HASH = "5" * 64


class FakeComponent:
    def __init__(
        self,
        name: str,
        digest: str,
        *,
        sample_rate: int = 48000,
        sample_count: int = 96000,
        sample_sha256: str = SAMPLE_HASH,
    ) -> None:
        self.name = name
        self.analysis_sha256 = digest
        self.sample_rate = sample_rate
        self.sample_count = sample_count
        self.sample_sha256 = sample_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "analysis_sha256": self.analysis_sha256,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
        }


def make_components() -> tuple[object, object, object, object, object]:
    signal = FakeComponent("signal", SIGNAL_HASH)
    signal.pitch_periodicity_analysis = SimpleNamespace(frequency_hz=440.0)
    spectral = FakeComponent("spectral", SPECTRAL_HASH)
    harmonic = FakeComponent("harmonic", HARMONIC_HASH)
    harmonic.spectral_analysis_sha256 = SPECTRAL_HASH
    harmonic.fundamental_frequency_hz = 440.0
    classification = FakeComponent("classification", CLASSIFICATION_HASH)
    classification.signal_analysis_sha256 = SIGNAL_HASH
    classification.spectral_analysis_sha256 = SPECTRAL_HASH
    classification.harmonic_perceptual_analysis_sha256 = HARMONIC_HASH
    decision = FakeComponent("decision", DECISION_HASH)
    decision.source_classification_sha256 = CLASSIFICATION_HASH
    return signal, spectral, harmonic, classification, decision


def make_analysis() -> CodeV5Analysis:
    signal, spectral, harmonic, classification, decision = make_components()
    return assemble_code_v5_analysis(
        signal, spectral, harmonic, classification, decision
    )


def test_valid_aggregate_identity() -> None:
    analysis = make_analysis()
    assert analysis.schema_version == 1
    assert analysis.tool_version == "0.5.0"
    assert analysis.sample_rate == 48000
    assert analysis.sample_count == 96000
    assert analysis.sample_sha256 == SAMPLE_HASH


def test_component_hash_map_is_canonical() -> None:
    assert make_analysis().component_sha256 == {
        "signal_analysis": SIGNAL_HASH,
        "spectral_analysis": SPECTRAL_HASH,
        "harmonic_perceptual_analysis": HARMONIC_HASH,
        "source_classification": CLASSIFICATION_HASH,
        "engineering_decision": DECISION_HASH,
    }


def test_to_dict_contains_every_component() -> None:
    report = make_analysis().to_dict()
    assert set(report) == {
        "schema_version",
        "tool_version",
        "sample_rate",
        "sample_count",
        "sample_sha256",
        "component_sha256",
        "signal_analysis",
        "spectral_analysis",
        "harmonic_perceptual_analysis",
        "source_classification",
        "engineering_decision",
        "analysis_sha256",
    }


def test_analysis_hash_is_lowercase_sha256() -> None:
    digest = make_analysis().analysis_sha256
    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)


def test_analysis_hash_is_deterministic() -> None:
    assert make_analysis().analysis_sha256 == make_analysis().analysis_sha256


def test_analysis_hash_changes_when_component_content_changes() -> None:
    first = make_analysis()
    second = make_analysis()
    second.engineering_decision.name = "changed"
    assert first.analysis_sha256 != second.analysis_sha256


def test_aggregate_is_frozen() -> None:
    analysis = make_analysis()
    with pytest.raises(FrozenInstanceError):
        analysis.sample_rate = 44100


def test_rejects_invalid_schema_version() -> None:
    analysis = make_analysis()
    with pytest.raises(ValueError, match="schema version"):
        CodeV5Analysis(
            schema_version=2,
            tool_version=analysis.tool_version,
            sample_rate=analysis.sample_rate,
            sample_count=analysis.sample_count,
            sample_sha256=analysis.sample_sha256,
            signal_analysis=analysis.signal_analysis,
            spectral_analysis=analysis.spectral_analysis,
            harmonic_perceptual_analysis=analysis.harmonic_perceptual_analysis,
            source_classification=analysis.source_classification,
            engineering_decision=analysis.engineering_decision,
        )


@pytest.mark.parametrize("tool_version", ["", " 0.5.0", "0.5.0 "])
def test_rejects_non_normalized_tool_version(tool_version: str) -> None:
    signal, spectral, harmonic, classification, decision = make_components()
    with pytest.raises(ValueError, match="tool_version"):
        assemble_code_v5_analysis(
            signal,
            spectral,
            harmonic,
            classification,
            decision,
            tool_version=tool_version,
        )


@pytest.mark.parametrize("field,value", [("sample_rate", 0), ("sample_count", 0)])
def test_rejects_non_positive_identity(field: str, value: int) -> None:
    signal, spectral, harmonic, classification, decision = make_components()
    setattr(signal, field, value)
    with pytest.raises(ValueError):
        assemble_code_v5_analysis(signal, spectral, harmonic, classification, decision)


@pytest.mark.parametrize("sample_hash", ["a" * 63, "A" * 64, "z" * 64])
def test_rejects_invalid_sample_hash(sample_hash: str) -> None:
    signal, spectral, harmonic, classification, decision = make_components()
    signal.sample_sha256 = sample_hash
    with pytest.raises(ValueError, match="sample_sha256"):
        assemble_code_v5_analysis(signal, spectral, harmonic, classification, decision)


@pytest.mark.parametrize("component_index", range(5))
def test_rejects_component_sample_rate_mismatch(component_index: int) -> None:
    components = list(make_components())
    components[component_index].sample_rate = 44100
    if component_index == 0:
        components[1].sample_rate = 48000
    with pytest.raises(ValueError, match="sample rates"):
        assemble_code_v5_analysis(*components)


@pytest.mark.parametrize("component_index", range(1, 5))
def test_rejects_component_sample_count_mismatch(component_index: int) -> None:
    components = list(make_components())
    components[component_index].sample_count += 1
    with pytest.raises(ValueError, match="sample counts"):
        assemble_code_v5_analysis(*components)


@pytest.mark.parametrize("component_index", range(1, 5))
def test_rejects_component_sample_hash_mismatch(component_index: int) -> None:
    components = list(make_components())
    components[component_index].sample_sha256 = "b" * 64
    with pytest.raises(ValueError, match="sample hashes"):
        assemble_code_v5_analysis(*components)


def test_rejects_harmonic_spectral_link_mismatch() -> None:
    components = list(make_components())
    components[2].spectral_analysis_sha256 = "9" * 64
    with pytest.raises(ValueError, match="harmonic/perceptual"):
        assemble_code_v5_analysis(*components)


def test_rejects_classification_signal_link_mismatch() -> None:
    components = list(make_components())
    components[3].signal_analysis_sha256 = "9" * 64
    with pytest.raises(ValueError, match="signal analysis"):
        assemble_code_v5_analysis(*components)


def test_rejects_classification_spectral_link_mismatch() -> None:
    components = list(make_components())
    components[3].spectral_analysis_sha256 = "9" * 64
    with pytest.raises(ValueError, match="spectral analysis"):
        assemble_code_v5_analysis(*components)


def test_rejects_classification_harmonic_link_mismatch() -> None:
    components = list(make_components())
    components[3].harmonic_perceptual_analysis_sha256 = "9" * 64
    with pytest.raises(ValueError, match="harmonic/perceptual"):
        assemble_code_v5_analysis(*components)


def test_rejects_decision_classification_link_mismatch() -> None:
    components = list(make_components())
    components[4].source_classification_sha256 = "9" * 64
    with pytest.raises(ValueError, match="engineering decision"):
        assemble_code_v5_analysis(*components)


def test_rejects_fundamental_availability_mismatch() -> None:
    components = list(make_components())
    components[2].fundamental_frequency_hz = None
    with pytest.raises(ValueError, match="fundamental"):
        assemble_code_v5_analysis(*components)


def test_rejects_fundamental_value_mismatch() -> None:
    components = list(make_components())
    components[2].fundamental_frequency_hz = 441.0
    with pytest.raises(ValueError, match="fundamental"):
        assemble_code_v5_analysis(*components)


def test_accepts_two_missing_fundamentals() -> None:
    components = list(make_components())
    components[0].pitch_periodicity_analysis.frequency_hz = None
    components[2].fundamental_frequency_hz = None
    assert assemble_code_v5_analysis(*components).sample_sha256 == SAMPLE_HASH


def test_assemble_accepts_explicit_tool_version() -> None:
    components = make_components()
    assert assemble_code_v5_analysis(*components, tool_version="test-build").tool_version == "test-build"


def test_analyze_audio_source_runs_components_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    signal, spectral, harmonic, classification, decision = make_components()
    calls: list[object] = []
    source = object()

    def signal_fn(value: object) -> object:
        calls.append(("signal", value))
        return signal

    def spectral_fn(value: object) -> object:
        calls.append(("spectral", value))
        return spectral

    def harmonic_fn(value: object, *, fundamental_frequency_hz: float | None) -> object:
        calls.append(("harmonic", value, fundamental_frequency_hz))
        return harmonic

    def classify_fn(*values: object) -> object:
        calls.append(("classification", values))
        return classification

    def decision_fn(value: object) -> object:
        calls.append(("decision", value))
        return decision

    monkeypatch.setattr(code_v5, "analyze_audio_source_signal", signal_fn)
    monkeypatch.setattr(code_v5, "analyze_audio_source_spectral", spectral_fn)
    monkeypatch.setattr(code_v5, "analyze_harmonic_perceptual", harmonic_fn)
    monkeypatch.setattr(code_v5, "classify_source", classify_fn)
    monkeypatch.setattr(code_v5, "decide_wavetable_readiness", decision_fn)

    result = analyze_audio_source_code_v5(source)
    assert result.engineering_decision is decision
    assert calls[0] == ("signal", source)
    assert calls[1] == ("spectral", source)
    assert calls[2] == ("harmonic", spectral, 440.0)
    assert calls[3] == ("classification", (signal, spectral, harmonic))
    assert calls[4] == ("decision", classification)
