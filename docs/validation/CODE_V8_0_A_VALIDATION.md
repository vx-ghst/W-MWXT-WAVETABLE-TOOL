# CODE V8-0A Validation — Executable compliance registry

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0A
Branch  : code-v8-wavetable-builder
Base    : main / v0.7.0 / 82e555248da838769061f7e5d56e8a9652bd1184
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY — REMOTE CI AND PRIVATE SUITE PENDING
```

## Purpose

CODE V8-0A converts the validated post-V7 reconciliation matrix into a strict executable contract. It does not claim that all partial or absent features are implemented. It makes every requirement visible, versioned, hashable, queryable and assigned to a closure stage before the DSP and builder work continues.

## Authorized architecture

The file-list extension is recorded before implementation in:

```text
docs/validation/CODE_V8_0_A_ADDENDUM.md
```

No frozen V7 XT module and no historical V1–V7 validation/release report is modified.

## Registry contract

```text
Registry ID              : w-mwxt-cdc-traceability
Schema version           : 1
Requirements             : 206
Active obligations       : 195
Included                 : 187
Modified                 : 2
Verify                   : 6
Deliberate exclusions    : 9
Post-prototype items     : 2
Registry SHA-256         : 64c486a4d9f3cbe5a6b7a5efe14bae631595112bfd2571a94fd9e018b3e4e0b9
```

Pinned source fingerprints:

```text
Cahier des charges SHA-256 : 86019dab690e74f608659888ea599b45ee7b1d740a56b075ca66ef149c852ba0
Audit matrix SHA-256       : 2621e479070635ae6bb008fbb588a4a80b31043f310977bfc9253a71fec13f76
Execution plan SHA-256     : 2a6e0b248a47a5c7add8fd7d4b3b56c325972611e2a52d1ddb68f937338f22c0
```

Each requirement records its exact text, source line, final scope, historical phase/module/test/acceptance, V7 baseline status, explicit support state, observed evidence, existing tests, remaining gap, corrected destination, target modules and target tests.

## Strict validation rules

The parser rejects:

- missing or additional fields;
- unknown enum values;
- invalid or duplicated requirement IDs;
- unsorted or duplicated source lines;
- empty destinations, target modules or target tests;
- inconsistent scope/status/destination combinations;
- inconsistent baseline status/support state combinations;
- unsupported schema versions;
- registry hash mismatches;
- incomplete legacy migration metadata.

Canonical JSON is UTF-8 with sorted keys, compact separators, no NaN values and one terminal newline. The SHA-256 covers the complete content except the hash field itself.

## Capability snapshot

```text
Supported baseline : 62
Partial            : 79
Planned            : 54
Excluded           : 9
Post-prototype     : 2
Total              : 206
```

This snapshot describes the audited `v0.7.0` baseline. It is not a final prototype-completion claim.

## Exclusion gates

All nine final exclusions are represented by executable gate contracts:

```text
CDC-IMP-008  manual temporal-region selection
CDC-IMP-010  MP3 import
CDC-SIG-012  stereo-content analysis after mono conversion
CDC-MODE-010 forced manual source-time range
CDC-EXC-001  other synthesizer targets
CDC-EXC-002  generic PPG profiles/export
CDC-EXC-003  Reese-only application architecture
CDC-EXC-004  mandatory WaveEdit dependency
CDC-EXC-005  opaque AI decisions
```

The tests verify the exact exclusion-ID set and concrete baseline boundaries including supported extensions, mono-only DSP input, public API, target protocol and forbidden dependencies.

## Schema adaptation and migration

Supported inputs:

```text
schema 1 registry payload                    -> strict validation
legacy validated audit-matrix row list       -> schema 1
legacy object containing exactly `rows`      -> schema 1
unknown/future schema                         -> explicit rejection
```

Migration is deterministic and idempotent for current payloads. No best-effort downgrade is allowed.

## CI change

The workflow now requires six jobs:

```text
ubuntu-latest / Python 3.11
ubuntu-latest / Python 3.12
ubuntu-latest / Python 3.13
windows-latest / Python 3.11
windows-latest / Python 3.12
windows-latest / Python 3.13
```

Each job installs the project, runs `compileall`, runs `pip check`, then executes the complete test suite.

## Local software validation

```text
compileall                         : PASS
V8-0A targeted tests              : 24 passed
Complete public suite             : 1059 passed, 4 skipped
Bundled registry import           : PASS
Wheel package-data inclusion      : PASS
Registry exact count/hash         : PASS
Nine exclusion gates              : PASS
git diff --check                  : PASS
Private-data path leakage scan    : PASS
```

The four skipped tests are the existing real-dump tests because the private dump directory is not mounted in the execution environment.

## Local pip-check limitation

The shared execution environment reports an unrelated pre-existing dependency conflict:

```text
moviepy 2.2.1 requires pillow <12.0, but pillow 12.2.0 is installed
```

Neither package is a dependency of W-MWXT-WAVETABLE-TOOL. The clean GitHub Actions matrix remains the authoritative `pip check` gate for V8-0A.

## Gates still required before V8-0A closure

```text
[ ] remote six-job CI matrix passes
[ ] clean-environment pip check passes in every CI job
[ ] private suite passes with the four reference dumps mounted
[ ] branch commit SHA is recorded
[ ] repository state is clean after the validated commit
```

## Safety boundary

CODE V8-0A opens no MIDI port, transmits no SysEx, modifies no instrument state and includes no private dump, generated SysEx, audio capture, local path or private evidence file.
