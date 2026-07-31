from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import os
import tempfile
import zipfile

import numpy as np

from importlib.metadata import PackageNotFoundError, version as distribution_version
from ..audio import AudioSource, fingerprint_file
from ..version import __version__
from ..errors import (
    ProjectExistsError,
    ProjectFormatError,
    ProjectIntegrityError,
    ProjectSourceError,
)
from .minimal_schema import (
    MANIFEST_ENTRY,
    MAX_PROJECT_NAME_LENGTH,
    MONO_SAMPLE_DTYPE,
    MONO_SAMPLES_ENTRY,
    PROJECT_EXTENSION,
    MinimalProject,
    MinimalProjectManifest,
    ProjectAudioRecord,
    ProjectSourceCheck,
    SourceStatus,
    SourceValidationPolicy,
    canonical_json_bytes,
    validate_project_name,
)


MAX_MANIFEST_BYTES = 1024 * 1024
EXPECTED_ARCHIVE_ENTRIES = (MANIFEST_ENTRY, MONO_SAMPLES_ENTRY)


@dataclass(frozen=True, slots=True)
class ProjectSaveResult:
    path: Path
    archive_sha256: str
    archive_bytes: int
    manifest: MinimalProjectManifest

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "archive_sha256": self.archive_sha256,
            "archive_bytes": self.archive_bytes,
            "project_name": self.manifest.project_name,
            "content_sha256": self.manifest.content_sha256,
            "sample_sha256": self.manifest.audio.sample_sha256,
            "state_sha256": self.manifest.audio.state_sha256,
        }


def _project_path(path: str | Path, *, must_exist: bool) -> Path:
    candidate = Path(path).expanduser()
    if candidate.suffix.lower() != PROJECT_EXTENSION:
        raise ProjectFormatError(
            f"Minimal project files must use the {PROJECT_EXTENSION} extension"
        )
    if must_exist:
        if not candidate.exists():
            raise ProjectFormatError(f"Project does not exist: {candidate}")
        if not candidate.is_file():
            raise ProjectFormatError(f"Project is not a regular file: {candidate}")
        return candidate.resolve(strict=True)
    return candidate.resolve(strict=False)


def _canonical_sample_bytes(source: AudioSource) -> bytes:
    samples = np.asarray(source.mono_samples, dtype=np.float64)
    if samples.ndim != 1:
        raise ProjectFormatError("Project audio samples must be one-dimensional")
    if not np.all(np.isfinite(samples)):
        raise ProjectFormatError("Project audio samples must contain finite values only")
    return samples.astype(MONO_SAMPLE_DTYPE, copy=False).tobytes(order="C")


def _zip_entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    info.flag_bits |= 0x800
    return info


def _render_archive(manifest: MinimalProjectManifest, sample_bytes: bytes) -> bytes:
    with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode="w+b") as handle:
        with zipfile.ZipFile(handle, mode="w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(_zip_entry(MANIFEST_ENTRY), canonical_json_bytes(manifest.to_dict()))
            archive.writestr(_zip_entry(MONO_SAMPLES_ENTRY), sample_bytes)
        handle.seek(0)
        return handle.read()


def save_project(
    source: AudioSource,
    path: str | Path,
    *,
    project_name: str | None = None,
    overwrite: bool = False,
    tool_version: str | None = None,
) -> ProjectSaveResult:
    destination = _project_path(path, must_exist=False)
    if destination.exists() and not overwrite:
        raise ProjectExistsError(
            f"Project already exists: {destination}; use overwrite=True to replace it"
        )
    if destination.exists() and not destination.is_file():
        raise ProjectFormatError(f"Project destination is not a regular file: {destination}")

    selected_name = source.metadata.source_path.stem if project_name is None else project_name
    selected_name = validate_project_name(selected_name)
    if len(selected_name) > MAX_PROJECT_NAME_LENGTH:
        raise ProjectFormatError("Project name is too long")

    sample_bytes = _canonical_sample_bytes(source)
    record = ProjectAudioRecord.from_audio_source(source)
    if sha256(sample_bytes).hexdigest() != record.sample_sha256:
        raise ProjectIntegrityError("AudioSource sample hash is inconsistent before project save")
    if tool_version is None:
        try:
            selected_tool_version = distribution_version("W-MWXT-WAVETABLE-TOOL")
        except PackageNotFoundError:
            selected_tool_version = __version__
    else:
        selected_tool_version = tool_version
    manifest = MinimalProjectManifest.create(
        project_name=selected_name,
        tool_version=selected_tool_version,
        audio=record,
        sample_bytes=sample_bytes,
    )
    archive_bytes = _render_archive(manifest, sample_bytes)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary.write(archive_bytes)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        if destination.exists() and not overwrite:
            raise ProjectExistsError(f"Project appeared during save: {destination}")
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return ProjectSaveResult(
        path=destination,
        archive_sha256=sha256(archive_bytes).hexdigest(),
        archive_bytes=len(archive_bytes),
        manifest=manifest,
    )


def _parse_manifest(raw: bytes) -> MinimalProjectManifest:
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ProjectFormatError(
            f"Project manifest exceeds the {MAX_MANIFEST_BYTES}-byte safety limit"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectFormatError("Project manifest is not valid UTF-8") from exc

    def reject_constant(value: str) -> object:
        raise ProjectFormatError(f"Project manifest contains non-finite JSON value {value}")

    try:
        payload = json.loads(text, parse_constant=reject_constant)
    except ProjectFormatError:
        raise
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(f"Project manifest is not valid JSON: {exc}") from exc
    return MinimalProjectManifest.from_dict(payload)


def _read_archive(path: Path) -> tuple[bytes, MinimalProjectManifest, bytes]:
    archive_raw = path.read_bytes()
    try:
        with zipfile.ZipFile(path, mode="r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ProjectFormatError("Project archive contains duplicate entry names")
            if tuple(names) != EXPECTED_ARCHIVE_ENTRIES:
                raise ProjectFormatError(
                    "Project archive entries are invalid; expected exactly "
                    f"{list(EXPECTED_ARCHIVE_ENTRIES)}, observed {names}"
                )
            for info in infos:
                if info.compress_type != zipfile.ZIP_STORED:
                    raise ProjectFormatError(
                        f"Project entry {info.filename!r} must use deterministic stored encoding"
                    )
                if info.flag_bits & 0x1:
                    raise ProjectFormatError("Encrypted project entries are not supported")
            manifest_info = archive.getinfo(MANIFEST_ENTRY)
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise ProjectFormatError("Project manifest is too large")
            manifest_raw = archive.read(MANIFEST_ENTRY)
            manifest = _parse_manifest(manifest_raw)
            sample_info = archive.getinfo(MONO_SAMPLES_ENTRY)
            expected_sample_bytes = manifest.audio.sample_count * np.dtype(MONO_SAMPLE_DTYPE).itemsize
            if sample_info.file_size != expected_sample_bytes:
                raise ProjectIntegrityError(
                    "Embedded mono sample byte length does not match the manifest: "
                    f"expected {expected_sample_bytes}, observed {sample_info.file_size}"
                )
            sample_bytes = archive.read(MONO_SAMPLES_ENTRY)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ProjectFormatError(f"Project is not a readable ZIP container: {exc}") from exc
    return archive_raw, manifest, sample_bytes


def _check_external_source(
    manifest: MinimalProjectManifest,
    policy: SourceValidationPolicy,
) -> ProjectSourceCheck:
    source_path = manifest.audio.metadata.source_path
    expected = manifest.audio.metadata.source_sha256
    if policy is SourceValidationPolicy.IGNORE:
        return ProjectSourceCheck(
            status=SourceStatus.NOT_CHECKED,
            source_path=source_path,
            expected_sha256=expected,
            observed_sha256=None,
            reason="External source validation was explicitly disabled.",
        )
    if not source_path.exists():
        result = ProjectSourceCheck(
            status=SourceStatus.MISSING,
            source_path=source_path,
            expected_sha256=expected,
            observed_sha256=None,
            reason="The original audio source is missing; embedded mono samples remain available.",
        )
    elif not source_path.is_file():
        result = ProjectSourceCheck(
            status=SourceStatus.UNAVAILABLE,
            source_path=source_path,
            expected_sha256=expected,
            observed_sha256=None,
            reason="The original source path is not a regular file.",
        )
    else:
        try:
            observed = fingerprint_file(source_path)
        except OSError as exc:
            result = ProjectSourceCheck(
                status=SourceStatus.UNAVAILABLE,
                source_path=source_path,
                expected_sha256=expected,
                observed_sha256=None,
                reason=f"The original source could not be read: {exc}",
            )
        else:
            if observed == expected:
                result = ProjectSourceCheck(
                    status=SourceStatus.UNCHANGED,
                    source_path=source_path,
                    expected_sha256=expected,
                    observed_sha256=observed,
                    reason="The original audio source matches its stored SHA-256 fingerprint.",
                )
            else:
                result = ProjectSourceCheck(
                    status=SourceStatus.CHANGED,
                    source_path=source_path,
                    expected_sha256=expected,
                    observed_sha256=observed,
                    reason="The original audio source no longer matches its stored fingerprint.",
                )
    if policy is SourceValidationPolicy.REQUIRE_UNCHANGED and result.status is not SourceStatus.UNCHANGED:
        raise ProjectSourceError(
            f"Project source validation failed ({result.status.value}): {result.reason}"
        )
    return result


def open_project(
    path: str | Path,
    *,
    source_policy: SourceValidationPolicy | str = SourceValidationPolicy.REQUIRE_UNCHANGED,
) -> MinimalProject:
    selected_policy = SourceValidationPolicy(source_policy)
    project_path = _project_path(path, must_exist=True)
    archive_raw, manifest, sample_bytes = _read_archive(project_path)

    observed_sample_sha256 = sha256(sample_bytes).hexdigest()
    if observed_sample_sha256 != manifest.audio.sample_sha256:
        raise ProjectIntegrityError(
            "Embedded mono sample SHA-256 does not match the manifest: "
            f"expected {manifest.audio.sample_sha256}, observed {observed_sample_sha256}"
        )
    manifest.verify_content_sha256(sample_bytes)

    samples = np.frombuffer(sample_bytes, dtype=MONO_SAMPLE_DTYPE)
    if samples.size != manifest.audio.sample_count:
        raise ProjectIntegrityError("Embedded mono sample count does not match the manifest")
    if not np.all(np.isfinite(samples)):
        raise ProjectIntegrityError("Embedded mono samples contain NaN or infinity")
    audio_source = manifest.audio.reconstruct(samples.astype(np.float64, copy=True))
    source_check = _check_external_source(manifest, selected_policy)

    return MinimalProject(
        path=project_path,
        manifest=manifest,
        audio_source=audio_source,
        source_check=source_check,
        archive_sha256=sha256(archive_raw).hexdigest(),
    )
