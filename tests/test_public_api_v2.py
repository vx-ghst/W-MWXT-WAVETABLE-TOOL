from __future__ import annotations

import w_mwxt_wavetable_tool as tool


def test_code_v2_public_api_exports_package_types() -> None:
    assert tool.PackageRequest is not None
    assert tool.PackagePlan is not None
    assert tool.PackageBuildResult is not None
    assert tool.PackageManifest is not None
    assert callable(tool.plan_package)
    assert callable(tool.build_package)
