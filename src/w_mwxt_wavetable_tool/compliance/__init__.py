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
from .pre_v8 import (
    CODE_V8_PREFLIGHT_SCHEMA_VERSION,
    EXPECTED_PRE_V8_REQUIREMENT_COUNT,
    PRE_V8_CLOSURE_ID,
    PRE_V8_CLOSURE_RESOURCE,
    PRE_V8_CLOSURE_SCHEMA_VERSION,
    PRE_V8_DECISION_PLAN_SCHEMA_VERSION,
    PRE_V8_DESTINATION_PREFIX,
    PRE_V8_SOURCE_CHAIN_SCHEMA_VERSION,
    ClosureStage,
    ClosureSupport,
    CodeV8PreflightAnalysis,
    PreV8ComplianceClosure,
    PreV8DecisionPlan,
    PreV8LinkError,
    PreV8ReadinessStatus,
    PreV8SourceChain,
    RequirementClosureEvidence,
    assemble_code_v8_preflight,
    assemble_pre_v8_decision_plan,
    assemble_pre_v8_source_chain,
    assert_zero_pre_v8_debt,
    load_pre_v8_compliance_closure,
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
    "CODE_V8_PREFLIGHT_SCHEMA_VERSION",
    "EXPECTED_PRE_V8_REQUIREMENT_COUNT",
    "PRE_V8_CLOSURE_ID",
    "PRE_V8_CLOSURE_RESOURCE",
    "PRE_V8_CLOSURE_SCHEMA_VERSION",
    "PRE_V8_DECISION_PLAN_SCHEMA_VERSION",
    "PRE_V8_DESTINATION_PREFIX",
    "PRE_V8_SOURCE_CHAIN_SCHEMA_VERSION",
    "ClosureStage",
    "ClosureSupport",
    "CodeV8PreflightAnalysis",
    "PreV8ComplianceClosure",
    "PreV8DecisionPlan",
    "PreV8LinkError",
    "PreV8ReadinessStatus",
    "PreV8SourceChain",
    "RequirementClosureEvidence",
    "assemble_code_v8_preflight",
    "assemble_pre_v8_decision_plan",
    "assemble_pre_v8_source_chain",
    "assert_zero_pre_v8_debt",
    "load_pre_v8_compliance_closure",
]

from .adapters import (
    LEGACY_REQUIREMENT_ID_CROSSWALK,
    resolve_requirement_reference,
    resolve_requirement_references,
)
from .migrations import migrate_requirement_references

try:
    __all__ += (
        "LEGACY_REQUIREMENT_ID_CROSSWALK",
        "resolve_requirement_reference",
        "resolve_requirement_references",
        "migrate_requirement_references",
    )
except NameError:
    pass
