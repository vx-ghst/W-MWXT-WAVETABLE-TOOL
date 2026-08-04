from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping

from .code_v8h import CodeV8HAnalysis, CodeV8HStatus, CodeV8HVariant
from .consolidation import (
    DEFAULT_CONSOLIDATION_POLICY,
    ConsolidationPolicy,
    ConsolidationStatus,
    WavetableConsolidationAnalysis,
    consolidate_wavetable_build,
)
from .models import WavetableContractError

CODE_V8I_SCHEMA_VERSION = 1


def _canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WavetableContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


class CodeV8IStatus(str, Enum):
    COMPLETE = "complete"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CodeV8IVariant:
    schema_version: int
    variant_id: str
    rank: int
    v8h_variant_sha256: str
    consolidation: WavetableConsolidationAnalysis
    physical_wave_count: int
    compression_ratio: float
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8I_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported V8-I variant schema version")
        if not isinstance(self.variant_id, str) or not self.variant_id:
            raise WavetableContractError("variant_id must not be empty")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise WavetableContractError("rank must be a positive integer")
        _sha256(self.v8h_variant_sha256, name="v8h_variant_sha256")
        if not isinstance(self.consolidation, WavetableConsolidationAnalysis):
            raise WavetableContractError("consolidation must be WavetableConsolidationAnalysis")
        if self.consolidation.status is not ConsolidationStatus.COMPLETE:
            raise WavetableContractError("V8-I variants require complete consolidation")
        if (
            isinstance(self.physical_wave_count, bool)
            or not isinstance(self.physical_wave_count, int)
            or not 1 <= self.physical_wave_count <= 61
        ):
            raise WavetableContractError("physical_wave_count must be in 1..61")
        if self.consolidation.physical_wave_set is None or (
            self.consolidation.physical_wave_set.physical_wave_count
            != self.physical_wave_count
        ):
            raise WavetableContractError("physical wave count disagrees with consolidation")
        if not 0.0 <= float(self.compression_ratio) <= 1.0:
            raise WavetableContractError("compression_ratio must be between 0 and 1")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "rank": self.rank,
            "v8h_variant_sha256": self.v8h_variant_sha256,
            "consolidation": self.consolidation.to_dict(),
            "physical_wave_count": self.physical_wave_count,
            "compression_ratio": self.compression_ratio,
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result


@dataclass(frozen=True, slots=True)
class CodeV8IAnalysis:
    schema_version: int
    status: CodeV8IStatus
    v8h_analysis_sha256: str
    policy: ConsolidationPolicy
    variants: tuple[CodeV8IVariant, ...]
    primary_variant_id: str | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != CODE_V8I_SCHEMA_VERSION:
            raise WavetableContractError("Unsupported CODE V8-I schema version")
        if not isinstance(self.status, CodeV8IStatus):
            raise WavetableContractError("status must be CodeV8IStatus")
        _sha256(self.v8h_analysis_sha256, name="v8h_analysis_sha256")
        if not isinstance(self.policy, ConsolidationPolicy):
            raise WavetableContractError("policy must be ConsolidationPolicy")
        variants = tuple(self.variants)
        object.__setattr__(self, "variants", variants)
        warnings = tuple(dict.fromkeys(self.warnings))
        blockers = tuple(dict.fromkeys(self.blockers))
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "blockers", blockers)
        if any(not isinstance(item, str) or not item for item in warnings + blockers):
            raise WavetableContractError("warnings and blockers must contain strings")
        if self.status is CodeV8IStatus.COMPLETE:
            if blockers or not variants or self.primary_variant_id is None:
                raise WavetableContractError("complete V8-I analysis requires variants and no blocker")
            if tuple(item.rank for item in variants) != tuple(range(1, len(variants) + 1)):
                raise WavetableContractError("V8-I ranks must be canonical")
            ids = tuple(item.variant_id for item in variants)
            if len(set(ids)) != len(ids):
                raise WavetableContractError("V8-I variant IDs must be unique")
            if self.primary_variant_id != ids[0]:
                raise WavetableContractError("V8-I primary variant must preserve first V8-H rank")
        else:
            if not blockers or variants or self.primary_variant_id is not None:
                raise WavetableContractError("rejected V8-I analysis must expose blockers only")
        if not isinstance(self.reason, str) or not self.reason:
            raise WavetableContractError("reason must not be empty")

    @property
    def primary_variant(self) -> CodeV8IVariant | None:
        return self.variants[0] if self.variants else None

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "v8h_analysis_sha256": self.v8h_analysis_sha256,
            "policy": self.policy.to_dict(),
            "variants": [item.to_dict() for item in self.variants],
            "primary_variant_id": self.primary_variant_id,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "requirements": {
                "CDC-W61-002": "implemented",
                "CDC-W61-007": "implemented",
                "CDC-USE-001": "implemented",
                "CDC-USE-002": "implemented",
                "CDC-USE-003": "revalidated",
                "CDC-USE-004": "prepared_for_v9",
            },
            "boundaries": {
                "inventory_allocation": False,
                "wctd_materialization": False,
                "sysex_generation": False,
                "midi_transport": False,
                "v9_user_report_generated": False,
            },
            "reason": self.reason,
        }

    @property
    def analysis_sha256(self) -> str:
        return _canonical_hash(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        result = self._content_dict()
        result["analysis_sha256"] = self.analysis_sha256
        return result

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"


def _rejected(
    v8h_analysis: CodeV8HAnalysis,
    policy: ConsolidationPolicy,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    reason: str,
) -> CodeV8IAnalysis:
    return CodeV8IAnalysis(
        schema_version=CODE_V8I_SCHEMA_VERSION,
        status=CodeV8IStatus.REJECTED,
        v8h_analysis_sha256=v8h_analysis.analysis_sha256,
        policy=policy,
        variants=(),
        primary_variant_id=None,
        warnings=warnings,
        blockers=blockers,
        reason=reason,
    )


def build_code_v8i(
    v8h_analysis: CodeV8HAnalysis,
    policy: ConsolidationPolicy = DEFAULT_CONSOLIDATION_POLICY,
) -> CodeV8IAnalysis:
    """Consolidate every complete V8-H build from 61 logical slots to N waves.

    V8-H ranking is preserved.  This stage does not allocate XT memory,
    materialize WCTD, generate SysEx or produce the final V9 user report.
    """

    if not isinstance(v8h_analysis, CodeV8HAnalysis):
        raise WavetableContractError("v8h_analysis must be CodeV8HAnalysis")
    if not isinstance(policy, ConsolidationPolicy):
        raise WavetableContractError("policy must be ConsolidationPolicy")
    if v8h_analysis.status is not CodeV8HStatus.COMPLETE:
        return _rejected(
            v8h_analysis,
            policy,
            ("V8-I requires a complete V8-H analysis",),
            tuple(v8h_analysis.warnings),
            "CODE V8-I rejected incomplete V8-H input without partial output.",
        )

    built: list[CodeV8IVariant] = []
    warnings: list[str] = list(v8h_analysis.warnings)
    for item in v8h_analysis.variants:
        consolidation = consolidate_wavetable_build(item.build, policy)
        warnings.extend(consolidation.warnings)
        if consolidation.status is not ConsolidationStatus.COMPLETE:
            return _rejected(
                v8h_analysis,
                policy,
                tuple(consolidation.blockers) or (f"Consolidation failed for {item.variant_id}",),
                tuple(dict.fromkeys(warnings)),
                "CODE V8-I rejected one variant and exposed no partial consolidated set.",
            )
        assert consolidation.physical_wave_set is not None
        count = consolidation.physical_wave_set.physical_wave_count
        compression = round((61 - count) / 60.0, 12)
        built.append(
            CodeV8IVariant(
                schema_version=CODE_V8I_SCHEMA_VERSION,
                variant_id=item.variant_id,
                rank=item.rank,
                v8h_variant_sha256=item.analysis_sha256,
                consolidation=consolidation,
                physical_wave_count=count,
                compression_ratio=compression,
                reason=(
                    "V8-I preserves V8-H musical ranking while adding reversible final-table physical consolidation."
                ),
            )
        )

    variants = tuple(built)
    return CodeV8IAnalysis(
        schema_version=CODE_V8I_SCHEMA_VERSION,
        status=CodeV8IStatus.COMPLETE,
        v8h_analysis_sha256=v8h_analysis.analysis_sha256,
        policy=policy,
        variants=variants,
        primary_variant_id=variants[0].variant_id,
        warnings=tuple(dict.fromkeys(warnings)),
        blockers=(),
        reason=(
            "CODE V8-I completed deterministic consolidation of every final 61-position build into 1..61 physical waves."
        ),
    )


__all__ = [
    "CODE_V8I_SCHEMA_VERSION",
    "CodeV8IStatus",
    "CodeV8IVariant",
    "CodeV8IAnalysis",
    "build_code_v8i",
]
