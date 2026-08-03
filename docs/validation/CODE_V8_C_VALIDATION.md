# CODE V8-C Validation - structural and essential keyframe selection

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-C
Branch  : code-v8-wavetable-builder
Base    : CODE V8-B / a973d41d2e46448bc0ec284fac3969bccb99cbec
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY - PRIVATE SUITE AND REMOTE CI PENDING
```

## Implemented contracts

```text
schema-versioned keyframe-selection policy
one deterministic representative per V8-B complete-link group
required lock and chronology participant preservation
optional source-endpoint representative preservation
explicit 1, 2, 8, 61 and above-61 capacity behavior
complete or explicit rejected selection status
bounded utility, diversity, temporal, structural and group objective
public subset scorer for small-case optimality verification
exact combinatorial search under explicit limits
deterministic greedy search above exact limits
one immutable decision per input candidate
selected, essential, forced and omitted candidate sets
redundancy versus capacity omission evidence
canonical JSON and deterministic SHA-256 links
```

## Compatibility contract

The following accepted contracts remain unchanged:

```text
all V8-A candidate, request, fixed-tail, policy and constraint schemas
all V8-B metrics, usefulness, interval and complete-link schemas
all V8-0 and V1-V7 public schemas
version 0.7.0
```

V8-C consumes V8-A and V8-B evidence without mutation and does not reinterpret their hashes or classifications.

## Local design validation

```text
compileall                                      : PASS on isolated V8-A/V8-B/V8-C bundle
V8-C targeted suite                            : 82 passed
V8-A targeted regression suite                 : 115 passed
V8-B targeted regression suite                 : 112 passed
one, two, eight and 61 distinct candidates     : PASS
above-61 reduction to exactly 61               : PASS
exact and polarity duplicate representative use: PASS
mixed real/reconstructed provenance            : PASS
required locks and chronology participants     : PASS
infeasible forced capacity rejection           : PASS with no partial selection
requested count and endpoint policy             : PASS
small-case exhaustive optimality                : PASS through public scorer
greedy large-case determinism                   : PASS
one decision per input candidate                : PASS
finite bounded objective components             : PASS
canonical tuples, frozen models and hashes      : PASS
no position, ordering, variant, WCTD or MIDI path: PASS
```

## Target-environment gates still required

```text
[ ] compileall passes in the target repository
[ ] pip check passes in the target environment
[ ] V8-C targeted suite passes in the target repository
[ ] complete public suite passes
[ ] complete private suite passes with all four reference dumps mounted
[ ] pre-V8 gate remains 62/62 supported with zero debt
[ ] isolated PEP 517 wheel includes the V8-C selection module
[ ] exact authorized file set and git diff --check pass
[ ] implementation commit SHA is recorded
[ ] twelve push and pull-request checks pass
[ ] repository is clean after the implementation commit
[ ] final closure evidence is committed in this report
```

## Acceptance assertions

- Every V8-C input links to the exact immutable V8-A request and V8-B analysis.
- Every input candidate receives exactly one explicit decision.
- Unprotected complete-link duplicates are omitted before capacity selection.
- Required locks and required chronology participants are never silently omitted.
- Complete selections contain one through 61 candidate IDs.
- More than 61 feasible candidates are reduced deterministically to exactly 61.
- Infeasible mandatory capacity returns rejected status, blockers and no partial list.
- Selected IDs are serialized in source order only and do not claim final table ordering.
- Exact small-case optimization is independently verifiable through the public subset scorer.
- Larger cases use stable deterministic greedy selection and canonical tie-breaks.
- Every objective component is finite, bounded and visible.
- No position assignment, chronology solving, variant generation, interpolation, WCTD, SysEx or MIDI execution path is introduced.

## Safety boundary

CODE V8-C performs immutable selection only. It builds no 61-slot table, materializes no WCTD payload, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path or private evidence file.
