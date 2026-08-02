from __future__ import annotations


def test_v7e_public_api() -> None:
    from w_mwxt_wavetable_tool.xt import (
        HARDWARE_PACKAGE_DEFAULT_STEM,
        HARDWARE_PACKAGE_SCHEMA_VERSION,
        XtHardwareArtifact,
        XtHardwarePackageAnalysis,
        XtHardwarePackageBuild,
        XtHardwarePackageOutputPaths,
        XtHardwarePackageStatus,
        XtHardwareTargetEvidence,
        build_xt_hardware_package_documents,
        load_and_build_xt_hardware_package,
    )

    assert HARDWARE_PACKAGE_SCHEMA_VERSION == 1
    assert HARDWARE_PACKAGE_DEFAULT_STEM.startswith("CODE_V7_E")
    assert XtHardwarePackageStatus.PASS.value == "pass"
    assert all(
        value is not None
        for value in (
            XtHardwareArtifact,
            XtHardwarePackageAnalysis,
            XtHardwarePackageBuild,
            XtHardwarePackageOutputPaths,
            XtHardwareTargetEvidence,
            build_xt_hardware_package_documents,
            load_and_build_xt_hardware_package,
        )
    )
