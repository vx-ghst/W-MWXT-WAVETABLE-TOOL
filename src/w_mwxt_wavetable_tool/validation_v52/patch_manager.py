from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Sequence


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_test_targets(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("Patch manifest requires a non-empty non_regression_tests list")
    targets: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError("Invalid non-regression test target")
        target = item.strip()
        if target.startswith("-"):
            raise RuntimeError(f"Pytest options are forbidden in patch manifests: {target}")
        path_part = target.split("::", 1)[0].replace("\\", "/")
        relative = Path(path_part)
        if relative.is_absolute() or ".." in relative.parts or not path_part.startswith("tests/"):
            raise RuntimeError(f"Unsafe non-regression test target: {target}")
        targets.append(target)
    return tuple(targets)


def _run_non_regression(repo: Path, targets: Sequence[str]) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
    command = [sys.executable, "-m", "pytest", "-q", *targets]
    result = subprocess.run(
        command,
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "output": result.stdout,
    }


def _restore_applied(applied: list[dict[str, Any]]) -> None:
    for item in reversed(applied):
        current = Path(item["current"])
        backup = Path(item["backup"])
        expected_after = item["after"]
        expected_before = item["before"]
        if not current.is_file() or _hash(current) != expected_after:
            raise RuntimeError(f"Cannot rollback safely; patched file changed after application: {current}")
        if not backup.is_file() or _hash(backup) != expected_before:
            raise RuntimeError(f"Cannot rollback safely; backup hash mismatch: {backup}")
        temporary = current.with_suffix(current.suffix + ".v52rollbacktmp")
        shutil.copy2(backup, temporary)
        temporary.replace(current)
        if _hash(current) != expected_before:
            raise RuntimeError(f"Rollback hash verification failed: {current}")


def apply_approved_patch_bundle(repo: Path, bundle: Path, backup_root: Path, *, confirmed: bool = False) -> dict[str, Any]:
    """Apply a hash-locked file bundle, run required regression tests, and rollback on failure.

    Bundle layout: PATCH_MANIFEST.json plus files/RELATIVE_PATH. PATCH_MANIFEST.json
    must contain ``files`` and a non-empty ``non_regression_tests`` list containing
    only pytest targets under ``tests/``. No Git write command is executed.
    """
    if not confirmed:
        raise RuntimeError("Patch application requires explicit operator confirmation")

    repo = repo.resolve()
    bundle = bundle.resolve()
    backup_root = backup_root.resolve()
    manifest_path = bundle / "PATCH_MANIFEST.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    tests = _validate_test_targets(manifest.get("non_regression_tests"))
    entries = manifest.get("files", [])
    if not entries:
        raise RuntimeError("Patch bundle contains no files")

    verified: list[tuple[Path, Path, Path, str, str]] = []
    for entry in entries:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"Unsafe patch path: {relative}")
        current = repo / relative
        replacement = bundle / "files" / relative
        if not current.is_file() or not replacement.is_file():
            raise RuntimeError(f"Missing current or replacement file: {relative}")
        before_sha = entry["before_sha256"]
        after_sha = entry["after_sha256"]
        if _hash(current) != before_sha:
            raise RuntimeError(f"Repository file changed since proposal: {relative}")
        if _hash(replacement) != after_sha:
            raise RuntimeError(f"Replacement hash mismatch: {relative}")
        verified.append((relative, current, replacement, before_sha, after_sha))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    manifest_sha = sha256(manifest_bytes).hexdigest()
    application_root = backup_root / f"{stamp}_{manifest_sha[:12]}"
    application_root.mkdir(parents=True, exist_ok=False)

    applied: list[dict[str, Any]] = []
    for relative, current, replacement, before_sha, after_sha in verified:
        backup = application_root / "files" / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, backup)
        if _hash(backup) != before_sha:
            raise RuntimeError(f"Backup hash mismatch before replacement: {relative}")
        temporary = current.with_suffix(current.suffix + ".v52tmp")
        shutil.copy2(replacement, temporary)
        if _hash(temporary) != after_sha:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Temporary replacement hash mismatch: {relative}")
        temporary.replace(current)
        if _hash(current) != after_sha:
            raise RuntimeError(f"Atomic replacement hash verification failed: {relative}")
        applied.append({
            "path": relative.as_posix(),
            "current": str(current),
            "before": before_sha,
            "after": after_sha,
            "backup": str(backup),
        })

    test_report = _run_non_regression(repo, tests)
    report: dict[str, Any] = {
        "schema_version": 2,
        "repo": str(repo),
        "bundle": str(bundle),
        "manifest_sha256": manifest_sha,
        "application_root": str(application_root),
        "applied": applied,
        "non_regression_tests": list(tests),
        "non_regression": test_report,
        "git_write_operations": False,
        "status": "pass" if test_report["returncode"] == 0 else "rollback_required",
    }

    if test_report["returncode"] != 0:
        _restore_applied(applied)
        report["status"] = "rolled_back_non_regression_failed"
        report["rollback_verified"] = all(
            Path(item["current"]).is_file() and _hash(Path(item["current"])) == item["before"]
            for item in applied
        )
        report_path = application_root / "PATCH_APPLICATION_REPORT.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise RuntimeError(f"Non-regression tests failed; patch rolled back. Report: {report_path}")

    report["rollback_verified"] = None
    report_path = application_root / "PATCH_APPLICATION_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
