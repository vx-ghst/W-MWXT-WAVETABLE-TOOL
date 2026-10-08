# CODE V8-C Addendum - structural and essential keyframe selection

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-C
Branch  : code-v8-wavetable-builder
Base    : CODE V8-B / a973d41d2e46448bc0ec284fac3969bccb99cbec
Version : 0.7.0 (unchanged until CODE V8-G)
```

## Purpose

CODE V8-C consumes one immutable `WavetableBuildRequest` from V8-A and its linked `CodeV8BAnalysis`. It selects the final structural and essential keyframes that later stages may place into the 61 editable positions. It does not assign positions, solve final ordering, create variants, interpolate transitions, materialize WCTD, generate SysEx or open MIDI.

## Authoritative stage boundary

The current public roadmap assigns:

```text
V8-C  final structural and essential keyframe selection
V8-D  ordering, placement, locks, chronology solving and variants
V8-E  interpolation families and adaptive transition density
V8-F  Factory Style, WCTD materialization and hardware gates
```

V8-C therefore serializes selected candidate IDs in canonical V8-B source order only. That serialization order is evidence, not a final Wavetable order or slot allocation.

## Requirements advanced by this stage

```text
CDC-W61-001  prepare no more than 61 final real/reconstructed keyframes
CDC-W61-002  preserve explicit mixed candidate provenance
CDC-W61-007  retain complete per-wave metadata through selection
CDC-USE-001  consume the V8-B distinct-wave count
CDC-USE-002  consume stable, breakpoint, structural and redundancy evidence
CDC-USE-003  preserve transition evidence for later placement/interpolation
```

The user-facing essential-slot report remains assigned to V9. V8-C exposes the selected and essential candidate IDs required to build that report later.

## Additive architecture

```text
wavetable/selection.py
```

The public `wavetable` package and package root re-export the complete V8-C surface. V8-A and V8-B schemas remain unchanged.

## Selection policy

`KeyframeSelectionPolicy` is schema-versioned and records:

```text
maximum keyframes, never above 61
optional requested keyframe count
source-endpoint preservation policy
exact-search candidate and combination limits
explicit utility, diversity, temporal, structural and group weights
```

All objective weights are finite, bounded and must sum to one.

## Candidate pool

The V8-C pool contains:

```text
one deterministic representative per complete-link V8-B group
all redundant candidates protected by required constraints
no unprotected candidate marked removable by V8-B
```

Required position-lock candidates and both endpoints of every required chronology edge are forced into the final set. Source endpoints are represented by their complete-link group representatives when endpoint preservation is enabled.

## Capacity behavior

```text
1 candidate             select 1
2 candidates            select 2
8 candidates            select 8
61 candidates           select 61
more than 61 candidates select exactly 61 when feasible
```

When the non-removable pool is smaller than an explicit requested count, all available candidates are selected and the reduction is reported. When required candidates exceed the 61-keyframe capacity, V8-C returns an explicit rejected result with blockers and no partial selection.

## Deterministic objective

Every candidate receives a bounded utility score derived from linked V8-A and V8-B evidence:

```text
effective usefulness and structural score
quality, source fidelity and XT compatibility
perceptual novelty and stability
harmonic richness and Bass power
breakpoint, extreme and structural class priority
```

Subset evaluation combines:

```text
utility
pairwise waveform/spectral engineering diversity
temporal source coverage
structural coverage
complete-link group coverage
```

Small feasible cases use exhaustive subset search within explicit limits. Larger cases use deterministic greedy maximization with canonical source-index and candidate-ID tie-breaks. `evaluate_keyframe_subset` exposes the same objective so small-case optimality is independently testable.

## Selection evidence

Every input candidate receives exactly one `CandidateSelectionDecision` containing:

```text
selected or omitted state
essential and forced state
source endpoint and group representative state
protected and removable state
V8-B structure class
utility and structural-priority scores
selected source-order rank when selected
evidence kinds, evidence text and reason
```

Omission is distinguished between complete-link redundancy and capacity limitation.

## Output contracts

`WavetableKeyframeSelection` records:

```text
complete or rejected status
request and V8-B hashes
policy and effective target
selected, essential, forced and omitted candidate IDs
one decision per input candidate
exact-search or greedy evidence
objective component scores
warnings, blockers and deterministic SHA-256
```

`CodeV8CAnalysis` links that selection to the V8-A request and V8-B analysis. Complete selections contain one through 61 keyframes. Rejected selections expose blockers and no partial keyframe list.

## Determinism

All public models are frozen and schema-versioned. Collections are canonical tuples, serialized JSON keys are sorted, hashes are lowercase SHA-256 values, NaN and infinity are rejected, and ties use stable source-index and candidate-ID ordering.

## Explicitly deferred scope

```text
final ordering and 61-position placement       V8-D
position-lock collision solving                V8-D
chronology solving and placement variants      V8-D
waveform/spectral/harmonic interpolation       V8-E
adaptive transition density                    V8-E
Factory Style and WCTD materialization         V8-F
hardware interpolation and positions 60-63     V8-F
complete CODE V8 closure                       V8-G
essential-slot user report                     V9
calibrated auditory simulation                 V10
```

## Safety boundary

CODE V8-C performs immutable in-memory selection only. It builds no 61-slot table, writes no WCTD, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path or private evidence file.
