from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any

from ..version import __version__
from .pitch import describe_frequency


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _require_ratio(value: float, *, name: str) -> float:
    result = _require_finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def _canonical_sha256(payload: dict[str, Any]) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(rendered).hexdigest()


class WorkingPitchCandidateKind(str, Enum):
    SOURCE_OCTAVE = "source_octave"
    EXPLICIT_LOCK = "explicit_lock"


@dataclass(frozen=True, slots=True)
class WorkingPitchCandidate:
    rank: int
    kind: WorkingPitchCandidateKind
    octave_shift: int | None
    target_frequency_hz: float
    target_period_samples: float
    target_midi_note: float
    nearest_midi_note: int
    note_name: str
    cents_deviation: float
    repitch_ratio: float
    transposition_cents: float
    period_distance_octaves: float
    within_preferred_period_range: bool
    score: float
    reason: str

    def __post_init__(self) -> None:
        if self.rank <= 0:
            raise ValueError("rank must be positive")
        if self.kind is WorkingPitchCandidateKind.SOURCE_OCTAVE and self.octave_shift is None:
            raise ValueError("source-octave candidates require octave_shift")
        if self.kind is WorkingPitchCandidateKind.EXPLICIT_LOCK and self.octave_shift is not None:
            raise ValueError("explicit-lock candidates must not expose octave_shift")
        for name in (
            "target_frequency_hz",
            "target_period_samples",
            "target_midi_note",
            "cents_deviation",
            "repitch_ratio",
            "transposition_cents",
            "period_distance_octaves",
            "score",
        ):
            _require_finite(getattr(self, name), name=name)
        if self.target_frequency_hz <= 0.0:
            raise ValueError("target_frequency_hz must be positive")
        if self.target_period_samples <= 0.0:
            raise ValueError("target_period_samples must be positive")
        if self.repitch_ratio <= 0.0:
            raise ValueError("repitch_ratio must be positive")
        if self.period_distance_octaves < 0.0:
            raise ValueError("period_distance_octaves must not be negative")
        _require_ratio(self.score, name="score")
        if not self.note_name:
            raise ValueError("note_name must not be empty")
        if not self.reason:
            raise ValueError("reason must not be empty")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "kind": self.kind.value,
            "octave_shift": self.octave_shift,
            "target_frequency_hz": self.target_frequency_hz,
            "target_period_samples": self.target_period_samples,
            "target_midi_note": self.target_midi_note,
            "nearest_midi_note": self.nearest_midi_note,
            "note_name": self.note_name,
            "cents_deviation": self.cents_deviation,
            "repitch_ratio": self.repitch_ratio,
            "transposition_cents": self.transposition_cents,
            "period_distance_octaves": self.period_distance_octaves,
            "within_preferred_period_range": self.within_preferred_period_range,
            "score": self.score,
            "reason": self.reason,
        }

    @property
    def candidate_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["candidate_sha256"] = self.candidate_sha256
        return result


@dataclass(frozen=True, slots=True)
class WorkingPitchCandidates:
    schema_version: int
    tool_version: str
    sample_rate: int
    sample_count: int
    sample_sha256: str
    pitch_periodicity_analysis_sha256: str
    source_frequency_hz: float | None
    source_period_samples: float | None
    source_note_name: str | None
    source_periodicity_score: float
    source_pitch_stability: float
    preferred_period_samples: float
    minimum_period_samples: float
    maximum_period_samples: float
    maximum_octave_shift: int
    candidates: tuple[WorkingPitchCandidate, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported working-pitch candidate schema version")
        if not self.tool_version or self.tool_version.strip() != self.tool_version:
            raise ValueError("tool_version must be a non-empty normalized string")
        if self.sample_rate <= 0 or self.sample_count <= 0:
            raise ValueError("sample_rate and sample_count must be positive")
        if not _hash_is_valid(self.sample_sha256):
            raise ValueError("sample_sha256 must be a lowercase SHA-256 digest")
        if not _hash_is_valid(self.pitch_periodicity_analysis_sha256):
            raise ValueError(
                "pitch_periodicity_analysis_sha256 must be a lowercase SHA-256 digest"
            )
        _require_ratio(self.source_periodicity_score, name="source_periodicity_score")
        _require_ratio(self.source_pitch_stability, name="source_pitch_stability")
        preferred = _require_finite(
            self.preferred_period_samples, name="preferred_period_samples"
        )
        minimum = _require_finite(
            self.minimum_period_samples, name="minimum_period_samples"
        )
        maximum = _require_finite(
            self.maximum_period_samples, name="maximum_period_samples"
        )
        if minimum <= 0.0 or preferred <= 0.0 or maximum <= 0.0:
            raise ValueError("period sample values must be positive")
        if not minimum <= preferred <= maximum:
            raise ValueError(
                "preferred_period_samples must be inside the minimum/maximum range"
            )
        if not 0 <= self.maximum_octave_shift <= 8:
            raise ValueError("maximum_octave_shift must be between 0 and 8")
        if self.source_frequency_hz is None:
            if self.source_period_samples is not None or self.source_note_name is not None:
                raise ValueError("unpitched sources must not expose source pitch fields")
            if self.candidates:
                raise ValueError("unpitched sources must not expose pitch candidates")
        else:
            frequency = _require_finite(
                self.source_frequency_hz, name="source_frequency_hz"
            )
            period = _require_finite(
                self.source_period_samples, name="source_period_samples"
            )
            if frequency <= 0.0 or period <= 0.0:
                raise ValueError("source pitch fields must be positive")
            if not self.source_note_name:
                raise ValueError("pitched sources require source_note_name")
            if not self.candidates:
                raise ValueError("pitched sources require at least one candidate")
        ranks = tuple(candidate.rank for candidate in self.candidates)
        if ranks != tuple(range(1, len(self.candidates) + 1)):
            raise ValueError("candidate ranks must be consecutive and start at one")
        hashes = tuple(candidate.candidate_sha256 for candidate in self.candidates)
        if len(set(hashes)) != len(hashes):
            raise ValueError("pitch candidates must be unique")

    @property
    def candidate_sha256(self) -> tuple[str, ...]:
        return tuple(candidate.candidate_sha256 for candidate in self.candidates)

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "sample_sha256": self.sample_sha256,
            "pitch_periodicity_analysis_sha256": (
                self.pitch_periodicity_analysis_sha256
            ),
            "source_frequency_hz": self.source_frequency_hz,
            "source_period_samples": self.source_period_samples,
            "source_note_name": self.source_note_name,
            "source_periodicity_score": self.source_periodicity_score,
            "source_pitch_stability": self.source_pitch_stability,
            "preferred_period_samples": self.preferred_period_samples,
            "minimum_period_samples": self.minimum_period_samples,
            "maximum_period_samples": self.maximum_period_samples,
            "maximum_octave_shift": self.maximum_octave_shift,
            "candidate_sha256": list(self.candidate_sha256),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


def _candidate(
    *,
    rank: int,
    kind: WorkingPitchCandidateKind,
    octave_shift: int | None,
    source_frequency_hz: float,
    target_frequency_hz: float,
    sample_rate: int,
    reference_a4_hz: float,
    preferred_period_samples: float,
    minimum_period_samples: float,
    maximum_period_samples: float,
) -> WorkingPitchCandidate:
    target_period_samples = float(sample_rate / target_frequency_hz)
    target_midi, nearest_midi, note_name, cents_deviation = describe_frequency(
        target_frequency_hz,
        reference_a4_hz=reference_a4_hz,
    )
    repitch_ratio = float(target_frequency_hz / source_frequency_hz)
    transposition_cents = float(1200.0 * math.log2(repitch_ratio))
    period_distance = float(
        abs(math.log2(target_period_samples / preferred_period_samples))
    )
    within_range = (
        minimum_period_samples <= target_period_samples <= maximum_period_samples
    )
    if within_range:
        range_distance = 0.0
    elif target_period_samples < minimum_period_samples:
        range_distance = abs(
            math.log2(target_period_samples / minimum_period_samples)
        )
    else:
        range_distance = abs(
            math.log2(target_period_samples / maximum_period_samples)
        )
    shift_octaves = abs(transposition_cents) / 1200.0
    score = float(
        1.0
        / (
            1.0
            + period_distance
            + 0.125 * shift_octaves
            + 0.5 * range_distance
        )
    )
    if kind is WorkingPitchCandidateKind.EXPLICIT_LOCK:
        reason = (
            "The candidate is the explicit working-pitch lock requested by the user."
        )
    elif octave_shift == 0:
        reason = (
            "The candidate preserves the detected source pitch without temporary repitching."
        )
    else:
        direction = "up" if octave_shift and octave_shift > 0 else "down"
        reason = (
            f"The candidate moves the source {direction} by {abs(int(octave_shift or 0))} "
            "octave(s) while preserving pitch class and harmonic ratios."
        )
    if within_range:
        reason += " Its period is inside the configured working range."
    else:
        reason += " Its period remains outside the configured working range."
    return WorkingPitchCandidate(
        rank=rank,
        kind=kind,
        octave_shift=octave_shift,
        target_frequency_hz=float(target_frequency_hz),
        target_period_samples=target_period_samples,
        target_midi_note=target_midi,
        nearest_midi_note=nearest_midi,
        note_name=note_name,
        cents_deviation=cents_deviation,
        repitch_ratio=repitch_ratio,
        transposition_cents=transposition_cents,
        period_distance_octaves=period_distance,
        within_preferred_period_range=within_range,
        score=score,
        reason=reason,
    )


def generate_working_pitch_candidates(
    pitch_analysis: Any,
    *,
    preferred_period_samples: float = 128.0,
    minimum_period_samples: float = 64.0,
    maximum_period_samples: float = 256.0,
    maximum_octave_shift: int = 4,
    locked_frequency_hz: float | None = None,
    tool_version: str = __version__,
) -> WorkingPitchCandidates:
    """Generate deterministic octave-preserving working-pitch candidates.

    The stage only plans a temporary pitch transform. It does not resample or alter
    source audio. An explicit lock may be added to the ranked set, but requires a
    detected source frequency so that its repitch ratio is measurable.
    """

    preferred = _require_finite(
        preferred_period_samples, name="preferred_period_samples"
    )
    minimum = _require_finite(minimum_period_samples, name="minimum_period_samples")
    maximum = _require_finite(maximum_period_samples, name="maximum_period_samples")
    if minimum <= 0.0 or preferred <= 0.0 or maximum <= 0.0:
        raise ValueError("period sample values must be positive")
    if not minimum <= preferred <= maximum:
        raise ValueError(
            "preferred_period_samples must be inside the minimum/maximum range"
        )
    if not isinstance(maximum_octave_shift, int) or not 0 <= maximum_octave_shift <= 8:
        raise ValueError("maximum_octave_shift must be an integer between 0 and 8")
    if not tool_version or tool_version.strip() != tool_version:
        raise ValueError("tool_version must be a non-empty normalized string")

    sample_rate = int(pitch_analysis.sample_rate)
    sample_count = int(pitch_analysis.sample_count)
    sample_hash = str(pitch_analysis.sample_sha256)
    analysis_hash = str(pitch_analysis.analysis_sha256)
    if sample_rate <= 0 or sample_count <= 0:
        raise ValueError("pitch analysis sample identity must be positive")
    if not _hash_is_valid(sample_hash) or not _hash_is_valid(analysis_hash):
        raise ValueError("pitch analysis hashes must be lowercase SHA-256 digests")

    periodicity_score = _require_ratio(
        pitch_analysis.periodicity_score, name="periodicity_score"
    )
    pitch_stability = _require_ratio(
        pitch_analysis.pitch_stability, name="pitch_stability"
    )
    source_frequency = pitch_analysis.frequency_hz
    if source_frequency is None:
        if locked_frequency_hz is not None:
            raise ValueError(
                "locked_frequency_hz requires an available detected source frequency"
            )
        return WorkingPitchCandidates(
            schema_version=1,
            tool_version=tool_version,
            sample_rate=sample_rate,
            sample_count=sample_count,
            sample_sha256=sample_hash,
            pitch_periodicity_analysis_sha256=analysis_hash,
            source_frequency_hz=None,
            source_period_samples=None,
            source_note_name=None,
            source_periodicity_score=periodicity_score,
            source_pitch_stability=pitch_stability,
            preferred_period_samples=preferred,
            minimum_period_samples=minimum,
            maximum_period_samples=maximum,
            maximum_octave_shift=maximum_octave_shift,
            candidates=(),
        )

    source_frequency = _require_finite(source_frequency, name="source_frequency_hz")
    if source_frequency <= 0.0 or source_frequency >= sample_rate / 2.0:
        raise ValueError("source_frequency_hz must be positive and below Nyquist")
    reference_a4_hz = float(getattr(pitch_analysis, "reference_a4_hz", 440.0))
    _, _, source_note_name, _ = describe_frequency(
        source_frequency,
        reference_a4_hz=reference_a4_hz,
    )

    unsorted: list[WorkingPitchCandidate] = []
    for octave_shift in range(-maximum_octave_shift, maximum_octave_shift + 1):
        target_frequency = float(source_frequency * (2.0 ** octave_shift))
        if target_frequency <= 0.0 or target_frequency >= sample_rate / 2.0:
            continue
        unsorted.append(
            _candidate(
                rank=1,
                kind=WorkingPitchCandidateKind.SOURCE_OCTAVE,
                octave_shift=octave_shift,
                source_frequency_hz=source_frequency,
                target_frequency_hz=target_frequency,
                sample_rate=sample_rate,
                reference_a4_hz=reference_a4_hz,
                preferred_period_samples=preferred,
                minimum_period_samples=minimum,
                maximum_period_samples=maximum,
            )
        )

    if locked_frequency_hz is not None:
        locked = _require_finite(locked_frequency_hz, name="locked_frequency_hz")
        if locked <= 0.0 or locked >= sample_rate / 2.0:
            raise ValueError("locked_frequency_hz must be positive and below Nyquist")
        unsorted.append(
            _candidate(
                rank=1,
                kind=WorkingPitchCandidateKind.EXPLICIT_LOCK,
                octave_shift=None,
                source_frequency_hz=source_frequency,
                target_frequency_hz=locked,
                sample_rate=sample_rate,
                reference_a4_hz=reference_a4_hz,
                preferred_period_samples=preferred,
                minimum_period_samples=minimum,
                maximum_period_samples=maximum,
            )
        )

    unsorted.sort(
        key=lambda item: (
            item.kind is WorkingPitchCandidateKind.EXPLICIT_LOCK,
            not item.within_preferred_period_range,
            item.period_distance_octaves,
            abs(item.transposition_cents),
            item.target_frequency_hz,
        )
    )
    ranked = tuple(
        replace(candidate, rank=index)
        for index, candidate in enumerate(unsorted, start=1)
    )
    return WorkingPitchCandidates(
        schema_version=1,
        tool_version=tool_version,
        sample_rate=sample_rate,
        sample_count=sample_count,
        sample_sha256=sample_hash,
        pitch_periodicity_analysis_sha256=analysis_hash,
        source_frequency_hz=source_frequency,
        source_period_samples=float(sample_rate / source_frequency),
        source_note_name=source_note_name,
        source_periodicity_score=periodicity_score,
        source_pitch_stability=pitch_stability,
        preferred_period_samples=preferred,
        minimum_period_samples=minimum,
        maximum_period_samples=maximum,
        maximum_octave_shift=maximum_octave_shift,
        candidates=ranked,
    )
