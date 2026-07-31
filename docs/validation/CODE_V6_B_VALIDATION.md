# CODE V6-B Validation — Segmentation and Attack Policy

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V6-B
Branch  : code-v6-cycle-engine
Version : 0.5.0 (unchanged until CODE V6-F)
```

## Delivered contract

CODE V6-B converts accepted CODE V4 transient/change evidence and the CODE V6-A
working-pitch plan into a deterministic, non-destructive source segmentation.

Public models and functions:

```text
SegmentKind
AttackPolicy
AttackDecision
SourceSegment
SegmentationAnalysis
segment_source
analyze_audio_source_segmentation
```

Canonical segment kinds:

```text
silence
attack
steady
transition
release
```

The analysis records complete source coverage, contiguous boundaries, local RMS,
activity, voiced ratio, spectral flux, onset strength, transient/change counts,
boundary reasons, classification reasons, and one SHA-256 per segment.

## Attack policy

```text
auto    keep only a bounded qualified attack followed by usable source material
keep    retain a detected attack explicitly
reject  exclude a detected attack from usable segment selection
```

`not_present` is reported when no qualified first-onset attack exists. Explicit
policies never invent an attack.

## Hash chain

```text
SignalAnalysis.analysis_sha256
WorkingPitchPlan.analysis_sha256
    └── SegmentationAnalysis.analysis_sha256
```

The segmentation object preserves sample rate, sample count, canonical sample hash,
working frequency, working period, repitch requirement, every segment hash, usable
segment indexes, and the primary sustain index.

## CLI

```powershell
W-MWXT-WAVETABLE-TOOL segment-audio `
  "D:\Audio\source.wav" `
  --pitch-policy auto `
  --attack-policy auto `
  --report "D:\Reports\source.segmentation.json"
```

## Safety boundary

CODE V6-B does not resample, rewrite, trim, normalize, or export audio. It does not
select cycles, reconstruct waves, quantize XT data, generate SysEx, transmit MIDI, or
execute any irreversible operation.

## Targeted validation

```text
Core segmentation tests : 48
CLI tests               : 5
Public API tests        : 5
Targeted total          : 58
```

## Acceptance gate

CODE V6-B passes when all targeted and full suites pass, two real-audio reports are
byte-identical, all source/plan/hash links validate, segment coverage is complete,
attack policy invariants hold, source audio is unchanged, and no generated report or
private audio enters Git.
