from __future__ import annotations

from pathlib import Path
import tomllib

import numpy as np
import pytest

import w_mwxt_wavetable_tool as tool
from w_mwxt_wavetable_tool.analysis import analyze_time_domain
from w_mwxt_wavetable_tool.audio import supported_extensions
from w_mwxt_wavetable_tool.compliance import EXCLUSION_GATES, load_compliance_registry
from w_mwxt_wavetable_tool.constants import (
    MICROWAVE_II_XT_EQUIPMENT_ID,
    WALDORF_MANUFACTURER_ID,
)
from w_mwxt_wavetable_tool.errors import AnalysisError


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_EXCLUDED_IDS = {
    "CDC-IMP-008",
    "CDC-IMP-010",
    "CDC-SIG-012",
    "CDC-MODE-010",
    "CDC-EXC-001",
    "CDC-EXC-002",
    "CDC-EXC-003",
    "CDC-EXC-004",
    "CDC-EXC-005",
}


def test_all_nine_exclusions_have_executable_gates() -> None:
    registry_ids = {item.id for item in load_compliance_registry().excluded_requirements}
    gate_ids = {gate.requirement_id for gate in EXCLUSION_GATES}
    assert registry_ids == gate_ids == EXPECTED_EXCLUDED_IDS
    assert len(EXCLUSION_GATES) == 9


def test_mp3_is_not_in_the_supported_import_contract() -> None:
    extensions = supported_extensions()
    assert ".mp3" not in extensions
    assert set(extensions) == {".aif", ".aifc", ".aiff", ".flac", ".wav", ".wave"}


def test_dsp_rejects_stereo_arrays_after_the_mono_boundary() -> None:
    with pytest.raises(AnalysisError, match="one-dimensional mono"):
        analyze_time_domain(np.zeros((128, 2), dtype=np.float64), 44100)


def test_public_api_does_not_expose_manual_time_range_or_reese_mode() -> None:
    normalized = {name.casefold() for name in tool.__all__}
    forbidden = {
        "manual_time_range",
        "manual_region_selection",
        "select_time_range",
        "reese_mode",
        "reese_converter",
    }
    assert normalized.isdisjoint(forbidden)


def test_protocol_target_remains_microwave_xt_only() -> None:
    assert WALDORF_MANUFACTURER_ID == 0x3E
    assert MICROWAVE_II_XT_EQUIPMENT_ID == 0x0E
    source_root = ROOT / "src" / "w_mwxt_wavetable_tool"
    texts: list[str] = []
    for path in source_root.rglob("*.py"):
        if "compliance" in path.parts:
            continue
        texts.append(path.read_text(encoding="utf-8").casefold())
    executable_text = "\n".join(texts)
    for forbidden in ("blofeld", "generic ppg", "waveedit", "reese_mode"):
        assert forbidden not in executable_text


def test_dependencies_do_not_require_waveedit_or_opaque_ai_frameworks() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = [
        item.casefold() for item in pyproject["project"].get("dependencies", [])
    ]
    optional = [
        item.casefold()
        for values in pyproject["project"].get("optional-dependencies", {}).values()
        for item in values
    ]
    declared = "\n".join(dependencies + optional)
    for forbidden in (
        "waveedit",
        "openai",
        "tensorflow",
        "torch",
        "keras",
        "anthropic",
    ):
        assert forbidden not in declared
