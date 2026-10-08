from pathlib import Path
from w_mwxt_wavetable_tool.validation_v52.clean_optimization import build_clean_optimization_inventory


def test_v52_clean_optimization_inventory_is_complete(tmp_path: Path) -> None:
    repo=Path(__file__).resolve().parents[1]
    report=build_clean_optimization_inventory(repo,tmp_path/"inventory.json")
    assert report["all_pass"] is True
    assert len(report["repair_defects"]) == 17
    assert len(report["repair_actions"]) == 17
    assert set(("AUTO","NO_REPITCH","LOCK")).issubset(report["working_pitch_policies"])
