# CODE V8-0A Addendum — Executable compliance registry architecture

**Project:** W-MWXT-WAVETABLE-TOOL
**Branch:** `code-v8-wavetable-builder`
**Baseline:** CODE V7 / `v0.7.0`
**Status:** approved architectural addendum before implementation

## 1. Reason for the addendum

The validated exhaustive CODE V8 plan requires V8-0A to provide:

- a machine-readable and testable registry for all 206 cahier-des-charges requirements;
- explicit support/capability states;
- strict schema versions;
- adapters and migrations;
- nine executable exclusion gates;
- deterministic hashes and validation.

The initial normative file list named the traceability and exclusion tests, but it did not provide implementation modules or a bundled registry resource. Implementing those requirements inside unrelated V7 modules would violate the frozen-contract rule and create silent coupling.

## 2. Authorized additions

The following files are added to the normative CODE V8 file list before code is written:

```text
CREATE src/w_mwxt_wavetable_tool/compliance/__init__.py
CREATE src/w_mwxt_wavetable_tool/compliance/models.py
CREATE src/w_mwxt_wavetable_tool/compliance/capabilities.py
CREATE src/w_mwxt_wavetable_tool/compliance/registry.py
CREATE src/w_mwxt_wavetable_tool/compliance/adapters.py
CREATE src/w_mwxt_wavetable_tool/compliance/migrations.py
CREATE src/w_mwxt_wavetable_tool/compliance/exclusions.py
CREATE src/w_mwxt_wavetable_tool/compliance/data/cdc_traceability_v1.json
CREATE tests/test_compliance_models.py
CREATE tests/test_compliance_capabilities.py
CREATE tests/test_compliance_migrations.py
CREATE docs/validation/CODE_V8_0_A_ADDENDUM.md
```

The following already-authorized files are used by V8-0A:

```text
CREATE tests/test_cdc_traceability.py
CREATE tests/test_cdc_exclusions.py
CREATE docs/validation/CODE_V8_0_A_VALIDATION.md
MODIFY .github/workflows/tests.yml
MODIFY pyproject.toml
MODIFY docs/roadmap/W-MWXT-WAVETABLE-TOOL_ROADMAP_AND_TRACEABILITY_MATRIX.md
MODIFY docs/specification/W-MWXT-WAVETABLE-TOOL_SPECIFICATION.md
MODIFY src/w_mwxt_wavetable_tool/__init__.py
```

## 3. Frozen baseline boundary

No V1–V7 report and no frozen V7 XT module is modified by V8-0A. The compliance layer observes and describes existing contracts; it does not recompute or mutate them.

## 4. Canonical registry contract

The bundled registry is schema version 1 and contains:

```text
registry identity
schema version
source document fingerprints
206 ordered requirement records
scope
baseline status
explicit support state
destination
legacy and target traceability
registry SHA-256
```

Canonical JSON uses UTF-8, sorted keys, compact separators, no NaN values, and one terminal newline. The registry hash covers the entire payload except the hash field itself.

## 5. Migration boundary

V8-0A supports:

- direct validation of schema version 1;
- adaptation of the validated legacy audit-matrix row list into schema version 1;
- migration of a legacy object containing `rows` into schema version 1;
- explicit rejection of unsupported future schema versions.

No silent downgrade or best-effort acceptance is permitted.
