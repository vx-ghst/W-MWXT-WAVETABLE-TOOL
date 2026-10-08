from __future__ import annotations

import w_mwxt_wavetable_tool as package
from w_mwxt_wavetable_tool import wavetable


def test_v8i_public_api_is_exported_from_package_and_wavetable_namespace() -> None:
    names = {
        "WAVETABLE_CONSOLIDATION_SCHEMA_VERSION",
        "ConsolidationPolicy",
        "DEFAULT_CONSOLIDATION_POLICY",
        "LogicalWavetable61",
        "PhysicalWave",
        "PhysicalWaveSet",
        "LogicalToPhysicalMapping",
        "FinalUsefulnessAnalysis",
        "WavetableConsolidationAnalysis",
        "consolidate_wavetable_build",
        "CODE_V8I_SCHEMA_VERSION",
        "CodeV8IStatus",
        "CodeV8IVariant",
        "CodeV8IAnalysis",
        "build_code_v8i",
    }
    for name in names:
        assert hasattr(package, name), name
        assert hasattr(wavetable, name), name
        assert name in package.__all__
        assert name in wavetable.__all__
