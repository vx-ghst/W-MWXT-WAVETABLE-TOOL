# CODE V8-B Addendum - usefulness, structure, breakpoints and deduplication

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-B
Branch  : code-v8-wavetable-builder
Base    : CODE V8-A / ef7827060b474d3241d20df752b57bf0e14fb436
Version : 0.7.0 (unchanged until CODE V8-G)
```

## Purpose

CODE V8-B consumes one validated `WavetableBuildRequest` from V8-A and measures the candidate inventory before any final keyframe selection. It identifies useful structure, stable regions, transition intervals, breakpoint candidates and acoustic redundancy. It does not delete candidates, select the final keyframes, assign any of the 61 positions, order the final table or interpolate transitions.

## Requirements closed by this stage

```text
CDC-USE-001  determine the number of distinct waves
CDC-USE-002  detect redundancy, stable regions, breakpoints and structural waves
CDC-USE-003  identify transitions
```

The analysis also supplies deterministic evidence to V8-C for the structural/keyframe selection stage. It does not claim the V9 essential-slot report required by CDC-USE-004.

## Additive architecture

```text
wavetable/metrics.py
wavetable/usefulness.py
wavetable/deduplication.py
```

The public `wavetable` package and package root re-export the complete V8-B surface. V8-A models and contracts remain unchanged.

## Wave-shape metrics

`WaveShapeMetrics` derives deterministic engineering descriptors from each XT-safe 64-sample candidate after the documented 128-point reverse-negate reconstruction:

```text
RMS, peak and crest factor
DC offset and zero-crossing rate
mean/max slope and mean curvature
spectral centroid and spread
low, mid and high spectral ratios
harmonic concentration and spectral flatness
polarity balance and composite complexity
```

The implementation is pure Python and deterministic. It uses a fixed 32-bin DFT and quantizes serialized floating-point values to twelve decimal places.

## Pairwise distance

`WavePairDistance` records:

```text
direct waveform distance
inverted-polarity waveform distance
maximum direct sample distance
signed and absolute correlation
spectral distance
feature distance
combined perceptual-distance proxy
exact-match flag
polarity-equivalent flag
```

The perceptual-distance value is an explicit deterministic engineering proxy. It is not represented as a calibrated listening result or a bit-exact model of the XT DSP.

## Structure and usefulness analysis

`analyze_candidate_structure` first creates one deterministic source order from source time, source index, inventory order and candidate ID. It then measures every adjacent interval and labels it as:

```text
stable
transition - moderate or strong
breakpoint
```

Breakpoint evidence can include waveform, spectral, level, brightness, Bass, polarity or composite changes.

Each candidate receives:

```text
source and inventory indices
wave-shape metrics
left/right interval hashes
neighborhood novelty
structural and effective-usefulness scores
stable, transition, breakpoint, structural, extreme or ineligible class
feature-extreme evidence
explicit reason and deterministic hash
```

Endpoints, breakpoints, significant feature extremes and candidates above the structural threshold are exposed as structural candidates. V8-C remains solely responsible for choosing the final keyframes.

## Deduplication analysis

`analyze_candidate_deduplication` classifies every relevant pair as:

```text
exact duplicate
polarity-equivalent duplicate
near duplicate
distinct
```

Duplicate groups use deterministic complete-link clustering. A candidate joins a group only when it satisfies the duplicate threshold against every existing member. This prevents transitive near-duplicate chains from merging acoustically distinct endpoints.

The analysis reports:

```text
distinct-wave count
pair evidence and duplicate kind
group representative
redundant members
required-constraint-protected members
members that V8-C may omit
warnings when distinct count exceeds 61
```

Required position locks and required chronology constraints protect their candidates. Protection affects the deterministic representative and omission eligibility, but V8-B never removes or rewrites a candidate.

## Aggregate contract

`CodeV8BAnalysis` links the request, structure analysis and deduplication analysis with canonical JSON and a final SHA-256. Its boundaries explicitly state that V8-B does not:

```text
select final keyframes
build the 61-position table
order the final table
interpolate transitions
materialize WCTD
generate SysEx
open or transmit MIDI
```

## Determinism

All public models are frozen and schema-versioned. Collections are canonical tuples, hashes are lowercase SHA-256 values, JSON keys are sorted, NaN and infinity are rejected, thresholds are explicit and source ordering is deterministic.

## Explicitly deferred scope

```text
final structural/keyframe selection and essential choices   V8-C
ordering, placement, locks and variant solving              V8-D
waveform/spectral/harmonic/perceptual interpolation         V8-E
Factory Style and WCTD materialization                      V8-F
hardware interpolation and positions 60-63 gates            V8-F
complete CODE V8 closure                                    V8-G
essential-slot report                                       V9
calibrated auditory simulation                              V10
```

## Safety boundary

CODE V8-B performs immutable in-memory analysis only. It builds no wavetable, writes no WCTD, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path or private evidence file.
