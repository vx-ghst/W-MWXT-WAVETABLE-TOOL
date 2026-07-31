# CODE V4-B Validation

## Scope

CODE V4-B adds deterministic fundamental-pitch and periodicity analysis on top
of the accepted CODE V4-A time-domain foundation.

Implemented:

- frame-wise normalized linear autocorrelation using zero-padded FFTs;
- explicit minimum and maximum frequency bounds;
- deterministic local-peak selection and parabolic lag refinement;
- active, voiced, and total frame ratios;
- robust confidence-weighted median pitch;
- A4-reference-aware MIDI note, scientific note name, and cents deviation;
- robust pitch spread in cents and pitch-stability score;
- periodicity and quasi-periodicity scores;
- explainable classes: silent, aperiodic, intermittent periodic, stable periodic,
  quasi-periodic, and unstable periodic;
- immutable serializable frame and aggregate models;
- sample and analysis SHA-256 fingerprints;
- `signal-analyze` integration with configurable pitch-analysis parameters.

Deferred to later CODE V4 gates:

- phase stability and cycle discontinuity;
- pitch-motion trajectory classification beyond robust spread;
- noise and SNR estimation;
- transient and change-point detection;
- final aggregate `SignalAnalysis` contract;
- release version `0.4.0`.

## Pitch method

Each frame is mean-centered before analysis. A linear autocorrelation is
computed with a zero-padded real FFT. Candidate lags are limited by the user
frequency bounds and corrected for decreasing overlap. The first local maximum
within 90 percent of the strongest local maximum is selected, which prefers the
shortest convincing period rather than an arbitrary later multiple. A bounded
three-point parabolic interpolation refines the lag.

A frame is voiced only when:

1. its RMS exceeds the active threshold;
2. a valid lag exists inside the configured range;
3. its periodicity score reaches the confidence threshold.

Silence and rejected frames expose JSON `null` for pitch fields, never NaN or
infinity.

## Aggregate definitions

- `frequency_hz`: confidence-weighted median of voiced-frame frequencies;
- `periodicity_score`: confidence-weighted median voiced-frame score;
- `pitch_spread_cents`: confidence-weighted median absolute cents distance from
  the aggregate pitch;
- `pitch_stability`: `1 / (1 + pitch_spread_cents / 50)`;
- `quasi_periodicity_score`: periodicity score multiplied by voiced-active ratio
  and pitch stability.

Classification thresholds are explicit:

- no active frames: `silent`;
- no confident sustained lag: `aperiodic`;
- voiced in fewer than half of active frames: `intermittent_periodic`;
- robust spread at most 15 cents: `stable_periodic`;
- spread above 15 and at most 120 cents: `quasi_periodic`;
- spread above 120 cents: `unstable_periodic`.

## Musical-note conversion

The default reference is A4 = 440 Hz and can be changed explicitly. MIDI pitch
uses:

```text
69 + 12 * log2(frequency / reference_a4_hz)
```

The nearest MIDI integer is converted to scientific pitch notation, where MIDI
60 is C4. Cents deviation remains in the interval from -50 to +50 cents.

## Automated validation

Generated CODE V4-B tests:

```text
46 passed
0 failed
```

Coverage includes:

- exact and detuned sine waves;
- square and harmonic-rich waves;
- DC offset;
- silence and seeded white noise;
- vibrato and quasi-periodicity;
- intermittent periodicity;
- abrupt two-note instability;
- short and end-aligned frames;
- stable hashes and source preservation;
- JSON finite-number policy;
- custom tuning reference;
- invalid ranges, Nyquist bounds, confidence, and samples;
- deterministic CLI JSON and report writing;
- public API availability.

## Expected repository totals

Starting from the accepted CODE V4-A totals:

```text
Targeted CODE V4-B : 46 passed
Public full suite   : 290 passed, 4 skipped
Private full suite  : 294 passed
```

The release version remains `0.3.0` during this intermediate gate. CODE V4 is
finalized as `0.4.0` only after the remaining DSP modules and final aggregate
contract are accepted.

CODE V4-B does not generate SysEx and performs no MIDI transmission.
