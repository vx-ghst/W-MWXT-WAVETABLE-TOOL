# CODE V5-B Validation

## Scope

CODE V5-B adds deterministic harmonic-series and perceptual-band descriptors on
top of the accepted CODE V5-A spectral foundation.

Implemented:

- explicit fundamental-frequency input for harmonic measurement;
- unique FFT-bin assignment to the nearest valid harmonic;
- configurable harmonic count, tolerance, and minimum power threshold;
- immutable per-harmonic peak records;
- harmonic and residual energy ratios;
- harmonic-to-residual ratio in decibels when finite;
- fundamental, odd, and even harmonic power ratios;
- three-part tristimulus distribution;
- power-weighted inharmonicity in cents;
- harmonic spectral slope in decibels per octave;
- deterministic Bark-band energy distribution;
- Bark centroid, spread, and normalized entropy;
- bounded perceptual brightness, spectral concentration, and noisiness metrics;
- cross-component sample and spectral-analysis identities;
- deterministic component SHA-256;
- public API propagation;
- dedicated `perceptual-analyze` CLI command combining CODE V4 pitch,
  CODE V5-A spectral analysis, and CODE V5-B harmonic/perceptual analysis.

Deferred to later CODE V5 gates:

- explainable source-family classification;
- confidence-calibrated class scores;
- engineering decision policies and recommendations;
- final CODE V5 aggregate contract;
- release version `0.5.0`.

## Harmonic method

CODE V5-B does not estimate pitch independently. It accepts an explicit
fundamental frequency. The CLI obtains that value from the accepted deterministic
CODE V4 pitch-periodicity analysis. This keeps pitch estimation and harmonic
measurement as separate, auditable components.

Each positive-frequency FFT bin is assigned to at most one nearest integer
harmonic. Assignment requires either the configured cents tolerance or the
minimum resolution-aware tolerance of 1.5 FFT bins. Unique assignment prevents
harmonic-energy double counting.

Detected harmonics must reach the configured peak-power ratio. Aggregate
harmonic energy uses the detected harmonic bands. Odd/even and tristimulus
values are normalized inside detected harmonic energy. Inharmonicity is the
power-weighted absolute cents deviation of observed harmonic peaks from their
ideal integer multiples.

## Perceptual-band method

The accepted V5-A normalized mean spectrum is mapped to configurable Bark bands
using a deterministic analytical frequency-to-Bark transform. Active Bark-band
energies sum to one. Silence exposes a zero distribution and JSON `null`
descriptors.

The perceptual metrics are measurements, not source labels:

- brightness is spectral centroid divided by Nyquist frequency;
- concentration is one minus normalized spectral entropy;
- noisiness reuses spectral flatness;
- Bark centroid, spread, and entropy describe critical-band energy placement.

Source classification is intentionally deferred to CODE V5-C.

## Safety

CODE V5-B imports and analyzes audio only. It does not generate SysEx and does
not transmit MIDI.

## Automated validation

```text
Targeted CODE V5-B : 38 passed
Public full suite   : 470 passed, 4 skipped
Private full suite  : 474 passed
```

The release version remains `0.4.0` during this intermediate gate.
