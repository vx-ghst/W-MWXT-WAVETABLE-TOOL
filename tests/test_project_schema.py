from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from w_mwxt_wavetable_tool.audio import import_audio
from w_mwxt_wavetable_tool.errors import ProjectFormatError, ProjectIntegrityError
from w_mwxt_wavetable_tool.project import (
    PROJECT_CONTAINER_ID,
    PROJECT_SCHEMA_VERSION,
    MinimalProjectManifest,
    ProjectAudioRecord,
    canonical_json_bytes,
    validate_project_name,
)


def _source(tmp_path: Path):
    path = tmp_path / "source.wav"
    sf.write(path, np.linspace(-0.5, 0.5, 64), 44100, subtype="FLOAT")
    return import_audio(path)


def test_project_name_validation_accepts_unicode_and_trims() -> None:
    assert validate_project_name("  Chœur mémoire  ") == "Chœur mémoire"


@pytest.mark.parametrize("name", ["", "   ", "bad\nname", "x" * 129])
def test_project_name_validation_rejects_invalid_values(name: str) -> None:
    with pytest.raises(ProjectFormatError):
        validate_project_name(name)


def test_canonical_json_is_stable_and_utf8() -> None:
    first = canonical_json_bytes({"z": 1, "a": "é"})
    second = canonical_json_bytes({"a": "é", "z": 1})
    assert first == second == b'{"a":"\xc3\xa9","z":1}\n'


def test_project_audio_record_roundtrip(tmp_path: Path) -> None:
    source = _source(tmp_path)
    record = ProjectAudioRecord.from_audio_source(source)
    reparsed = ProjectAudioRecord.from_dict(record.to_dict())
    assert reparsed == record
    reopened = reparsed.reconstruct(source.mono_samples)
    assert reopened.to_summary() == source.to_summary()


def test_manifest_create_and_roundtrip(tmp_path: Path) -> None:
    source = _source(tmp_path)
    sample_bytes = source.mono_samples.astype("<f8", copy=False).tobytes()
    manifest = MinimalProjectManifest.create(
        project_name="Test",
        tool_version="0.2.0",
        audio=ProjectAudioRecord.from_audio_source(source),
        sample_bytes=sample_bytes,
    )
    assert manifest.schema_version == PROJECT_SCHEMA_VERSION
    assert manifest.container == PROJECT_CONTAINER_ID
    reparsed = MinimalProjectManifest.from_dict(manifest.to_dict())
    assert reparsed == manifest
    reparsed.verify_content_sha256(sample_bytes)


def test_manifest_content_hash_detects_sample_change(tmp_path: Path) -> None:
    source = _source(tmp_path)
    sample_bytes = source.mono_samples.astype("<f8", copy=False).tobytes()
    manifest = MinimalProjectManifest.create(
        project_name="Test",
        tool_version="0.2.0",
        audio=ProjectAudioRecord.from_audio_source(source),
        sample_bytes=sample_bytes,
    )
    changed = bytearray(sample_bytes)
    changed[0] ^= 1
    with pytest.raises(ProjectIntegrityError, match="content SHA-256"):
        manifest.verify_content_sha256(bytes(changed))


def test_manifest_rejects_unsupported_schema(tmp_path: Path) -> None:
    source = _source(tmp_path)
    sample_bytes = source.mono_samples.astype("<f8", copy=False).tobytes()
    manifest = MinimalProjectManifest.create(
        project_name="Test",
        tool_version="0.2.0",
        audio=ProjectAudioRecord.from_audio_source(source),
        sample_bytes=sample_bytes,
    ).to_dict()
    manifest["schema_version"] = 999
    with pytest.raises(ProjectFormatError, match="Unsupported project schema"):
        MinimalProjectManifest.from_dict(manifest)


def test_manifest_rejects_extra_fields(tmp_path: Path) -> None:
    source = _source(tmp_path)
    sample_bytes = source.mono_samples.astype("<f8", copy=False).tobytes()
    manifest = MinimalProjectManifest.create(
        project_name="Test",
        tool_version="0.2.0",
        audio=ProjectAudioRecord.from_audio_source(source),
        sample_bytes=sample_bytes,
    ).to_dict()
    manifest["unexpected"] = True
    with pytest.raises(ProjectFormatError, match="fields are invalid"):
        MinimalProjectManifest.from_dict(manifest)


def test_audio_record_rejects_disagreeing_sample_counts(tmp_path: Path) -> None:
    record = ProjectAudioRecord.from_audio_source(_source(tmp_path)).to_dict()
    record["sample_count"] = 63
    with pytest.raises(ProjectFormatError, match="sample counts disagree"):
        ProjectAudioRecord.from_dict(record)
