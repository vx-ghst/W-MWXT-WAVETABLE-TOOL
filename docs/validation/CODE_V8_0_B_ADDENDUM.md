# CODE V8-0B Addendum - Import, signal, behavior, and region architecture

**Project:** W-MWXT-WAVETABLE-TOOL
**Branch:** `code-v8-wavetable-builder`
**Baseline:** CODE V8-0A closure / `820927bfdd69dbac55ae3fdf9a90f0d7c716f50c`
**Version:** `0.7.0` until CODE V8-G
**Status:** approved architectural addendum before the CODE V8-0B implementation commit

## 1. Reason for the addendum

The normative CODE V8 file list authorizes the new mono-scoring, rapid-FM, saturation, complexity, beating, and behavioral-decision modules. During the atomic pre-implementation audit, four additional boundaries proved necessary:

1. the eight required region classes cannot be added to the historical V6 `SegmentKind` enum without changing the accepted V6 segmentation schema and hashes;
2. the V8-0B signal extension requires its own integration test and immutable aggregate contract rather than mutating the accepted CODE V4 `SignalAnalysis` schema;
3. scored mono decisions add structured fields to `MonoConversionReport`, so minimal-project parsing must accept both the historical seven-field representation and the new extended representation;
4. a pathological sparse-transient corpus exposed a negative-local-maximum edge case in the existing autocorrelation pitch selector. The fix preserves the positive-score selection rule and prevents an `IndexError` when every local autocorrelation maximum is non-positive.

The addendum therefore isolates V8-0B additions and preserves the accepted V1-V7 aggregate contracts.

## 2. Additional authorized files

```text
CREATE src/w_mwxt_wavetable_tool/analysis/regions.py
CREATE tests/test_analysis_regions.py
CREATE tests/test_analysis_signal_extensions.py
CREATE docs/validation/CODE_V8_0_B_ADDENDUM.md
```

## 3. Additional authorized modifications

```text
MODIFY src/w_mwxt_wavetable_tool/audio/__init__.py
MODIFY src/w_mwxt_wavetable_tool/audio/importers.py
MODIFY src/w_mwxt_wavetable_tool/analysis/periodicity.py
MODIFY src/w_mwxt_wavetable_tool/project/minimal_schema.py
```

The globally authorized documentation files remain available to V8-0B:

```text
MODIFY README.md
MODIFY CHANGELOG.md
MODIFY docs/roadmap/W-MWXT-WAVETABLE-TOOL_ROADMAP_AND_TRACEABILITY_MATRIX.md
MODIFY docs/specification/W-MWXT-WAVETABLE-TOOL_SPECIFICATION.md
```

## 4. Preserved contracts

V8-0B does not change:

- `SignalAnalysis` schema version 1;
- the historical six-value `SourceClass` contract used by CODE V5;
- `SegmentationAnalysis` schema version 1 or the historical `SegmentKind` values;
- any frozen V7 XT module;
- any historical V1-V7 validation or release report;
- the CODE V8-0A baseline compliance registry, which continues to describe the audited `v0.7.0` baseline.

New capabilities are layered through:

```text
SignalAnalysis -> SignalExtensionAnalysis
SegmentationAnalysis -> RegionInterestAnalysis -> RegionSlotAllocation
SignalAnalysis + SignalExtensionAnalysis -> BehaviorClassification
```

## 5. Minimal-project compatibility

`MonoConversionReport.to_dict()` now records:

```text
selected_candidate
candidate_periodicity_scores
periodicity_margin
```

The project parser accepts exactly one of two representations:

```text
legacy seven-field mono report
extended ten-field mono report
```

Partial mixtures and unknown fields remain rejected. Existing project archives therefore remain readable, while new scored decisions retain their complete deterministic evidence.

## 6. Region allocation boundary

`RegionSlotAllocation` is an advisory interest-density contract. It does not build a wavetable, choose final waves, write synth memory, construct SysEx, or transmit MIDI. Final 61-position selection and placement remain assigned to CODE V8-A through V8-E.

## 7. Safety boundary

No V8-0B module opens a MIDI port, transmits SysEx, writes the instrument, or embeds private dumps or audio evidence in Git.
