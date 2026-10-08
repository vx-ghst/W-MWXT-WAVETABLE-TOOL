from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
import json
import math

import numpy as np

from ..audio.models import (
    AudioContainerFormat,
    AudioMeasurements,
    AudioMetadata,
    AudioSource,
    MonoConversionReport,
    MonoPolicy,
    MonoStrategy,
)
from ..errors import ProjectFormatError, ProjectIntegrityError


PROJECT_CONTAINER_ID = "w-mwxt-minimal-project"
PROJECT_SCHEMA_VERSION = 1
PROJECT_EXTENSION = ".mwxtproj"
MANIFEST_ENTRY = "manifest.json"
MONO_SAMPLES_ENTRY = "audio/mono-f64le.bin"
MONO_SAMPLE_DTYPE = "<f8"
MAX_PROJECT_NAME_LENGTH = 128


class SourceValidationPolicy(str, Enum):
    REQUIRE_UNCHANGED = "require_unchanged"
    ALLOW_EMBEDDED = "allow_embedded"
    IGNORE = "ignore"


class SourceStatus(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    NOT_CHECKED = "not_checked"


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProjectFormatError(f"{label} must be a JSON object")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], *, expected: set[str], label: str
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"extra={extra}")
        raise ProjectFormatError(f"{label} fields are invalid: {', '.join(details)}")


def _require_string(value: object, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ProjectFormatError(f"{label} must be a string")
    if not allow_empty and not value:
        raise ProjectFormatError(f"{label} must not be empty")
    return value


def _require_int(value: object, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectFormatError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ProjectFormatError(f"{label} must be >= {minimum}")
    return value


def _require_float(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectFormatError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ProjectFormatError(f"{label} must be a finite number")
    return result


def _require_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ProjectFormatError(f"{label} must be a boolean")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    result = _require_string(value, label=label)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise ProjectFormatError(f"{label} must be a lowercase SHA-256 hexadecimal digest")
    return result


def validate_project_name(value: str) -> str:
    if not isinstance(value, str):
        raise ProjectFormatError("Project name must be a string")
    normalized = value.strip()
    if not normalized:
        raise ProjectFormatError("Project name must not be empty")
    if len(normalized) > MAX_PROJECT_NAME_LENGTH:
        raise ProjectFormatError(
            f"Project name must contain at most {MAX_PROJECT_NAME_LENGTH} characters"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ProjectFormatError("Project name must not contain control characters")
    return normalized


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProjectFormatError(f"Project manifest cannot be serialized: {exc}") from exc
    return (rendered + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class ProjectSourceCheck:
    status: SourceStatus
    source_path: Path
    expected_sha256: str
    observed_sha256: str | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "source_path": str(self.source_path),
            "expected_sha256": self.expected_sha256,
            "observed_sha256": self.observed_sha256,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ProjectAudioRecord:
    metadata: AudioMetadata
    mono_conversion: MonoConversionReport
    measurements: AudioMeasurements
    sample_count: int
    sample_dtype: str
    sample_entry: str
    sample_sha256: str
    state_sha256: str

    @classmethod
    def from_audio_source(cls, source: AudioSource) -> ProjectAudioRecord:
        return cls(
            metadata=source.metadata,
            mono_conversion=source.mono_conversion,
            measurements=source.measurements,
            sample_count=int(source.mono_samples.size),
            sample_dtype=MONO_SAMPLE_DTYPE,
            sample_entry=MONO_SAMPLES_ENTRY,
            sample_sha256=source.sample_sha256,
            state_sha256=source.state_sha256,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "metadata": self.metadata.to_dict(),
            "mono_conversion": self.mono_conversion.to_dict(),
            "measurements": self.measurements.to_dict(),
            "sample_count": self.sample_count,
            "sample_dtype": self.sample_dtype,
            "sample_entry": self.sample_entry,
            "sample_sha256": self.sample_sha256,
            "state_sha256": self.state_sha256,
        }

    @classmethod
    def from_dict(cls, value: object) -> ProjectAudioRecord:
        payload = _require_mapping(value, label="audio")
        _require_exact_keys(
            payload,
            expected={
                "metadata",
                "mono_conversion",
                "measurements",
                "sample_count",
                "sample_dtype",
                "sample_entry",
                "sample_sha256",
                "state_sha256",
            },
            label="audio",
        )
        metadata_payload = _require_mapping(payload["metadata"], label="audio.metadata")
        _require_exact_keys(
            metadata_payload,
            expected={
                "source_path",
                "container",
                "libsndfile_format",
                "subtype",
                "endian",
                "sample_rate",
                "channels",
                "frames",
                "duration_seconds",
                "source_bytes",
                "source_mtime_ns",
                "source_sha256",
                "source_extension",
                "extension_matches_container",
            },
            label="audio.metadata",
        )
        try:
            container = AudioContainerFormat(
                _require_string(metadata_payload["container"], label="audio.metadata.container")
            )
        except ValueError as exc:
            raise ProjectFormatError("audio.metadata.container is unsupported") from exc
        metadata = AudioMetadata(
            source_path=Path(
                _require_string(metadata_payload["source_path"], label="audio.metadata.source_path")
            ),
            container=container,
            libsndfile_format=_require_string(
                metadata_payload["libsndfile_format"], label="audio.metadata.libsndfile_format"
            ),
            subtype=_require_string(metadata_payload["subtype"], label="audio.metadata.subtype"),
            endian=_require_string(metadata_payload["endian"], label="audio.metadata.endian"),
            sample_rate=_require_int(
                metadata_payload["sample_rate"], label="audio.metadata.sample_rate", minimum=1
            ),
            channels=_require_int(
                metadata_payload["channels"], label="audio.metadata.channels", minimum=1
            ),
            frames=_require_int(
                metadata_payload["frames"], label="audio.metadata.frames", minimum=0
            ),
            duration_seconds=_require_float(
                metadata_payload["duration_seconds"], label="audio.metadata.duration_seconds"
            ),
            source_bytes=_require_int(
                metadata_payload["source_bytes"], label="audio.metadata.source_bytes", minimum=0
            ),
            source_mtime_ns=_require_int(
                metadata_payload["source_mtime_ns"], label="audio.metadata.source_mtime_ns", minimum=0
            ),
            source_sha256=_require_sha256(
                metadata_payload["source_sha256"], label="audio.metadata.source_sha256"
            ),
            source_extension=_require_string(
                metadata_payload["source_extension"],
                label="audio.metadata.source_extension",
                allow_empty=True,
            ),
            extension_matches_container=_require_bool(
                metadata_payload["extension_matches_container"],
                label="audio.metadata.extension_matches_container",
            ),
        )

        conversion_payload = _require_mapping(
            payload["mono_conversion"], label="audio.mono_conversion"
        )
        legacy_conversion_fields = {
            "policy",
            "strategy",
            "source_channels",
            "selected_channel",
            "channel_rms",
            "stereo_correlation",
            "reason",
        }
        extended_conversion_fields = legacy_conversion_fields | {
            "selected_candidate",
            "candidate_periodicity_scores",
            "periodicity_margin",
        }
        conversion_fields = set(conversion_payload)
        if conversion_fields not in (
            legacy_conversion_fields,
            extended_conversion_fields,
        ):
            expected = (
                extended_conversion_fields
                if conversion_fields & (
                    extended_conversion_fields - legacy_conversion_fields
                )
                else legacy_conversion_fields
            )
            _require_exact_keys(
                conversion_payload,
                expected=expected,
                label="audio.mono_conversion",
            )
        try:
            policy = MonoPolicy(
                _require_string(conversion_payload["policy"], label="audio.mono_conversion.policy")
            )
            strategy = MonoStrategy(
                _require_string(
                    conversion_payload["strategy"], label="audio.mono_conversion.strategy"
                )
            )
        except ValueError as exc:
            raise ProjectFormatError("audio.mono_conversion enum value is unsupported") from exc
        channel_rms_payload = conversion_payload["channel_rms"]
        if not isinstance(channel_rms_payload, list):
            raise ProjectFormatError("audio.mono_conversion.channel_rms must be an array")
        channel_rms = tuple(
            _require_float(item, label=f"audio.mono_conversion.channel_rms[{index}]")
            for index, item in enumerate(channel_rms_payload)
        )
        selected_raw = conversion_payload["selected_channel"]
        selected_channel = (
            None
            if selected_raw is None
            else _require_int(
                selected_raw, label="audio.mono_conversion.selected_channel", minimum=0
            )
        )
        correlation_raw = conversion_payload["stereo_correlation"]
        stereo_correlation = (
            None
            if correlation_raw is None
            else _require_float(
                correlation_raw, label="audio.mono_conversion.stereo_correlation"
            )
        )
        selected_candidate: str | None = None
        candidate_periodicity_scores: tuple[tuple[str, float], ...] = ()
        periodicity_margin: float | None = None
        if conversion_fields == extended_conversion_fields:
            selected_candidate_raw = conversion_payload["selected_candidate"]
            selected_candidate = (
                None
                if selected_candidate_raw is None
                else _require_string(
                    selected_candidate_raw,
                    label="audio.mono_conversion.selected_candidate",
                )
            )
            score_payload = conversion_payload["candidate_periodicity_scores"]
            if not isinstance(score_payload, list):
                raise ProjectFormatError(
                    "audio.mono_conversion.candidate_periodicity_scores must be an array"
                )
            parsed_scores: list[tuple[str, float]] = []
            for index, item in enumerate(score_payload):
                score_item = _require_mapping(
                    item,
                    label=(
                        "audio.mono_conversion.candidate_periodicity_scores"
                        f"[{index}]"
                    ),
                )
                _require_exact_keys(
                    score_item,
                    expected={"name", "periodicity_score"},
                    label=(
                        "audio.mono_conversion.candidate_periodicity_scores"
                        f"[{index}]"
                    ),
                )
                parsed_scores.append(
                    (
                        _require_string(
                            score_item["name"],
                            label=(
                                "audio.mono_conversion.candidate_periodicity_scores"
                                f"[{index}].name"
                            ),
                        ),
                        _require_float(
                            score_item["periodicity_score"],
                            label=(
                                "audio.mono_conversion.candidate_periodicity_scores"
                                f"[{index}].periodicity_score"
                            ),
                        ),
                    )
                )
            candidate_periodicity_scores = tuple(parsed_scores)
            margin_raw = conversion_payload["periodicity_margin"]
            periodicity_margin = (
                None
                if margin_raw is None
                else _require_float(
                    margin_raw,
                    label="audio.mono_conversion.periodicity_margin",
                )
            )
        mono_conversion = MonoConversionReport(
            policy=policy,
            strategy=strategy,
            source_channels=_require_int(
                conversion_payload["source_channels"],
                label="audio.mono_conversion.source_channels",
                minimum=1,
            ),
            selected_channel=selected_channel,
            channel_rms=channel_rms,
            stereo_correlation=stereo_correlation,
            reason=_require_string(
                conversion_payload["reason"], label="audio.mono_conversion.reason"
            ),
            selected_candidate=selected_candidate,
            candidate_periodicity_scores=candidate_periodicity_scores,
            periodicity_margin=periodicity_margin,
        )

        measurements_payload = _require_mapping(
            payload["measurements"], label="audio.measurements"
        )
        _require_exact_keys(
            measurements_payload,
            expected={
                "sample_count",
                "minimum",
                "maximum",
                "peak_absolute",
                "rms",
                "mean",
                "dc_offset",
                "is_silent",
                "has_dc_offset",
                "all_finite",
            },
            label="audio.measurements",
        )
        measurements = AudioMeasurements(
            sample_count=_require_int(
                measurements_payload["sample_count"],
                label="audio.measurements.sample_count",
                minimum=0,
            ),
            minimum=_require_float(
                measurements_payload["minimum"], label="audio.measurements.minimum"
            ),
            maximum=_require_float(
                measurements_payload["maximum"], label="audio.measurements.maximum"
            ),
            peak_absolute=_require_float(
                measurements_payload["peak_absolute"],
                label="audio.measurements.peak_absolute",
            ),
            rms=_require_float(measurements_payload["rms"], label="audio.measurements.rms"),
            mean=_require_float(measurements_payload["mean"], label="audio.measurements.mean"),
            dc_offset=_require_float(
                measurements_payload["dc_offset"], label="audio.measurements.dc_offset"
            ),
            is_silent=_require_bool(
                measurements_payload["is_silent"], label="audio.measurements.is_silent"
            ),
            has_dc_offset=_require_bool(
                measurements_payload["has_dc_offset"],
                label="audio.measurements.has_dc_offset",
            ),
            all_finite=_require_bool(
                measurements_payload["all_finite"], label="audio.measurements.all_finite"
            ),
        )

        sample_count = _require_int(payload["sample_count"], label="audio.sample_count", minimum=0)
        sample_dtype = _require_string(payload["sample_dtype"], label="audio.sample_dtype")
        sample_entry = _require_string(payload["sample_entry"], label="audio.sample_entry")
        if sample_dtype != MONO_SAMPLE_DTYPE:
            raise ProjectFormatError(
                f"audio.sample_dtype must be {MONO_SAMPLE_DTYPE!r}, got {sample_dtype!r}"
            )
        if sample_entry != MONO_SAMPLES_ENTRY:
            raise ProjectFormatError(
                f"audio.sample_entry must be {MONO_SAMPLES_ENTRY!r}, got {sample_entry!r}"
            )
        if sample_count != metadata.frames or sample_count != measurements.sample_count:
            raise ProjectFormatError(
                "Project sample counts disagree between audio, metadata, and measurements"
            )
        if len(channel_rms) != metadata.channels:
            raise ProjectFormatError(
                "Project channel RMS count does not match metadata channel count"
            )
        if mono_conversion.source_channels != metadata.channels:
            raise ProjectFormatError(
                "Project mono conversion channel count does not match metadata"
            )
        if selected_channel is not None and selected_channel >= metadata.channels:
            raise ProjectFormatError("Selected mono channel is outside the source channel range")

        return cls(
            metadata=metadata,
            mono_conversion=mono_conversion,
            measurements=measurements,
            sample_count=sample_count,
            sample_dtype=sample_dtype,
            sample_entry=sample_entry,
            sample_sha256=_require_sha256(
                payload["sample_sha256"], label="audio.sample_sha256"
            ),
            state_sha256=_require_sha256(
                payload["state_sha256"], label="audio.state_sha256"
            ),
        )

    def reconstruct(self, samples: np.ndarray) -> AudioSource:
        source = AudioSource(
            metadata=self.metadata,
            mono_samples=samples,
            measurements=self.measurements,
            mono_conversion=self.mono_conversion,
        )
        if source.sample_sha256 != self.sample_sha256:
            raise ProjectIntegrityError("Embedded mono sample SHA-256 does not match the manifest")
        if source.state_sha256 != self.state_sha256:
            raise ProjectIntegrityError("Reopened audio state SHA-256 does not match the manifest")
        return source


@dataclass(frozen=True, slots=True)
class MinimalProjectManifest:
    project_name: str
    tool_version: str
    audio: ProjectAudioRecord
    content_sha256: str
    schema_version: int = PROJECT_SCHEMA_VERSION
    container: str = PROJECT_CONTAINER_ID

    def core_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "container": self.container,
            "tool_version": self.tool_version,
            "project_name": self.project_name,
            "audio": self.audio.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.core_dict()
        payload["content_sha256"] = self.content_sha256
        return payload

    @classmethod
    def create(
        cls,
        *,
        project_name: str,
        tool_version: str,
        audio: ProjectAudioRecord,
        sample_bytes: bytes,
    ) -> MinimalProjectManifest:
        provisional = cls(
            project_name=validate_project_name(project_name),
            tool_version=_require_string(tool_version, label="tool_version"),
            audio=audio,
            content_sha256="0" * 64,
        )
        content_sha256 = provisional.calculate_content_sha256(sample_bytes)
        return cls(
            project_name=provisional.project_name,
            tool_version=provisional.tool_version,
            audio=audio,
            content_sha256=content_sha256,
        )

    @classmethod
    def from_dict(cls, value: object) -> MinimalProjectManifest:
        payload = _require_mapping(value, label="manifest")
        _require_exact_keys(
            payload,
            expected={
                "schema_version",
                "container",
                "tool_version",
                "project_name",
                "audio",
                "content_sha256",
            },
            label="manifest",
        )
        schema_version = _require_int(
            payload["schema_version"], label="schema_version", minimum=1
        )
        if schema_version != PROJECT_SCHEMA_VERSION:
            raise ProjectFormatError(
                f"Unsupported project schema version {schema_version}; expected {PROJECT_SCHEMA_VERSION}"
            )
        container = _require_string(payload["container"], label="container")
        if container != PROJECT_CONTAINER_ID:
            raise ProjectFormatError(
                f"Unsupported project container {container!r}; expected {PROJECT_CONTAINER_ID!r}"
            )
        return cls(
            project_name=validate_project_name(
                _require_string(payload["project_name"], label="project_name")
            ),
            tool_version=_require_string(payload["tool_version"], label="tool_version"),
            audio=ProjectAudioRecord.from_dict(payload["audio"]),
            content_sha256=_require_sha256(
                payload["content_sha256"], label="content_sha256"
            ),
            schema_version=schema_version,
            container=container,
        )

    def calculate_content_sha256(self, sample_bytes: bytes) -> str:
        digest = sha256()
        digest.update(canonical_json_bytes(self.core_dict()))
        digest.update(b"\0")
        digest.update(sample_bytes)
        return digest.hexdigest()

    def verify_content_sha256(self, sample_bytes: bytes) -> None:
        actual = self.calculate_content_sha256(sample_bytes)
        if actual != self.content_sha256:
            raise ProjectIntegrityError(
                "Project content SHA-256 does not match the manifest: "
                f"expected {self.content_sha256}, observed {actual}"
            )


@dataclass(frozen=True, slots=True)
class MinimalProject:
    path: Path
    manifest: MinimalProjectManifest
    audio_source: AudioSource
    source_check: ProjectSourceCheck
    archive_sha256: str

    def to_summary(self) -> dict[str, object]:
        return {
            "project": {
                "path": str(self.path),
                "name": self.manifest.project_name,
                "container": self.manifest.container,
                "schema_version": self.manifest.schema_version,
                "tool_version": self.manifest.tool_version,
                "content_sha256": self.manifest.content_sha256,
                "archive_sha256": self.archive_sha256,
            },
            "source_check": self.source_check.to_dict(),
            "audio": self.audio_source.to_summary(),
        }
