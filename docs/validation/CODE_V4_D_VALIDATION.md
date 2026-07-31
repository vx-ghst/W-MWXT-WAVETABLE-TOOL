# CODE V4-D Validation

## Scope

CODE V4-D adds deterministic noise-floor, signal-to-noise, transient, and
change-point analysis on top of the accepted CODE V4-C phase and pitch-motion
foundation.

Implemented:

- frame-wise deterministic residual-noise candidates;
- period-lag residuals for confident voiced frames;
- conservative frame-RMS fallback for unvoiced material;
- explicit lower-quantile noise-floor estimate;
- signal RMS, noise-floor RMS, dBFS values, and finite SNR when defined;
- noise-stationarity score;
- explainable noise classes: silent, pristine, signal dominated, mixed, and
  noise dominated;
- deterministic short-time energy and normalized spectral-flux features;
- robust adaptive onset threshold based on median absolute deviation;
- minimum-separation transient peak selection;
- energy, spectral, and combined change points;
- transient density, median event interval, and change ratio;
- explainable classes: silent, steady, sparse transients, transient rich, and
  changing;
- immutable serializable models and stable SHA-256 fingerprints;
- `signal-analyze` integration with explicit configuration options.

Deferred to the final CODE V4 gate:

- the aggregate `SignalAnalysis` contract combining all accepted V4 modules;
- consolidated documentation and release propagation;
- release version `0.4.0`.

## Noise method

For each pitch-analysis frame, CODE V4-D uses a period-separated residual when
that frame has a confident fundamental lag. The residual is divided by the
square root of two so independent noise on the two compared cycles remains on a
single-signal RMS scale. Unvoiced frames use their full RMS as a conservative
noise candidate. The configured lower quantile of all candidates is reported as
the estimated noise floor.

This estimate is deterministic and explainable. It is not presented as a
laboratory measurement of analogue self-noise.

## Transient and change method

Frames provide RMS, log-energy change, and positive normalized spectral flux.
Onset strength combines positive energy rise and spectral flux. A median and MAD
threshold identifies local peaks, followed by deterministic minimum-separation
selection. Change points are reported independently when absolute energy change
or spectral flux crosses an explicit threshold.

## Safety

CODE V4-D imports and analyzes audio only. It does not generate SysEx and does
not transmit MIDI.

## Automated validation

Generated CODE V4-D tests:

```text
44 passed
0 failed
```

The isolated repository snapshot available during package construction passed:

```text
322 passed
0 failed
```

Expected totals on the accepted repository baseline are:

```text
Targeted CODE V4-D : 44 passed
Public full suite   : 366 passed, 4 skipped
Private full suite  : 370 passed
```

The release version remains `0.3.0` during this intermediate gate. CODE V4 is
finalized as `0.4.0` only after the aggregate analysis contract and release
closure are accepted.
