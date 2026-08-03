"""Executable cahier-des-charges traceability and exclusion contracts."""

from .capabilities import (
    CAPABILITY_SUMMARY_SCHEMA_VERSION,
    CapabilitySummary,
    summarize_capabilities,
)
from .exclusions import (
    EXCLUSION_CONTRACT_SCHEMA_VERSION,
    EXCLUSION_GATES,
    ExclusionGate,
    ExclusionKind,
)
from .migrations import migrate_registry_payload
from .models import (
    EXPECTED_ACTIVE_COUNT,
    EXPECTED_EXCLUDED_COUNT,
    EXPECTED_POST_PROTOTYPE_COUNT,
    EXPECTED_REQUIREMENT_COUNT,
    REGISTRY_ID,
    REGISTRY_SCHEMA_VERSION,
    BaselineStatus,
    ComplianceFormatError,
    ComplianceRegistry,
    RegistrySource,
    RequirementRecord,
    RequirementScope,
    SupportState,
    canonical_json_bytes,
    support_for_status,
)
from .registry import (
    REGISTRY_RESOURCE,
    load_compliance_registry,
    load_compliance_registry_file,
    write_compliance_registry,
)

__all__ = [
    "BaselineStatus",
    "CAPABILITY_SUMMARY_SCHEMA_VERSION",
    "CapabilitySummary",
    "ComplianceFormatError",
    "ComplianceRegistry",
    "EXPECTED_ACTIVE_COUNT",
    "EXPECTED_EXCLUDED_COUNT",
    "EXPECTED_POST_PROTOTYPE_COUNT",
    "EXPECTED_REQUIREMENT_COUNT",
    "EXCLUSION_CONTRACT_SCHEMA_VERSION",
    "EXCLUSION_GATES",
    "ExclusionGate",
    "ExclusionKind",
    "REGISTRY_ID",
    "REGISTRY_RESOURCE",
    "REGISTRY_SCHEMA_VERSION",
    "RegistrySource",
    "RequirementRecord",
    "RequirementScope",
    "SupportState",
    "canonical_json_bytes",
    "load_compliance_registry",
    "load_compliance_registry_file",
    "migrate_registry_payload",
    "summarize_capabilities",
    "support_for_status",
    "write_compliance_registry",
]
