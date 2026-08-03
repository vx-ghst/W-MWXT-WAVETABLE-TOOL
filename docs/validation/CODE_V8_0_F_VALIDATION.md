# CODE V8-0F Validation - pre-V8 aggregate and zero required-debt gate

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0F
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0E / 4db4ac6bc1ba5c7262cddef082fed6eb6294b6ce
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY - PRIVATE SUITE AND REMOTE CI PENDING
```

## Implemented contracts

```text
schema-versioned pre-V8 compliance closure ledger
exact baseline-registry SHA-256 link
62/62 required pre-V8 obligations represented
zero missing, partial, or absent pre-V8 debt
canonical 27-class taxonomy correction recorded
V3 imported-state and sample-identity link
V4-V6 aggregate provenance validation
V7 projection, optional trajectory, QC, and package validation
complete V8-0B through V8-0E component-link validation
ready versus rejected source preflight status
no hidden fallback for rejected sources
canonical JSON and deterministic aggregate SHA-256
```

## Compatibility contract

The following accepted contracts remain unchanged:

```text
ComplianceRegistry schema 1
CodeV5Analysis schema 1
CodeV6Analysis schema 1
all accepted V7 XT schemas
all accepted V8-0B through V8-0E schemas
version 0.7.0
```

The historical V8-0A registry remains the audit of the `v0.7.0` baseline. V8-0F overlays current closure evidence rather than rewriting historical baseline support states.

## Local design validation

```text
compileall                              : PASS on reconstructed V8-0E source tree
V8-0F targeted suite                   : 56 passed
Complete public suite                  : 1522 passed, 4 skipped
pre-V8 required requirement count      : 62 exact
supported pre-V8 requirement count     : 62 exact
remaining required pre-V8 debt         : 0 exact
closure stage distribution             : 2 / 12 / 19 / 24 / 4 / 1
module and test evidence paths          : PASS
baseline registry SHA-256 link          : PASS
27-class correction gate                : PASS
V3-V7 link validation                   : PASS
V8-0B through V8-0E link validation     : PASS
ready and explicit rejection states     : PASS
NaN-safe canonical JSON                 : PASS
public API exports                      : PASS
```

The four public skips are the existing private real-dump tests because private evidence is not stored in the repository.

## Target-environment gates still required

```text
[ ] compileall passes in the target repository
[ ] pip check passes in the target environment
[ ] V8-0F targeted suite passes in the target repository
[ ] complete public suite passes
[ ] complete private suite passes with all four reference dumps mounted
[ ] isolated PEP 517 wheel includes the pre-V8 module and closure ledger
[ ] exact authorized file set and git diff --check pass
[ ] implementation commit SHA is recorded
[ ] twelve push and pull-request checks pass
[ ] repository is clean after the implementation commit
[ ] final closure evidence is committed in this report
```

## Acceptance assertions

- The exact 62 active requirements destined to `V8-0*` are present once, in canonical registry order.
- No excluded or post-prototype requirement is used to inflate the closure count.
- No requirement assigned to a later CODE stage is falsely claimed as pre-V8 work.
- Every closure record has module, test, reason, and deterministic hash evidence.
- `CDC-CLS-001` records 27 canonical musical classes.
- The historical baseline registry remains byte-stable and separately hash-linked.
- V3, V4, V5, V6, and supplied V7 artifacts must form one exact provenance chain.
- Every V8-0B through V8-0E analysis and decision link must match.
- A rejected source remains rejected while the implementation debt gate remains closed.
- No MIDI or SysEx transmission path is introduced.

## Safety boundary

CODE V8-0F builds no wavetable, opens no MIDI port, transmits no SysEx, allocates no XT memory, and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
