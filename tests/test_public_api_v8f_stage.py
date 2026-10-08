from __future__ import annotations

import inspect

import w_mwxt_wavetable_tool as root
from w_mwxt_wavetable_tool import wavetable


EXPECTED = (
    "DEFAULT_FACTORY_STYLE_POLICY",
    "FACTORY_STYLE_SCHEMA_VERSION",
    "HARDWARE_GATE_SCHEMA_VERSION",
    "WCTD_MODEL_SCHEMA_VERSION",
    "CodeV8FAnalysis",
    "CodeV8FStatus",
    "FactoryStyleAction",
    "FactoryStyleAnalysis",
    "FactoryStylePolicy",
    "FactoryStyleSlotDecision",
    "FactoryStyleStatus",
    "FactoryStyleVariant",
    "HardwareGateEvidence",
    "HardwareGateKind",
    "HardwareGatePlan",
    "HardwareGatePlanStatus",
    "HardwareGateRequirement",
    "HardwareGateResult",
    "HardwareGateResultStatus",
    "WctdMaterializationSet",
    "WctdMaterializationStatus",
    "WctdReference",
    "WctdReferenceKind",
    "WctdReferenceModel",
    "apply_factory_style",
    "build_code_v8f",
    "default_hardware_gate_requirements",
    "evaluate_hardware_gates",
    "materialize_wctd_models",
    "materialize_wctd_reference_model",
)


def test_v8f_stage_symbols_are_exported_from_wavetable_package() -> None:
    for name in EXPECTED:
        assert hasattr(wavetable, name), name
        assert name in wavetable.__all__


def test_v8f_stage_symbols_are_exported_from_package_root() -> None:
    for name in EXPECTED:
        assert hasattr(root, name), name
        assert name in root.__all__


def test_v8f_function_signatures_are_explicit() -> None:
    assert tuple(inspect.signature(wavetable.apply_factory_style).parameters) == (
        "request",
        "v8e_analysis",
        "policy",
    )
    assert tuple(inspect.signature(wavetable.materialize_wctd_reference_model).parameters) == (
        "build",
        "user_references",
    )
    assert tuple(inspect.signature(wavetable.evaluate_hardware_gates).parameters) == (
        "model",
        "evidence",
    )


def test_build_code_v8f_signature_is_explicit() -> None:
    assert tuple(inspect.signature(wavetable.build_code_v8f).parameters) == (
        "request",
        "v8e_analysis",
        "factory_policy",
        "allocations",
        "hardware_evidence",
    )


def test_v8f_schema_versions_are_one() -> None:
    assert wavetable.FACTORY_STYLE_SCHEMA_VERSION == 1
    assert wavetable.WCTD_MODEL_SCHEMA_VERSION == 1
    assert wavetable.HARDWARE_GATE_SCHEMA_VERSION == 1


def test_v8f_api_does_not_expose_midi_or_sysex_execution_names() -> None:
    lowered = {name.lower() for name in EXPECTED}
    assert not any("send" in name or "transmit" in name or "open_midi" in name for name in lowered)
