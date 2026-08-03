# CODE V8-D Validation - ordering, placement, locks, chronology and variants

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-D
Branch  : code-v8-wavetable-builder
Base    : CODE V8-C / 4dd3eeb32a638eb45be96a41606aeb3bcd5f75b5
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY - PRIVATE SUITE AND REMOTE CI PENDING
```

## Implemented contracts

```text
schema-versioned ordering, placement and variant policies
exact selected-set identity preservation from V8-C
five-term public ordering objective
six deterministic ordering strategies
exhaustive small-case and topological greedy large-case solving
required and preference chronology outcomes
required lock ordering and capacity feasibility
sparse unique position assignment across editable positions 1-61
hard required anchors and feasible preference anchors
five deterministic placement biases
explicit occupied and open positions for V8-E
ranked and signature-deduplicated placement variants
moved-candidate and position-delta evidence
complete or rejected results with no partial fallback
canonical JSON and deterministic SHA-256 links
```

## Compatibility contract

The following accepted contracts remain unchanged:

```text
all V8-A request, candidate, policy, lock and chronology schemas
all V8-B metrics, usefulness and complete-link schemas
all V8-C selection policies, decisions and aggregate schemas
all V8-0 and V1-V7 public schemas
version 0.7.0
```

V8-D consumes V8-A through V8-C evidence without mutation and preserves every selected candidate ID exactly once.

## Local design validation

```text
compileall                                         : PASS on isolated V8-A/V8-B/V8-C/V8-D bundle
V8-D targeted suite                               : 97 passed
V8-A targeted regression suite                    : 115 passed
V8-B targeted regression suite                    : 112 passed
V8-C targeted regression suite                    : 82 passed
one, two, eight and 61-position capacity behavior         : PASS
mixed real/reconstructed provenance               : PASS
six ordering strategies and five spacing biases   : PASS
five-term weighted compromise                     : PASS
small-case exhaustive ordering optimality         : PASS through public scorer
large-case deterministic topological ordering     : PASS
required locks and chronology                     : PASS
preference lock/chronology evidence                : PASS
infeasible anchor capacity rejection               : PASS with no partial output
sparse occupied/open position partition            : PASS
ranked unique placement variants                   : PASS
canonical tuples, frozen models and hashes         : PASS
no interpolation, WCTD, SysEx or MIDI path         : PASS
```

## Target-environment gates still required

```text
[ ] compileall passes in the target repository
[ ] pip check passes in the target environment
[ ] V8-D targeted suite passes in the target repository
[ ] complete public suite passes
[ ] complete private suite passes with all four reference dumps mounted
[ ] pre-V8 gate remains 62/62 supported with zero debt
[ ] isolated PEP 517 wheel includes all V8-D modules
[ ] exact authorized file set and git diff --check pass
[ ] implementation commit SHA is recorded
[ ] twelve push and pull-request checks pass
[ ] repository is clean after the implementation commit
[ ] final closure evidence is committed in this report
```

## Acceptance assertions

- Every complete ordering is an exact permutation of the complete V8-C selection.
- Every complete placement assigns each ordered candidate exactly once to one unique position from 0 through 60.
- Assigned positions increase strictly with final order.
- Required chronology and required position locks are never silently violated.
- Preference constraints are satisfied, violated, or marked not applicable with explicit evidence.
- Exact search is independently verifiable through `evaluate_wavetable_order`.
- Large cases use deterministic topological greedy solving and canonical tie-breaks.
- Ordering exposes source fidelity, scan smoothness, harmonic diversity, Bass strength, and discontinuity avoidance.
- Sparse placements expose every open position for V8-E and do not synthesize filler waves.
- Inventories above 61 are first reduced by V8-C and then assigned to exactly 61 editable positions.
- Placement variants have unique candidate-position signatures and deterministic rank.
- Infeasible mandatory constraints produce blockers and no partial order, placement, or variant.
- No interpolation, WCTD materialization, SysEx generation, MIDI opening, or MIDI transmission path is introduced.

## Safety boundary

CODE V8-D performs immutable planning only. It generates no waveform samples, materializes no WCTD payload, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI, and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
