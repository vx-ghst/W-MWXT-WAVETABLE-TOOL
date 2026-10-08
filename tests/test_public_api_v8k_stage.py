from __future__ import annotations

import w_mwxt_wavetable_tool as public


def test_v8k_public_api_is_exported() -> None:
    required = {
        "WctdMode",
        "MaterializedWctd",
        "WctdMaterialization",
        "materialize_v8k_wctd",
        "WavetablePackage",
        "CompletePackageContract",
        "build_wavetable_package",
        "V8KHardwareGatePlan",
        "V8KHardwareGateReport",
        "load_v8k_hardware_campaign",
        "CodeV8KAnalysis",
        "build_code_v8k",
    }
    assert required <= set(public.__all__)
    for name in required:
        assert hasattr(public, name)
