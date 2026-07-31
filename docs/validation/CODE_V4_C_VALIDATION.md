
# CODE V4-C Validation

## Scope

CODE V4-C adds deterministic phase-continuity, cycle-discontinuity, and
pitch-motion analysis on top of the accepted CODE V4-B pitch and periodicity
foundation.

Implemented:

- phase estimation at the center of every voiced pitch frame;
- sinusoidal projection-strength measurement;
- expected phase-advance comparison across consecutive voiced frames;
- wrapped phase-error measurements in radians and degrees;
- configurable cycle-discontinuity threshold;
- median, 95th-percentile, and maximum absolute phase error;
- phase-stability score and discontinuity ratio;
- explainable phase classes: unavailable, stable, variable, discontinuous;
- pitch excursion, median step, maximum step, and linear slope;
- direction consistency, reversal count, and reversal rate;
- explainable pitch-motion classes: unvoiced, insufficient, stable, glide up,
  glide down, vibrato, stepped, irregular;
- exact reuse and fingerprint validation of a precomputed CODE V4-B pitch report;
- immutable serializable models and deterministic SHA-256 fingerprints;
- `signal-analyze` integration and explicit CLI thresholds.

Deferred to later CODE V4 gates:

- noise-floor and SNR estimation;
- transient and change-point detection;
- final aggregate `SignalAnalysis` contract;
- release version `0.4.0`.

## Phase method

For each voiced pitch frame, the mean-centered signal is Hann-windowed and
projected onto the estimated fundamental frequency. The complex projection is
converted to a phase value at the frame center. For consecutive voiced frames,
the observed phase advance is compared with the advance predicted from the mean
of the two frame frequencies and the elapsed center time. The residual is
wrapped to the interval from `-pi` to `+pi`.

This is a deterministic signal-analysis metric. It does not claim to recover an
absolute analogue oscillator phase.

## Pitch-motion method

Voiced-frame frequencies are expressed on a cents scale. Consecutive voiced
frames provide pitch steps, direction signs, and reversals. A deterministic
least-squares slope is computed from all voiced frame centers. Explicit
thresholds classify stable pitch, directional glides, bounded reversing motion,
discrete steps, and residual irregular motion.

## Safety

CODE V4-C imports and analyzes audio only. It does not generate SysEx and does
not transmit MIDI.
