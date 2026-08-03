# CODE V8-B Validation - usefulness, structure, breakpoints and deduplication

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-B
Branch  : code-v8-wavetable-builder
Base    : CODE V8-A / ef7827060b474d3241d20df752b57bf0e14fb436
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY - PRIVATE SUITE AND REMOTE CI PENDING
```

## Implemented contracts

```text
schema-versioned wave-shape metrics
fixed 128-point reconstruction and 32-bin deterministic DFT
exact, polarity-equivalent, near and distinct pair analysis
source-ordered stable, transition and breakpoint intervals
moderate/strong transition threshold evidence
waveform, spectral, level, brightness, Bass and polarity breakpoint kinds
per-candidate structural/usefulness classification
feature-extreme preservation evidence
deterministic complete-link duplicate grouping
required-lock and required-chronology protection
explicit representative, redundant, protected and removable candidate states
distinct-wave count and >61 warning
linked CodeV8BAnalysis aggregate
canonical JSON and deterministic SHA-256
```

## Compatibility contract

The following accepted contracts remain unchanged:

```text
all V8-A candidate, fixed-tail, request, constraint, slot, build and build-set schemas
all V8-0 and V1-V7 public schemas
version 0.7.0
```

V8-B consumes `WavetableBuildRequest` and never mutates the request or candidate objects.

## Local design validation

```text
compileall                                        : PASS on isolated V8-A/V8-B bundle
V8-A plus V8-B targeted bundle                   : 227 passed
V8-B targeted suite                              : 112 passed
invalid sample length/type/range gates            : PASS
zero, sine, square and deterministic corpus       : PASS
metric bounds, frozen models and finite values    : PASS
pair symmetry and exact/polarity identities       : PASS
stable, moderate/strong transition and breakpoint : PASS
source-order and interval-hash links               : PASS
ineligible and extreme-feature classification      : PASS
exact, polarity and near duplicate groups          : PASS
complete-link anti-chain gate                      : PASS
required lock/chronology protection                : PASS
representative ranking and >61 warning             : PASS
request/structure/dedup aggregate hash links       : PASS
public API compatibility                           : PASS
no selection, placement, interpolation or WCTD     : PASS
```

## Target-environment gates still required

```text
[ ] compileall passes in the target repository
[ ] pip check passes in the target environment
[ ] V8-B targeted suite passes in the target repository
[ ] complete public suite passes
[ ] complete private suite passes with all four reference dumps mounted
[ ] pre-V8 gate remains 62/62 supported with zero debt
[ ] isolated PEP 517 wheel includes all six wavetable modules
[ ] exact authorized file set and git diff --check pass
[ ] implementation commit SHA is recorded
[ ] twelve push and pull-request checks pass
[ ] repository is clean after the implementation commit
[ ] final closure evidence is committed in this report
```

## Acceptance assertions

- Every input candidate is analyzed exactly once and remains immutable.
- Every adjacent source-order interval is labeled stable, transition or breakpoint.
- The configured stable, transition and breakpoint thresholds are all effective.
- Breakpoint evidence is explicit and never inferred from one opaque score alone.
- Exact and polarity-equivalent identities are preserved as distinct duplicate kinds.
- Near-duplicate decisions require waveform/perceptual, spectral, feature and correlation gates.
- Duplicate groups use complete-link membership and cannot rely on transitive chaining.
- Required locks and chronology constraints protect referenced candidates.
- The distinct-wave count equals the number of deterministic duplicate groups.
- V8-B exposes candidates that V8-C may omit but never removes them itself.
- More than 61 distinct groups produces an explicit V8-C warning.
- The engineering perceptual-distance proxy is not claimed as calibrated auditory truth.
- Every analysis object carries explicit evidence, reason, canonical serialization and hashes.
- No final keyframe choice, position assignment, table ordering, interpolation, WCTD, SysEx or MIDI execution path is introduced.

## Safety boundary

CODE V8-B performs immutable analysis only. It builds no wavetable, materializes no WCTD payload, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path or private evidence file.
