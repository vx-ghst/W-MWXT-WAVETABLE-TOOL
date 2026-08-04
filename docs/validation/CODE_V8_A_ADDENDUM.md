# CODE V8-A Addendum - generic wavetable build contracts

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-A
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0F / 51c5d2c5a3672b9ff1d6b7db5aafaded4acbf41c
Version : 0.7.0 (unchanged until CODE V8-G)
```

## Purpose

CODE V8-A opens the generic 61-position builder after the executable V8-0 gate proved `62/62 supported, debt=0`. It defines immutable, schema-versioned input, candidate, constraint, slot, build, and variant-set contracts. It does not yet select structural waves, order candidates, interpolate transitions, materialize WCTD, allocate XT memory, build SysEx, or transmit MIDI.

## Controlled CODE V8 order

```text
CODE V8-A  generic WavetableBuild models and contracts
CODE V8-B  usefulness, structure, breakpoints and deduplication
CODE V8-C  structural/keyframe selection for positions 1-61
CODE V8-D  ordering, placement, locks, chronology and variants
CODE V8-E  interpolation families and adaptive transition density
CODE V8-F  Factory Style, WCTD materialization and hardware gates
CODE V8-G  integration, compliance closure, documentation and release gate
```

Later stages consume the V8-A contracts. They must not bypass or silently reinterpret them.

## CODE V8 requirement domain

The generic builder domain contains 28 active requirements:

```text
CDC-W61-001 through CDC-W61-007
CDC-USE-001 through CDC-USE-003
CDC-PLC-001 through CDC-PLC-007
CDC-TRN-001 through CDC-TRN-007
CDC-PROF-003
CDC-SYX-002
CDC-SYX-005
CDC-HW-002 structural V8 portion
```

CODE V8-A establishes the shared contract surface for these requirements. It does not claim that the algorithms or hardware gates assigned to V8-B through V8-F are already complete.

## Additive architecture

```text
wavetable/models.py
wavetable/contracts.py
wavetable/__init__.py
```

The public package root re-exports the V8-A surface. Historical V1-V7 and V8-0 schemas remain unchanged.

## Candidate contract

`WavetableCandidate` stores one XT-safe 64-sample candidate and its provenance:

```text
candidate identity and source-artifact SHA-256
real, reconstructed, repaired, variant or interpolated origin
generation method with strict origin/method compatibility
safe generated range -127..127
64-point stored and 128-point reconstructed hashes
quality, usefulness, stability and harmonic-richness scores
brightness, Bass power, source fidelity and XT compatibility
perceptual novelty, source time/index, evidence and reason
structural eligibility
```

Candidates may be duplicate in wave content because duplicate detection belongs to V8-B. Candidate IDs must remain unique.

## Fixed-tail contract

`FixedTailContract` preserves exactly three explicit baseline references for WCTD positions 61, 62 and 63. It stores the source WCTD SHA-256 and never invents fixed references.

V8-A distinguishes:

```text
61 editable user positions: internal positions 0-60, display positions 1-61
3 fixed-tail positions: internal positions 61-63
64 total WCTD positions
```

## Request and constraint contract

`WavetableBuildRequest` links one ready `CodeV8PreflightAnalysis` to:

```text
one canonical candidate inventory
one fixed-tail contract
one explicit build policy
optional required or preferred position locks
optional required or preferred chronology constraints
selected conversion mode and optimization profile
source sample identity and preflight SHA-256
```

A rejected preflight has no hidden fallback. Candidate count must match the repaired-wave count recorded by V8-0F. Required chronology must be acyclic. Required locks must not contradict required chronology. Preference conflicts remain serializable for later variant comparison.

## Policy contract

The build policy always requests exactly 61 editable positions and records:

```text
variant count from 1 to 16
linear, smoothstep, exponential, logarithmic or adaptive progression
allowed interpolation families
mixed-provenance policy
chronology policy
intentional-break policy
Factory Style request
```

The policy declares future processing choices without executing them in V8-A.

## Slot and build contracts

`WavetableSlot` defines the final per-position metadata required by later stages:

```text
position and display position
stored XT samples and deterministic hashes
role, origin and generation method
quality/usefulness/stability/richness/brightness/Bass metrics
source candidate IDs and source time
locked, structural, transition and redundant states
evidence and reason
```

A complete `WavetableBuild` requires exactly 61 slots in canonical order, at least one structural position and at least one essential position. A rejected build exposes explicit blockers and no partial slot list. `WavetableBuildSet` carries deterministic variants and an explicit primary variant.

## Explicitly deferred scope

```text
usefulness, structural and duplicate analysis        V8-B
keyframe selection and essential-position choice     V8-C
ordering, placement, locks and variant solving       V8-D
waveform/spectral/harmonic/perceptual interpolation  V8-E
Factory Style and WCTD reference materialization     V8-F
hardware interpolation and positions 60-63 gates     V8-F
complete CODE V8 closure and release audit           V8-G
reports and export bundle                             V9
calibrated preview and auditory simulation            V10
```

## Safety boundary

CODE V8-A builds no wavetable, materializes no WCTD payload, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI, and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
