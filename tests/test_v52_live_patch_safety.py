from pathlib import Path
import hashlib
import json
import pytest
import w_mwxt_wavetable_tool.validation_v52.patch_manager as pm


def h(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_bundle(tmp_path: Path, target: Path, *, tests=None) -> Path:
    bundle = tmp_path / "bundle"
    (bundle / "files").mkdir(parents=True)
    replacement = bundle / "files" / "module.py"
    replacement.write_text("new\n")
    manifest = {
        "files": [{"path": "module.py", "before_sha256": h(target), "after_sha256": h(replacement)}],
    }
    if tests is not None:
        manifest["non_regression_tests"] = tests
    (bundle / "PATCH_MANIFEST.json").write_text(json.dumps(manifest))
    return bundle


def test_v52_patch_manager_requires_confirmation_hashes_and_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("old\n")
    bundle = make_bundle(tmp_path, target)

    with pytest.raises(RuntimeError, match="confirmation"):
        pm.apply_approved_patch_bundle(repo, bundle, tmp_path / "backup", confirmed=False)
    with pytest.raises(RuntimeError, match="non_regression_tests"):
        pm.apply_approved_patch_bundle(repo, bundle, tmp_path / "backup", confirmed=True)
    assert target.read_text() == "old\n"

    manifest = json.loads((bundle / "PATCH_MANIFEST.json").read_text())
    manifest["non_regression_tests"] = ["tests/test_module.py"]
    (bundle / "PATCH_MANIFEST.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(pm, "_run_non_regression", lambda repo, targets: {"command": ["pytest"], "returncode": 0, "output": "1 passed"})
    report = pm.apply_approved_patch_bundle(repo, bundle, tmp_path / "backup", confirmed=True)
    assert target.read_text() == "new\n"
    assert Path(report["applied"][0]["backup"]).read_text() == "old\n"
    assert report["git_write_operations"] is False
    assert report["status"] == "pass"
    assert report["non_regression"]["returncode"] == 0


def test_v52_patch_manager_rolls_back_when_non_regression_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("old\n")
    bundle = make_bundle(tmp_path, target, tests=["tests/test_module.py::test_regression"])
    monkeypatch.setattr(pm, "_run_non_regression", lambda repo, targets: {"command": ["pytest"], "returncode": 1, "output": "failed"})

    with pytest.raises(RuntimeError, match="rolled back"):
        pm.apply_approved_patch_bundle(repo, bundle, tmp_path / "backup", confirmed=True)
    assert target.read_text() == "old\n"


def test_v52_patch_manager_rejects_unsafe_test_targets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("old\n")
    bundle = make_bundle(tmp_path, target, tests=["--maxfail=1"])
    with pytest.raises(RuntimeError, match="forbidden"):
        pm.apply_approved_patch_bundle(repo, bundle, tmp_path / "backup", confirmed=True)
    assert target.read_text() == "old\n"
