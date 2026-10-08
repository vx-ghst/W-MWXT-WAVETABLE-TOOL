from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .models import ComplianceRegistry, SupportState


CAPABILITY_SUMMARY_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CapabilitySummary:
    schema_version: int
    total: int
    supported: int
    partial: int
    planned: int
    excluded: int
    post_prototype: int

    def __post_init__(self) -> None:
        if self.schema_version != CAPABILITY_SUMMARY_SCHEMA_VERSION:
            raise ValueError("Unsupported capability summary schema version")
        counts = (
            self.total,
            self.supported,
            self.partial,
            self.planned,
            self.excluded,
            self.post_prototype,
        )
        if any(value < 0 for value in counts):
            raise ValueError("Capability counts must not be negative")
        if self.total != sum(counts[1:]):
            raise ValueError("Capability counts do not add up to total")

    def to_dict(self) -> dict[str, int]:
        return {
            "schema_version": self.schema_version,
            "total": self.total,
            "supported": self.supported,
            "partial": self.partial,
            "planned": self.planned,
            "excluded": self.excluded,
            "post_prototype": self.post_prototype,
        }


def summarize_capabilities(registry: ComplianceRegistry) -> CapabilitySummary:
    counts = Counter(item.support for item in registry.requirements)
    return CapabilitySummary(
        schema_version=CAPABILITY_SUMMARY_SCHEMA_VERSION,
        total=len(registry.requirements),
        supported=counts[SupportState.SUPPORTED],
        partial=counts[SupportState.PARTIAL],
        planned=counts[SupportState.PLANNED],
        excluded=counts[SupportState.EXCLUDED],
        post_prototype=counts[SupportState.POST_PROTOTYPE],
    )
