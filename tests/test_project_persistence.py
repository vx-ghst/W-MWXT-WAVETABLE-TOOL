from __future__ import annotations

from pathlib import Path
import json
import zipfile

import numpy as np
import pytest
import soundfile as sf

from w_mwxt_wavetable_tool.audio import import_audio
from w_mwxt_wavetable_tool.errors import (
    ProjectExistsError,
    ProjectFormatError,
    ProjectIntegrityError,
    ProjectSourceError,
)
from w_mwxt_wavetable_tool.project import (
    MANIFEST_ENTRY,
    MONO_SAMPLES_ENTRY,
    SourceStatus,
    SourceValidationPolicy,
    open_project,
    save_project,
)


def _audio(tmp_path: Path, *, name: str = "source.wav"):
    path = tmp_path / name
    phase = np.arange(128, dtype=np.float64) / 128.0
    samples = 0.7 * np.sin(2.0 * np.pi * 5.0 * phase)
    sf.write(path, samples, 48000, subtype="FLOAT")
    return path, import_audio(path)


def _read_entries(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _rewrite(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in entries:
            archive.writestr(name, data)


def test_save_and_open_reproduce_imported_state(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    project_path = tmp_path / "project.mwxtproj"
    saved = save_project(source, project_path, project_name="My project", tool_version="0.2.0")
    opened = open_project(project_path)
    assert opened.manifest.project_name == "My project"
    assert opened.source_check.status is SourceStatus.UNCHANGED
    assert opened.audio_source.to_summary() == source.to_summary()
    assert opened.archive_sha256 == saved.archive_sha256


def test_two_saves_are_byte_identical(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    first = tmp_path / "first.mwxtproj"
    second = tmp_path / "second.mwxtproj"
    one = save_project(source, first, project_name="Stable", tool_version="0.2.0")
    two = save_project(source, second, project_name="Stable", tool_version="0.2.0")
    assert first.read_bytes() == second.read_bytes()
    assert one.archive_sha256 == two.archive_sha256
    assert one.manifest.content_sha256 == two.manifest.content_sha256


def test_archive_has_exact_deterministic_entries(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    project_path = tmp_path / "project.mwxtproj"
    save_project(source, project_path, tool_version="0.2.0")
    with zipfile.ZipFile(project_path, "r") as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == [MANIFEST_ENTRY, MONO_SAMPLES_ENTRY]
        assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)


def test_existing_project_requires_overwrite_opt_in(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    project_path = tmp_path / "project.mwxtproj"
    save_project(source, project_path, tool_version="0.2.0")
    with pytest.raises(ProjectExistsError):
        save_project(source, project_path, tool_version="0.2.0")
    save_project(source, project_path, overwrite=True, tool_version="0.2.0")


def test_project_extension_is_required(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    with pytest.raises(ProjectFormatError, match="extension"):
        save_project(source, tmp_path / "project.zip", tool_version="0.2.0")


def test_unicode_and_long_project_path(tmp_path: Path) -> None:
    _, source = _audio(tmp_path, name="chœur.wav")
    nested = tmp_path / ("projets_" + "x" * 70)
    project_path = nested / "mémoire_angélique.mwxtproj"
    save_project(source, project_path, project_name="Mémoire angélique", tool_version="0.2.0")
    opened = open_project(project_path)
    assert opened.manifest.project_name == "Mémoire angélique"


def test_changed_source_is_rejected_by_default(tmp_path: Path) -> None:
    source_path, source = _audio(tmp_path)
    project_path = tmp_path / "project.mwxtproj"
    save_project(source, project_path, tool_version="0.2.0")
    source_path.write_bytes(source_path.read_bytes() + b"changed")
    with pytest.raises(ProjectSourceError, match="changed"):
        open_project(project_path)


def test_changed_source_can_use_embedded_samples(tmp_path: Path) -> None:
    source_path, source = _audio(tmp_path)
    project_path = tmp_path / "project.mwxtproj"
    save_project(source, project_path, tool_version="0.2.0")
    source_path.write_bytes(source_path.read_bytes() + b"changed")
    opened = open_project(project_path, source_policy=SourceValidationPolicy.ALLOW_EMBEDDED)
    assert opened.source_check.status is SourceStatus.CHANGED
    assert opened.audio_source.state_sha256 == source.state_sha256


def test_missing_source_is_rejected_by_default(tmp_path: Path) -> None:
    source_path, source = _audio(tmp_path)
    project_path = tmp_path / "project.mwxtproj"
    save_project(source, project_path, tool_version="0.2.0")
    source_path.unlink()
    with pytest.raises(ProjectSourceError, match="missing"):
        open_project(project_path)


def test_missing_source_can_use_embedded_samples(tmp_path: Path) -> None:
    source_path, source = _audio(tmp_path)
    project_path = tmp_path / "project.mwxtproj"
    save_project(source, project_path, tool_version="0.2.0")
    source_path.unlink()
    opened = open_project(project_path, source_policy="allow_embedded")
    assert opened.source_check.status is SourceStatus.MISSING
    assert opened.audio_source.sample_sha256 == source.sample_sha256


def test_ignore_source_policy_does_not_touch_external_source(tmp_path: Path) -> None:
    source_path, source = _audio(tmp_path)
    project_path = tmp_path / "project.mwxtproj"
    save_project(source, project_path, tool_version="0.2.0")
    source_path.unlink()
    opened = open_project(project_path, source_policy="ignore")
    assert opened.source_check.status is SourceStatus.NOT_CHECKED


def test_non_zip_project_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.mwxtproj"
    path.write_text("not a zip", encoding="utf-8")
    with pytest.raises(ProjectFormatError, match="ZIP"):
        open_project(path, source_policy="ignore")


def test_missing_project_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProjectFormatError, match="does not exist"):
        open_project(tmp_path / "missing.mwxtproj", source_policy="ignore")


def test_extra_archive_entry_is_rejected(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    path = tmp_path / "project.mwxtproj"
    save_project(source, path, tool_version="0.2.0")
    entries = _read_entries(path)
    _rewrite(path, [(MANIFEST_ENTRY, entries[MANIFEST_ENTRY]), (MONO_SAMPLES_ENTRY, entries[MONO_SAMPLES_ENTRY]), ("extra.txt", b"x")])
    with pytest.raises(ProjectFormatError, match="entries are invalid"):
        open_project(path, source_policy="ignore")


def test_duplicate_archive_entry_is_rejected(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    path = tmp_path / "project.mwxtproj"
    save_project(source, path, tool_version="0.2.0")
    entries = _read_entries(path)
    with pytest.warns(UserWarning):
        _rewrite(path, [(MANIFEST_ENTRY, entries[MANIFEST_ENTRY]), (MANIFEST_ENTRY, entries[MANIFEST_ENTRY]), (MONO_SAMPLES_ENTRY, entries[MONO_SAMPLES_ENTRY])])
    with pytest.raises(ProjectFormatError, match="duplicate"):
        open_project(path, source_policy="ignore")


def test_corrupted_sample_payload_is_rejected(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    path = tmp_path / "project.mwxtproj"
    save_project(source, path, tool_version="0.2.0")
    entries = _read_entries(path)
    samples = bytearray(entries[MONO_SAMPLES_ENTRY])
    samples[10] ^= 1
    _rewrite(path, [(MANIFEST_ENTRY, entries[MANIFEST_ENTRY]), (MONO_SAMPLES_ENTRY, bytes(samples))])
    with pytest.raises(ProjectIntegrityError, match="sample SHA-256"):
        open_project(path, source_policy="ignore")


def test_truncated_sample_payload_is_rejected(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    path = tmp_path / "project.mwxtproj"
    save_project(source, path, tool_version="0.2.0")
    entries = _read_entries(path)
    _rewrite(path, [(MANIFEST_ENTRY, entries[MANIFEST_ENTRY]), (MONO_SAMPLES_ENTRY, entries[MONO_SAMPLES_ENTRY][:-8])])
    with pytest.raises(ProjectIntegrityError, match="byte length"):
        open_project(path, source_policy="ignore")


def test_corrupted_manifest_json_is_rejected(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    path = tmp_path / "project.mwxtproj"
    save_project(source, path, tool_version="0.2.0")
    entries = _read_entries(path)
    _rewrite(path, [(MANIFEST_ENTRY, b"{broken"), (MONO_SAMPLES_ENTRY, entries[MONO_SAMPLES_ENTRY])])
    with pytest.raises(ProjectFormatError, match="valid JSON"):
        open_project(path, source_policy="ignore")


def test_manifest_content_hash_change_is_rejected(tmp_path: Path) -> None:
    _, source = _audio(tmp_path)
    path = tmp_path / "project.mwxtproj"
    save_project(source, path, tool_version="0.2.0")
    entries = _read_entries(path)
    manifest = json.loads(entries[MANIFEST_ENTRY])
    manifest["project_name"] = "Tampered"
    rendered = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _rewrite(path, [(MANIFEST_ENTRY, rendered), (MONO_SAMPLES_ENTRY, entries[MONO_SAMPLES_ENTRY])])
    with pytest.raises(ProjectIntegrityError, match="content SHA-256"):
        open_project(path, source_policy="ignore")


def test_project_save_does_not_modify_source(tmp_path: Path) -> None:
    source_path, source = _audio(tmp_path)
    before = source_path.read_bytes()
    save_project(source, tmp_path / "project.mwxtproj", tool_version="0.2.0")
    assert source_path.read_bytes() == before
