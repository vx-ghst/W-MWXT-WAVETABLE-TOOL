from __future__ import annotations

import w_mwxt_wavetable_tool as tool


def test_v2c_public_api_exports() -> None:
    assert tool.ComparisonStatus.EXACT.value == "exact"
    assert tool.HardwareValidationStatus.PASS_EXACT.value == "pass_exact"
    assert callable(tool.inspect_hardware_package)
    assert callable(tool.prepare_hardware_validation)
    assert callable(tool.compare_hardware_readback)
    assert callable(tool.build_hardware_test_from_backup)
