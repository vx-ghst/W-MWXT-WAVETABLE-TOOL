# CODE V8-D Addendum - ordering, placement, locks, chronology and variants

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-D
Branch  : code-v8-wavetable-builder
Base    : CODE V8-C / 4dd3eeb32a638eb45be96a41606aeb3bcd5f75b5
Version : 0.7.0 (unchanged until CODE V8-G)
```

## Purpose

CODE V8-D consumes one immutable `WavetableBuildRequest`, its linked `CodeV8BAnalysis`, and a complete `CodeV8CAnalysis`. It determines the final order of the selected keyframes, assigns those keyframes to the 61 editable XT positions, resolves required locks and chronology, and generates ranked deterministic placement variants. It does not generate transition waves, fill unoccupied positions, materialize WCTD, generate SysEx, open MIDI, or modify an instrument.

## Authoritative stage boundary

```text
V8-C  choose final structural and essential keyframes
V8-D  order, place, solve locks and chronology, generate variants
V8-E  interpolate transitions and adapt transition density
V8-F  Factory Style, WCTD materialization and hardware gates
```

A sparse V8-D placement is intentional when V8-C selected fewer than 61 keyframes. Every unoccupied editable position remains explicit input for V8-E.

## Requirements closed by this stage

```text
CDC-PLC-001  reorder selected waves when source chronology is not optimal
CDC-PLC-002  minimize adjacent perceptual and spectral gaps
CDC-PLC-003  preserve an explainable musical progression
CDC-PLC-004  satisfy required chronology and score chronology preferences
CDC-PLC-005  honor required position locks and report preference locks
CDC-PLC-006  generate and compare deterministic placement variants
CDC-PLC-007  expose the five-term weighted ordering compromise
```

V8-D also advances the 61-position plan requirements by assigning every selected keyframe to one unique editable position while preserving exact candidate identity and provenance.

## Additive architecture

```text
wavetable/ordering.py
wavetable/placement.py
wavetable/variants.py
```

The public `wavetable` package and package root re-export the complete V8-D surface. V8-A, V8-B, and V8-C schemas remain unchanged.

## Ordering contract

`order_wavetable_keyframes` consumes exactly the complete V8-C selected set. It cannot add, remove, replace, or duplicate a selected candidate.

The public ordering objective exposes five bounded terms:

```text
source fidelity
scan smoothness
harmonic diversity
Bass strength
avoidance of unintended discontinuities
```

`OrderingPolicy` records their explicit weights. Six deterministic strategies provide alternate weight profiles:

```text
balanced
source fidelity
scan smoothness
harmonic diversity
Bass strength
discontinuity avoidance
```

Small cases use exhaustive permutation search under explicit candidate and permutation limits. Larger cases use deterministic topological greedy ordering. `evaluate_wavetable_order` exposes the same scoring function so small-case optimality is independently verifiable.

## Chronology and ordering feasibility

Required chronology edges are hard constraints. Preference chronology edges are scored and reported but may be violated without rejecting a result. Required position locks constrain relative ordering before absolute placement: a candidate locked to an earlier position must appear before a candidate locked to a later position, and the keyframes between locked candidates must fit in the available position interval.

When no complete order can satisfy required chronology and lock capacity, ordering is rejected with blockers and no partial candidate order.

## Placement contract

`place_wavetable_ordering` assigns the ordered candidates to unique positions 0 through 60, displayed publicly as positions 1 through 61.

Required locks are hard anchors. Preference locks are accepted only when the complete order remains feasible; an infeasible preference is reported as violated and does not reject an otherwise valid placement. Preference locks may also be disabled explicitly by policy.

Five deterministic spacing biases are available:

```text
balanced
early concentrated
late concentrated
center concentrated
edge expanded
```

Every complete placement records:

```text
candidate ID and exact position
final-order and source-order indices
essential and forced state
required-lock and preference-lock state
structure class and evidence
occupied and open positions
lock and chronology outcomes
ordering, spacing, lock and chronology score terms
```

Position order always agrees with the final keyframe order. A complete placement contains one through 61 selected candidates. It never creates a transition candidate to occupy an open position.

## Variants

`build_wavetable_placement_variants` evaluates deterministic ordering-strategy and placement-bias combinations. Variants with identical candidate-position signatures are deduplicated. Feasible unique variants are ranked by placement objective, stable strategy/bias tie-breaks, and canonical hashes.

The request controls the desired variant count from 1 through 16. When fewer unique feasible variants exist, the result remains complete and includes an explicit warning. Every alternative records moved candidate IDs and its mean absolute position delta from the primary variant.

## Conflict and rejection behavior

V8-D reports, without hidden fallback:

```text
rejected V8-C input
missing required selected candidate
required chronology conflict
required lock/order conflict
insufficient capacity between locked anchors
more selected candidates than editable positions
no complete ordering and placement variant
```

Rejected ordering, placement, and aggregate results expose blockers and no partial order, assignment, or variant.

## Determinism

All public models are frozen and schema-versioned. Collections are canonical tuples, JSON keys are sorted, hashes are lowercase SHA-256 values, scores are finite and bounded, and every tie uses stable source index, candidate ID, strategy, bias, and content-hash ordering.

## Explicitly deferred scope

```text
transition-wave generation and interpolation         V8-E
adaptive density across open positions               V8-E
complete 61-slot waveform materialization            V8-E/V8-F
Factory Style and WCTD serialization                  V8-F
positions 60-63 hardware and read-back gates          V8-F
complete CODE V8 integration and release              V8-G
SysEx/MIDI execution                                  later controlled stages
```

## Safety boundary

CODE V8-D performs deterministic in-memory ordering and placement planning only. It generates no waveform samples, writes no WCTD, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI, and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
