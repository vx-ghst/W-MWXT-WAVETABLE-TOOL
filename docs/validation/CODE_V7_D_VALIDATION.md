# CODE V7-D — XT trajectory QC and deterministic audition

## Scope

CODE V7-D consumes the accepted CODE V7-C 61-slot trajectory and performs deterministic quality control without modifying any slot. It measures all 60 adjacent transitions and all 59 interior curvature points, audits neighborhoods around phase-changed anchors, and renders deterministic mathematical audition WAV files.

An optional CODE V7-B projection report enables a preserve-phase baseline comparison using the original V7-B anchor payloads and the exact V7-C slot allocation and interpolation fractions.

## Canonical invariants

- Input trajectory schema: CODE V7-C schema 1.
- Editable positions: exactly 61.
- Stored points per position: exactly 64.
- Logical reconstruction: exactly 128 reverse-negate points.
- Quantization range: -127 through +127.
- Forbidden value: -128.
- Adjacent duplicate slots: forbidden.
- Source wave order: unchanged.
- V7-C slot payloads: never modified.
- Hardware allocation: none.
- SysEx generation or transmission: none.

## Deterministic measurements

- 60 adjacent time-domain distances.
- 60 adjacent normalized spectral distances.
- 60 weighted combined distances.
- 59 time-domain curvature measurements.
- 59 spectral curvature measurements.
- Robust median/MAD thresholds with explicit absolute floors.
- Local transition audit around every phase-changed anchor.
- Optional comparison with the preserve-phase V7-B baseline.

## Deterministic previews

The stage writes mono PCM-16 WAV files with no timestamps or random metadata:

1. optimized continuous 61-slot sweep;
2. optimized stepped-slot audition;
3. preserve-phase baseline sweep when a matching V7-B report is supplied.

These files are mathematical previews. They do not emulate the exact Microwave XT oscillator interpolation, DAC, analogue output path, filters, envelopes, or modulation system.

## Status policy

- `pass`: no adjacent jump and no curvature point exceeds the configured deterministic robust threshold.
- `review`: one or more metrics exceed a threshold; manual report inspection and listening are required.
- malformed hashes, invalid XT payloads, wrong slot counts, duplicates, or mismatched V7-B/V7-C lineage are rejected as errors.

## Test evidence

The delivery includes tests for:

- all 61 slots and 60/59 measurement cardinalities;
- XT-native storage and reverse-negate validation;
- deterministic JSON, Markdown, and WAV bytes;
- baseline hash linkage;
- explicit `review` behavior;
- strict CLI exit code;
- public API exports;
- absence of SysEx and trajectory mutation boundaries.
