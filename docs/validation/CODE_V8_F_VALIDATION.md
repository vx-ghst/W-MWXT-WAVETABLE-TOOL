# CODE V8-F Validation - Factory Style, WCTD models and hardware gates

## Stage identity

Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-F
Branch  : code-v8-wavetable-builder
Base    : CODE V8-E / 1f3824d82140bbdd45c4065e211b3529cd4d99f7
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY - PRIVATE SUITE, REMOTE CI AND HARDWARE EVIDENCE PENDING

## Implemented contracts

- optional request-controlled Factory Style;
- byte-exact preservation of protected keyframes;
- bounded transition-only shaping;
- continuity revalidation and regression gate;
- canonical 64-entry WCTD reference model;
- 61 user entries and three exact fixed-tail entries;
- explicit unresolved allocation and binary-ready states;
- deterministic 128-byte reference payload and SHA-256;
- six ordered hardware-gate requirements;
- immutable hardware evidence and exact comparison;
- blocked, pending, pass and fail gate results;
- ready, accepted, failed and rejected aggregate states;
- no hidden hardware acceptance fallback;
- canonical JSON and deterministic hashes.

## Compatibility contract

The following accepted contracts remain unchanged:

- all V8-A candidate, request, policy, slot, build and fixed-tail schemas;
- all V8-B metrics, usefulness and deduplication schemas;
- all V8-C selection schemas;
- all V8-D ordering, placement and variant schemas;
- all V8-E interpolation, transition-map and continuity schemas;
- all V8-0 and V1-V7 public schemas;
- version 0.7.0.

## Local design validation

compileall                                      : PASS on V8-F compatibility bundle
V8-F targeted suite                            : 98 passed
Factory Style inactive exact pass-through      : PASS
Factory Style request-controlled activation    : PASS
protected keyframes byte-identical             : PASS
transition-only bounded changes                : PASS
safe generated range -127..127                 : PASS
continuity recalculation                       : PASS
continuity failure and regression rejection    : PASS
64 canonical WCTD entries                      : PASS
61 user plus three fixed-tail entries          : PASS
unresolved and resolved allocation states      : PASS
128-byte reference payload and SHA-256         : PASS
six canonical hardware requirements            : PASS
positions 60 through 63 gate                   : PASS
slow and fast scan gates                       : PASS
complete read-back hash gate                   : PASS
mismatched references force failure            : PASS
no evidence never claims acceptance            : PASS
canonical frozen models and hashes             : PASS
no SysEx or MIDI execution path                : PASS

## Target-environment gates still required

[ ] compileall passes in the target repository
[ ] pip check passes in the target environment
[ ] V8-F targeted suite passes in the target repository
[ ] complete public suite passes
[ ] complete private suite passes with all four reference dumps mounted
[ ] pre-V8 gate remains 62/62 supported with zero debt
[ ] isolated PEP 517 wheel includes all V8-F modules
[ ] exact authorized file set and git diff --check pass
[ ] implementation commit SHA is recorded
[ ] twelve push and pull-request checks pass
[ ] repository is clean after the implementation commit
[ ] real hardware evidence is supplied for all six gates
[ ] complete 64-reference read-back matches the canonical model
[ ] final closure evidence is committed in this report

## Software acceptance assertions

- Factory Style is activated only by both request and policy.
- Factory Style inactive mode preserves the V8-E build hash exactly.
- Factory Style never changes protected or non-transition slots.
- Every changed sample stays within the configured integer delta.
- Every generated sample stays in -127..127.
- Every styled variant has a linked 60-edge continuity report.
- A failed continuity report is never retained as a complete variant.
- Every WCTD model has exactly 64 canonical reference entries.
- Positions 0 through 60 link to the exact build slots.
- Positions 61 through 63 preserve FixedTailContract exactly.
- Missing user allocation remains explicit and never becomes binary ready.
- A resolved allocation has exactly 61 unique explicit references.
- Hardware requirements have deterministic IDs and canonical order.
- A binary-unready model blocks every hardware gate.
- A binary-ready model without evidence leaves every gate pending.
- Hardware acceptance requires all six gates to pass.
- Reference or read-back mismatches force a failed gate even when evidence says passed.
- No complete WCTD dump, SysEx generation, MIDI opening or MIDI transmission path is introduced.

## Hardware acceptance gate

Software validation alone cannot close the hardware-dependent part of CODE V8-F.

The following real evidence remains mandatory:

1. two known references match the planned model;
2. one or more intermediate positions match;
3. internal positions 60 through 63 match;
4. controlled slow scan passes;
5. controlled fast scan passes;
6. complete 64-reference read-back matches the canonical payload hash.

Until these six gates pass, the correct aggregate status is ready_for_hardware. The stage must not be reported as hardware_accepted.

## Safety boundary

CODE V8-F generates only in-memory models and deterministic reports. It serializes no complete instrument dump, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI, and modifies no instrument state. Private dumps, captures and evidence files remain outside Git.
