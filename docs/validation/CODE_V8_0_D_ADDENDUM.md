# CODE V8-0D Addendum - XT-native resampling and effective profiles

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0D
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0C / a72aeb4d050f73541358a32e0b9f63852ae1ff2d
Version : 0.7.0 (unchanged until CODE V8-G)
```

## Purpose

CODE V8-0D closes the XT-relative analysis and treatment contracts that could not be completed in source-only stages. It adds an explicit comparison layer around the accepted V7 reverse-negate reconstruction rule without mutating the frozen V7 projection, trajectory, QC, package, or hardware-evidence schemas.

## Requirements assigned to this stage

```text
CDC-SPEC-012  harmonic loss caused by XT reduction
CDC-SPEC-013  aliasing risk after conversion and transposition
CDC-PSY-006   source-versus-XT perceptual difference
CDC-CYC-004   XT compatibility and psychoacoustic cycle quality
CDC-XT-002    rotation, start, phase, polarity, time reversal, and mirror candidates
CDC-XT-003    multiple half-wave and reduction methods
CDC-XT-004    complete XT wave metrics
CDC-XT-005    effective Bass/Sub weighting
CDC-XT-006    linked before/after and 128/64/reconstruction representations
CDC-XT-007    automatic or user-selected treatment
CDC-RSM-002   high-quality periodic resampling and anti-aliasing
CDC-RSM-003   multiple resampling algorithms
CDC-RSM-004   phase and fundamental preservation
CDC-RSM-005   explicit normalization without hidden Bass thinning
CDC-RSM-006   ringing, overshoot, and extreme-value control
CDC-BASS-001  fundamental and H2/H3 preservation
CDC-BASS-002  subharmonic and phase control
CDC-BASS-003  non-useful upper-harmonic reduction evidence
CDC-BASS-004  inter-wave amplitude and Bass-power consistency
CDC-BASS-005  Bass-specific working-pitch comparison
CDC-BASS-006  monophonic Bass instability warning
CDC-BASS-007  separate Sub and Bass scores
CDC-PROF-001  nine effective optimization profiles
CDC-PROF-002  explicit Experimental controlled-defect policy
```

## Additive architecture

```text
profiles/models.py
profiles/weights.py
profiles/factory.py
profiles/bass.py
decision/profile_selector.py
xt/resampling.py
xt/quantization.py
xt/symmetry_candidates.py
xt/wave_metrics.py
xt/wave_optimizer.py
```

The historical `XtProjectionSet` and its V7 serialized children remain unchanged. V8-0D consumes the same confirmed XT reconstruction rule and emits separate schema-versioned comparison and optimization results.

## Resampling contract

Three deterministic periodic algorithms are compared:

```text
windowed_sinc  anti-aliased Kaiser-windowed periodic sinc
fourier        periodic Fourier-domain band-limited resampling
linear         periodic linear diagnostic baseline
```

Every result records phase shift, phase correlation, fundamental-amplitude ratio, low-band loss, spectral error, aliasing risk, ringing, overshoot, extremes, normalization, warnings, and a canonical SHA-256.

Normalization is explicit:

```text
none
peak_match
rms_match
bass_protect
```

Safety scaling is reported and never implemented as silent sample clipping.

## Quantization contract

Quantization compares deterministic nearest and error-feedback candidates. Generated XT values are limited to `-127..127`; `-128`, wraparound, non-finite values, and silent overflow are rejected. Before/after time, spectral, harmonic, band, DC, extreme, and quality measurements are serialized.

## Symmetry-candidate contract

The optimizer can evaluate:

```text
6 transforms
128 phase/start rotations
6 half-wave or reduction methods
2 quantization algorithms
4 explicit normalization policies
```

The default optimizer uses every phase, transform, and half-wave method with nearest XT quantization. Search configuration is immutable, serializable, deterministic, and overridable.

## XT metrics and aliasing contract

`XtWaveMetrics` records time, phase, harmonic, band, seam, amplitude, aliasing, ringing, subharmonic, perceptual, Sub, and Bass evidence. `XtAliasingAnalysis` evaluates one reconstructed wave at ascending playback frequencies across several octaves and records the safe harmonic boundary and aliased power for each note.

The cycle-domain perceptual distance is a deterministic engineering proxy. It does not claim calibrated audibility or a bit-exact XT DSP model.

## Effective profiles

Exactly nine effective profiles are defined:

```text
bass_sub
lead
pad
bell_fm
vocal_choir
texture
drone
percussive
experimental
```

Each profile contains one normalized 14-component objective vector. Musical classification supplies the main prior; the conversion-mode prior is capped at `0.25` and cannot independently force a profile. A manual override preserves the automatic profile evidence.

The Experimental profile may explicitly preserve controlled aliasing, asymmetry, saturation, phase error, roughness, and abrupt-transition evidence. It never permits non-finite values, overflow, generated `-128`, or unreported clipping.

## Bass/Sub contract

Bass/Sub adds:

- explicit fundamental, H2, H3, low-band, phase, amplitude, aliasing, and ringing weights;
- Bass Protect normalization;
- separate Sub and Bass scores;
- subharmonic and monophonic-instability warnings;
- upper-harmonic reduction evidence;
- comparison of every accepted V6 working-pitch candidate;
- amplitude and Bass-power consistency across an ordered wave set.

## Independent wave-set operation

`optimize_xt_wave_set` applies the same effective profile independently to every input wave and preserves canonical source order. It supports exactly 61 inputs and records one indexed optimization result per wave. Final selection, placement, interpolation, and WCTD construction remain assigned to CODE V8.

## Explicitly deferred scope

```text
complete Auto Repair policy/actions                 V8-0E
pre-V8 aggregate and zero required-debt gate        V8-0F
61-position selection, ordering, interpolation      V8
Sound, reports, exports, complete project           V9
calibrated preview and hardware audibility          V10
```

## Safety boundary

CODE V8-0D opens no MIDI port, transmits no SysEx, allocates no XT memory, and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
