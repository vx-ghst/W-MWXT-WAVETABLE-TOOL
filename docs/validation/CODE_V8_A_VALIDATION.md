# CODE V8-A Validation - generic wavetable build contracts

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-A
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0F / 51c5d2c5a3672b9ff1d6b7db5aafaded4acbf41c
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY - PRIVATE SUITE AND REMOTE CI PENDING
```

## Implemented contracts

```text
schema-versioned WavetableCandidate contract
strict origin and generation-method compatibility
safe 64-sample XT stored domain -127..127
128-point reverse-negate reconstruction identity
complete per-candidate build metrics and provenance
exact 61-user-position and 64-WCTD-position constants
three-reference fixed-tail contract for positions 61-63
build policy with progression, variants and future interpolation families
required/preferred position-lock contract
required/preferred chronology contract
required-cycle and lock/chronology contradiction rejection
ready V8-0F preflight and repaired-wave-count gate
mixed real/reconstructed candidate inventory contract
complete WavetableSlot metadata contract
complete versus rejected WavetableBuild contract
multi-variant WavetableBuildSet contract
canonical JSON and deterministic SHA-256 links
```

## Compatibility contract

The following accepted contracts remain unchanged:

```text
ComplianceRegistry and pre-V8 closure schemas
CodeV5Analysis and CodeV6Analysis
all accepted V7 XT schemas
all accepted V8-0B through V8-0F schemas
version 0.7.0
```

V8-A adds a new `wavetable` package and public exports. It does not reinterpret the historical V7 trajectory or package artifacts.

## Local design validation

```text
compileall                              : PASS on isolated V8-A source bundle
V8-A targeted suite                    : 115 passed
canonical user-position count          : 61 exact
canonical WCTD-position count          : 64 exact
fixed-tail positions                   : 61, 62, 63 exact
safe generated stored range            : -127..127 exact
forbidden generated -128 gate          : PASS
candidate origin/method matrix          : PASS
candidate duplicate-content allowance  : PASS for V8-B analysis
required chronology cycle gate          : PASS
required lock/chronology conflict gate  : PASS including transitive conflicts
preference-conflict serialization       : PASS
ready/rejected preflight gate            : PASS
repaired-wave-count link                : PASS
mixed-provenance policy                 : PASS
61-slot complete-build invariant         : PASS
explicit rejected-build blockers        : PASS
NaN and infinity rejection              : PASS
canonical tuples and frozen models      : PASS
deterministic JSON and hashes           : PASS
no WCTD, SysEx or MIDI execution path    : PASS
```

## Target-environment gates still required

```text
[ ] compileall passes in the target repository
[ ] pip check passes in the target environment
[ ] V8-A targeted suite passes in the target repository
[ ] complete public suite passes
[ ] complete private suite passes with all four reference dumps mounted
[ ] isolated PEP 517 wheel includes all three wavetable modules
[ ] exact authorized file set and git diff --check pass
[ ] implementation commit SHA is recorded
[ ] twelve push and pull-request checks pass
[ ] repository is clean after the implementation commit
[ ] final closure evidence is committed in this report
```

## Acceptance assertions

- A build request cannot be created from a rejected V8-0F preflight.
- Candidate count must equal the repaired-wave count recorded by V8-0F.
- Candidate IDs are unique, while duplicate wave content remains available to V8-B.
- Candidate and slot origin/method combinations are explicit and validated.
- Generated stored samples cannot contain `-128` or values outside `-127..127`.
- The fixed tail contains exactly three explicit references and preserves its source WCTD hash.
- Required chronology constraints are acyclic.
- Required position locks cannot contradict required chronology, including transitively.
- Preference conflicts remain available for deterministic variant comparison.
- A complete build contains exactly positions 0 through 60 in order.
- A rejected build has blockers and exposes no partial slot list.
- Every automatic contract carries evidence, reason and deterministic hashes.
- No builder, interpolator, WCTD writer, SysEx generator or MIDI transport is falsely claimed by V8-A.

## Safety boundary

CODE V8-A builds no wavetable, materializes no WCTD payload, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI, and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
