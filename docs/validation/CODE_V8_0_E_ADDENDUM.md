# CODE V8-0E Addendum - complete Auto Repair policies and actions

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0E
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0D / aa319b396c12845c914efb5d0e5f7555d9327eb8
Version : 0.7.0 (unchanged until CODE V8-G)
```

## Purpose

CODE V8-0E closes the three active Auto Repair requirements without mutating the accepted V5, V6, V7, or V8-0D serialized contracts. It introduces one deterministic repair subsystem that detects every required defect, resolves an explicit four-state policy, records every action, and preserves canonical before/candidate/selected evidence.

## Requirements assigned to this stage

```text
CDC-REP-001  detect every required Auto Repair defect
CDC-REP-002  AUTO, COMPARE, IGNORE, and PRESERVE policies
CDC-REP-003  canonical before/after comparison
```

## Additive architecture

```text
repair/models.py
repair/detectors.py
repair/actions.py
repair/policy.py
repair/engine.py
```

The public package surface exports the new immutable contracts and functions through `repair/__init__.py` and the package root. Historical component schemas remain unchanged.

## Canonical defect contract

The detector layer reports exactly 17 defects in canonical order:

```text
dc_offset
clipping
zero_crossing
loop_discontinuity
derivative_discontinuity
phase_inversion
polarity_inversion
start_end_mismatch
amplitude_inconsistency
cycle_length
pitch_estimate
parasitic_noise
fundamental_loss
spectral_jump
inter_wave_level_mismatch
redundant_wave
excessive_aliasing
```

Every finding records the measured score, threshold, detection state, severity, evidence, reason, and deterministic SHA-256. Context-dependent findings remain explicit when a reference wave, neighbor, expected pitch, target level, or aliasing estimate is unavailable.

## Four-state policy contract

Every defect resolves to exactly one policy:

```text
AUTO      apply a deterministic safe action when sufficient evidence exists
COMPARE   compute and retain a candidate without selecting it
IGNORE    retain the source and record that the finding was ignored
PRESERVE  retain the source and record intentional preservation
```

`RepairPolicySet` stores one default policy plus canonical per-defect overrides. The Experimental optimization profile may explicitly preserve bounded controlled defects, but no policy can permit NaN, infinity, normalized overflow, silent wrapping, or unreported clipping.

## Action contract

The action layer contains one canonical action kind for every defect. Actions are deterministic and report:

```text
input and output sample hashes
sample or metadata change state
resolved policy and action status
parameters and measured evidence
warnings and rationale
```

Actions that require unavailable context do not guess. They return `review_required` or a non-applicable result with an explicit explanation.

## Before, candidate, and selected comparison

`RepairComparison` preserves three branches:

```text
before     immutable input wave
candidate  accumulated COMPARE previews
selected   accumulated AUTO actions
```

Each branch stores complete deterministic wave metrics and detected-defect counts. This prevents a preview from being selected implicitly and prevents an AUTO action from being hidden inside the comparison branch.

## Engine and sequence operation

`auto_repair_wave` executes findings and policies in a deterministic dependency-aware order. Every canonical defect still receives one action record, including `not_required` states.

`auto_repair_wave_sequence` preserves source order, carries the selected repaired predecessor into the next context, keeps the original next wave as forward evidence, and supports exactly 61 waves. It records one indexed result per wave and a final aggregate hash.

## Explicit boundaries

```text
pre-V8 aggregate and zero required-debt gate        V8-0F
61-position selection, ordering, interpolation      V8
reports, preview audition, and complete project     V9/V10
non-destructive editor UI for policy changes         V11/V13
automatic MIDI or SysEx transmission                excluded here
```

CODE V8-0E provides serialized before/candidate/selected data for later reports and audition. It does not claim that the report, preview renderer, or editor UI is already implemented.

## Safety boundary

CODE V8-0E opens no MIDI port, transmits no SysEx, allocates no XT memory, and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
