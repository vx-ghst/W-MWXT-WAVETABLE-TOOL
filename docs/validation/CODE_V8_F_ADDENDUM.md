# CODE V8-F Addendum - Factory Style, WCTD models and hardware gates

## Stage identity

Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-F
Branch  : code-v8-wavetable-builder
Base    : CODE V8-E / 1f3824d82140bbdd45c4065e211b3529cd4d99f7
Version : 0.7.0 (unchanged until CODE V8-G)

## Purpose

CODE V8-F consumes one immutable WavetableBuildRequest and one complete CODE V8-E analysis. It may apply a bounded optional Factory Style policy, materialize canonical 64-entry WCTD reference models, and evaluate six explicit hardware gates.

This stage does not serialize a complete instrument dump, allocate XT memory, generate SysEx, open MIDI, transmit MIDI, or claim hardware acceptance without supplied evidence.

## Authoritative stage boundary

V8-E  complete 61-slot waveform plans and continuity evidence
V8-F  Factory Style, WCTD reference models and hardware evidence gates
V8-G  final integration, compliance audit, documentation and release gate

## Requirements advanced by this stage

CDC-FAC-001  optional deterministic Factory Style policy
CDC-FAC-002  byte-exact protection of structural and locked keyframes
CDC-FAC-003  bounded transition-only shaping with continuity revalidation
CDC-WCTD-001 canonical 64-entry reference model
CDC-WCTD-002 61 user references plus three preserved fixed references
CDC-WCTD-003 explicit unresolved user allocation state
CDC-HWG-001 known-reference-pair hardware gate
CDC-HWG-002 intermediate-position hardware gate
CDC-HWG-003 positions 60 through 63 hardware gate
CDC-HWG-004 controlled slow-scan hardware gate
CDC-HWG-005 controlled fast-scan hardware gate
CDC-HWG-006 complete 64-reference read-back gate

## Additive architecture

wavetable/factory_style.py
wavetable/wctd.py
wavetable/hardware_gate.py

The accepted V8-A through V8-E schemas remain unchanged. The public wavetable package and package root re-export the complete V8-F surface.

## Factory Style contract

Factory Style is an explicit deterministic engineering profile. It is not represented as a reverse-engineered or bit-exact reproduction of Waldorf factory algorithms.

Activation requires both:

- FactoryStylePolicy.enabled is true;
- WavetableBuildRequest.policy.factory_style is true.

When either condition is false, the accepted V8-E build and continuity report are preserved exactly.

When active, Factory Style may modify only mutable transition slots. The following slots remain byte-identical:

- required or preference locked slots;
- structural slots;
- essential slots;
- breakpoint slots;
- extreme slots;
- stable keyframes;
- explicit edge holds and other non-transition slots.

The policy exposes bounded circular smoothing, adjacent-slot blending, a maximum integer sample delta, continuity regression tolerance, and an optional non-worsening continuity gate.

Every changed slot retains source-candidate links and receives generated-variant provenance. Generated samples remain inside -127..127 and generated -128 remains impossible.

Every styled build receives a fresh 60-edge continuity report. A mandatory continuity failure rejects the variant. A configured non-worsening gate rejects changes that exceed the admitted continuity regression tolerance.

## Factory Style evidence

Every one of the 61 positions receives one immutable decision record containing:

- original and styled slot hashes;
- action;
- protected state;
- changed state;
- maximum integer sample delta;
- evidence and reason.

Canonical actions are:

- preserve protected;
- preserve keyframe;
- preserve edge hold;
- preserve transition;
- smooth transition.

## WCTD reference model

V8-F materializes a canonical reference model with exactly 64 entries:

- positions 0 through 60: user positions from the complete V8-E or Factory Style build;
- positions 61 through 63: the exact three fixed-tail references from FixedTailContract.

Each user entry links to the exact source slot hash and its source candidate IDs. Each fixed entry links to the accepted fixed-tail contract.

## Allocation boundary

V8-F does not invent XT User Wave allocation numbers.

Without an explicit external allocation, each user entry carries the existing unresolved marker 0xFFFF and the model is binary_ready=false. This marker is logical planning evidence only. It is not claimed as an instrument-ready WCTD payload.

An explicit allocation must contain exactly 61 unique uint16 references. It may not use 0xFFFF. Once all user references are supplied, binary_ready becomes true.

The three fixed references are always copied byte-for-byte from FixedTailContract and cannot be overridden by the allocation map.

## Reference payload

The model exposes the canonical 128-byte big-endian sequence of 64 uint16 reference words and its SHA-256. This sequence supports deterministic comparison and exact read-back evidence.

It is not a complete WCTD dump, SysEx message, memory write command, or proof of instrument acceptance.

## Hardware gates

V8-F defines exactly six ordered hardware requirements:

1. known reference pair;
2. intermediate positions;
3. positions 60 through 63;
4. controlled slow scan;
5. controlled fast scan;
6. complete 64-reference read-back.

The final-user/fixed-tail gate covers internal positions 60, 61, 62 and 63, corresponding to displayed positions 61 through 64.

The read-back gate covers all 64 positions and requires the observed reference-payload SHA-256 to equal the canonical model hash.

## Gate states

Each hardware gate is one of:

- blocked: the model is not binary ready;
- pending: the model is ready but no evidence was supplied;
- pass: evidence and model comparison both pass;
- fail: supplied evidence fails or contradicts the model.

The aggregate hardware plan is pending, accepted, or failed. CODE V8-F is hardware_accepted only when all six gates pass with explicit evidence.

A user assertion that a test passed never overrides mismatched references, missing required observations, or a read-back hash mismatch.

## Hardware evidence contract

Evidence is immutable and records:

- gate ID;
- source artifact SHA-256;
- explicit pass/fail observation;
- observed positions;
- observed uint16 references;
- optional full reference-payload SHA-256;
- evidence statements and reason.

Private dumps, captures and local evidence files remain outside Git. Only normalized hashes and controlled observations may enter the public evidence model.

## Aggregate result

build_code_v8f returns one CodeV8FAnalysis containing:

- the linked request and V8-E hashes;
- Factory Style analysis;
- WCTD materialization set;
- hardware gate plan;
- warnings, blockers and deterministic SHA-256.

Canonical statuses are:

- ready_for_hardware;
- hardware_accepted;
- hardware_failed;
- rejected.

A rejected prerequisite produces no partial acceptance claim. A complete logical model without hardware evidence remains ready_for_hardware, not accepted.

## Determinism

All public V8-F models are frozen and schema-versioned. Collections are canonical tuples, JSON keys are sorted, hashes are lowercase SHA-256 values, user/fixed positions are canonical, and all ranking and comparison decisions have stable tie-breaks.

## Explicitly deferred scope

complete instrument WCTD serialization        V8-G or later controlled packaging
SysEx generation and destination addressing  later controlled stage
MIDI port opening and transmission            later controlled stage
final compliance audit and version release   V8-G
hardware acceptance without actual evidence  forbidden
bit-exact Waldorf Factory algorithm claim     forbidden

## Safety boundary

CODE V8-F performs deterministic in-memory shaping, reference-model construction and evidence evaluation only. It writes no instrument file, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI, and modifies no instrument state.
