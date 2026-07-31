# CODE V5-A Validation

## Scope

CODE V5-A establishes the deterministic spectral-analysis foundation on top of
release `0.4.0`.

Implemented:

- deterministic end-aligned spectral framing;
- explicit periodic Hann windowing;
- configurable power-of-two FFT size;
- deterministic DC removal policy;
- per-frame and aggregate power-spectrum analysis;
- spectral centroid and bandwidth;
- 85% and 95% spectral rolloff;
- spectral flatness, crest, and normalized entropy;
- dominant frequency and dominant-power ratio;
- configurable low, mid, and high band-energy ratios;
- positive spectral flux and stationarity;
- immutable serializable frame and aggregate models;
- sample and analysis SHA-256 fingerprints;
- public API propagation;
- dedicated `spectral-analyze` CLI command.

Deferred to later CODE V5 gates:

- harmonic-series, inharmonicity, and harmonic-to-noise descriptors;
- perceptual scales and psychoacoustic summaries;
- explainable source classification;
- decision policies and engineering recommendations;
- final CODE V5 aggregate contract;
- release version `0.5.0`.

## Spectral method

Frames reuse the accepted deterministic framing policy: sample zero is always a
frame start, regular starts advance by the configured hop size, and the final
full frame is aligned to the end of the signal. Short sources use one partial
frame.

Each frame is optionally mean-centered, multiplied by a periodic Hann window,
and transformed with a real FFT. The FFT size is explicit and must be a power of
two at least as large as the configured frame size. Short frames are transformed
inside the same fixed FFT grid so every frame shares one frequency axis.

Power is normalized by window energy. Inactive or spectrally empty frames expose
JSON `null` descriptors, never NaN or infinity.

## Aggregate spectrum

The aggregate normalized mean power spectrum is built from active frame power
spectra. It sums to one when active spectral energy exists and is all zero for
silence. Aggregate centroid, bandwidth, rolloff, flatness, crest, entropy,
dominant frequency, and band ratios are derived from this common spectrum.

Spectral flux uses only positive bin-wise changes between consecutive active
normalized spectra. Stationarity is an explicit bounded transform of median
flux. Source classification is intentionally deferred.

## Safety

CODE V5-A imports and analyzes audio only. It does not generate SysEx and does
not transmit MIDI.

## Automated validation

```text
Targeted CODE V5-A : 35 passed
Public full suite   : 432 passed, 4 skipped
Private full suite  : 436 passed
```

The release version remains `0.4.0` during this intermediate gate.
