# CODE V4-A Validation

## Scope

CODE V4-A establishes the deterministic time-domain analysis foundation of CODE V4.

Implemented:

- strict finite mono-signal validation;
- deterministic frame placement without zero padding;
- peak, RMS, dBFS, crest factor, and DC-offset measurements;
- positive/negative peak asymmetry;
- clipping counts and ratios;
- explicit near-clip and repeated-flat-extreme measurements;
- documented saturation-likelihood heuristic;
- frame RMS and frame peak envelopes;
- amplitude stability;
- active-frame ratio;
- envelope dynamic range;
- stable sample and analysis SHA-256 fingerprints;
- immutable serializable analysis models;
- `signal-analyze` CLI JSON output and report writing.

Deferred to later CODE V4 gates:

- pitch and musical-note estimation;
- periodicity and quasi-periodicity;
- phase stability and discontinuity;
- pitch-motion classification;
- noise and SNR estimation;
- transient and change-point detection;
- final aggregate `SignalAnalysis` contract;
- release version `0.4.0`.

## Deterministic framing

For signals longer than one frame:

1. frames start at sample zero;
2. regular starts advance by the configured hop size;
3. the final full frame is aligned to the last source sample when required;
4. no frame is zero-padded;
5. short signals use one partial frame.

The report records every frame start and center time.

## Level definitions

- `peak_absolute`: maximum absolute sample value;
- `rms`: square root of the mean squared sample value;
- `peak_dbfs` and `rms_dbfs`: `20 * log10(value)` when defined;
- `crest_factor`: `peak_absolute / rms` when RMS is non-zero;
- `dc_offset`: arithmetic mean;
- `clipped_sample_ratio`: samples at or above the configured clipping threshold;
- `peak_asymmetry`: normalized difference between positive and negative peak magnitude.

Undefined logarithmic or ratio metrics use JSON `null`, never NaN or infinity.

## Saturation estimate

`saturation_likelihood` is an explainable heuristic, not a claim of physical certainty.
It is driven by:

- threshold-clipped samples;
- repeated near-extreme samples whose adjacent slope is effectively zero.

A naturally high-amplitude sine without a flat top is not classified as probable saturation merely because it approaches full scale.

## Envelope definitions

The envelope reports per-frame RMS and peak values, then derives:

- mean and standard deviation of frame RMS;
- coefficient of variation when defined;
- `amplitude_stability = 1 / (1 + coefficient_of_variation)`;
- active-frame count and ratio;
- active-envelope dynamic range in decibels when defined.

Silence remains finite and serializable. Its coefficient of variation and logarithmic dynamic range are `null`.

## Automated validation

Generated CODE V4-A tests:

```text
37 passed
0 failed
```

Coverage includes:

- silence;
- exact sine levels;
- DC offset;
- clipping;
- flat limiting;
- near-full-scale unclipped sine;
- peak asymmetry;
- invalid shapes and non-finite samples;
- deterministic end-aligned framing;
- short signals;
- stable and two-level envelopes;
- deterministic hashes;
- source preservation;
- JSON finite-number policy;
- CLI output and report writing;
- public API availability.

## Expected repository totals

Based on the accepted CODE V3 release:

```text
Targeted CODE V4-A : 37 passed
Public full suite   : 244 passed, 4 skipped
Private full suite  : 248 passed
```

The release version remains `0.3.0` during this intermediate gate. CODE V4 is finalized as `0.4.0` only after all CODE V4 modules and the final `SignalAnalysis` contract are accepted.

CODE V4-A does not generate SysEx and performs no MIDI transmission.
