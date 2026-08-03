# CODE V8-E Addendum - interpolation families and adaptive transition density

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-E
Branch  : code-v8-wavetable-builder
Base    : CODE V8-D / 2a292a63d1a703b1b60bd35f337762dd01883c16
Version : 0.7.0 (unchanged until CODE V8-G)
```

## Purpose

CODE V8-E consumes one immutable `WavetableBuildRequest`, its linked V8-B and V8-C analyses, and the complete ranked V8-D placement variants. It fills every V8-D open editable position, generates deterministic XT-native transition waves, allocates active transition density from measured interval complexity, and evaluates all 60 adjacent slot transitions.

CODE V8-E produces complete 61-slot in-memory `WavetableBuild` values. It does not apply Factory Style, serialize WCTD, allocate instrument memory, generate SysEx, open MIDI, transmit MIDI, or modify an instrument.

## Authoritative stage boundary

```text
V8-D  final ordering, sparse keyframe placement, locks, chronology, variants
V8-E  interpolation, adaptive density, complete 61-slot plans, continuity
V8-F  Factory Style, WCTD materialization, hardware gates
V8-G  integration, compliance closure, documentation, release gate
```

The three fixed tail references remain immutable V8-A evidence and are copied into every complete `WavetableBuild`. They are not materialized into WCTD by V8-E.

## Requirements advanced by this stage

```text
CDC-INT-001  deterministic waveform interpolation
CDC-INT-002  deterministic amplitude interpolation
CDC-INT-003  deterministic phase-aware interpolation
CDC-INT-004  deterministic spectral interpolation
CDC-INT-005  deterministic harmonic interpolation
CDC-INT-006  deterministic perceptual interpolation
CDC-INT-007  adaptive transition density from interval evidence
CDC-INT-008  fundamental, level and polarity protection
CDC-INT-009  complete transition map and continuity evidence
CDC-W61-003  fill every editable position while preserving keyframes
CDC-W61-004  preserve essential and locked positions exactly
```

Factory Style behavior, WCTD references, hardware interpolation behavior, positions 61-63 hardware evidence, and read-back remain assigned to V8-F.

## Additive architecture

```text
wavetable/interpolation.py
wavetable/continuity.py
wavetable/builder.py
```

The existing V8-A through V8-D models are consumed without mutation. The package root and public `wavetable` package re-export the complete V8-E surface.

## Interpolation families

The V8-A `GenerationMethod` contract already defines six interpolation families. V8-E implements all six:

```text
waveform interpolation
amplitude interpolation
phase-aware interpolation
spectral interpolation
harmonic interpolation
perceptual interpolation
```

### Waveform interpolation

Per-sample linear interpolation in the reconstructed 128-point cycle.

### Amplitude interpolation

Endpoint cycles are RMS-normalized, crossfaded, and restored to the linearly interpolated endpoint level.

### Phase-aware interpolation

The right endpoint is circularly aligned to the left endpoint before sample-domain interpolation. Polarity is never silently inverted.

### Spectral interpolation

The complex real-FFT spectra are interpolated directly and returned through a deterministic inverse transform.

### Harmonic interpolation

Harmonic magnitudes follow a log-domain path while phases follow the shortest wrapped angular path.

### Perceptual interpolation

A deterministic hybrid combines phase-aligned waveform motion and harmonic-domain motion. It remains an engineering interpolation proxy and does not claim calibrated auditory equivalence.

Every generated waveform is reduced to the 64 stored XT points, quantized with deterministic error feedback, clipped to the safe generated range `-127..127`, and reconstructed by the accepted XT antisymmetry contract.

## Method selection

`InterpolationPolicy` records:

```text
ordered enabled method priority
adaptive or fixed method selection
fundamental protection
RMS level protection
polarity continuity protection
level and fundamental tolerances
```

When adaptive selection is enabled, every allowed method is evaluated for one transition position. Selection uses deterministic objective evidence covering:

```text
expected path position between endpoints
RMS level error
fundamental magnitude error
polarity continuity
peak safety
```

Ties use policy priority, errors, and the generated stored-wave hash.

## Progression curves

V8-E supports the existing V8-A curves:

```text
linear
smoothstep
exponential
logarithmic
adaptive
```

The adaptive curve combines smoothstep and a complexity-dependent exponent. Every curve preserves exact zero and one boundaries and is monotonic.

## Adaptive transition density

`TransitionDensityPolicy` records a minimum active stage count, a base active fraction, a complexity contribution, and a complexity exponent.

For each pair of adjacent V8-D keyframes, V8-E measures:

```text
perceptual distance
spectral distance
maximum sample distance
endpoint complexity
RMS level difference
harmonic-concentration difference
```

The resulting bounded interval complexity determines the number of distinct active interpolation stages inside the fixed V8-D positional capacity. Low-complexity intervals may repeat generated stages across multiple positions. High-complexity intervals receive more distinct stages, up to every available position.

V8-E never moves a V8-D keyframe to obtain density. The transition map records both the desired active fraction and the realized stage count inside each immutable anchor interval.

## Edge positions

Some V8-D spacing variants may leave open positions before the first keyframe or after the last keyframe. These positions cannot have two interpolation endpoints. V8-E therefore uses explicit deterministic endpoint holds:

```text
leading positions  copy the first immutable keyframe
trailing positions copy the last immutable keyframe
```

Edge holds are marked `REDUNDANT`, are not claimed as interpolated waves, and remain visible in the transition map.

## Keyframe protection

Every V8-D assignment is copied byte-for-byte into its exact assigned position. V8-E verifies this after filling all open positions.

The following properties are preserved:

```text
candidate ID
stored 64-point samples
origin and generation method
metrics and source time
essential and structural role
accepted required or preference lock state
```

No interpolation output can replace, normalize, rotate, shift, invert, or otherwise mutate a selected keyframe.

## Complete 61-slot builds

Each successful V8-D variant produces one complete `WavetableBuild`:

```text
61 slots in canonical position order 0..60
immutable keyframe slots
interpolated transition slots
explicit repeated transition stages when density is reduced
explicit endpoint holds when edge positions are open
unchanged fixed-tail contract
```

All successful builds are collected into one `WavetableBuildSet`. V8-E may select a different primary variant from V8-D when continuity and density evidence justify it; the original V8-D rank remains recorded.

## Continuity analysis

`WavetableContinuityReport` evaluates all 60 adjacent slot transitions. Every transition records:

```text
waveform distance
spectral distance
perceptual distance
maximum sample distance
correlation
RMS level delta
fundamental delta
bounded continuity score
pass, warning, or failure status
intentional-break evidence where allowed
```

A failed transition cannot be hidden inside a complete V8-E variant. Variants with mandatory continuity failures are excluded. If every V8-D variant fails, V8-E returns an explicit rejected aggregate with no partial build set.

## Variant ranking

Complete V8-E variants are ranked by a deterministic objective combining:

```text
mean and minimum continuity
V8-D placement objective
adaptive density fit
absence of mandatory continuity failures
```

Ties use the original V8-D rank, variant ID, and build hash. Every build, transition map, continuity report, and aggregate exposes canonical JSON and lowercase SHA-256 evidence.

## Explicitly deferred scope

```text
Factory Style profile and heuristics             V8-F
WCTD reference assignment and serialization      V8-F
fixed positions 61-63 hardware confirmation      V8-F
hardware interpolation and read-back gates       V8-F
complete CODE V8 integration and release          V8-G
SysEx and MIDI execution                          later controlled stages
```

## Safety boundary

CODE V8-E performs deterministic in-memory waveform generation and analysis only. It writes no WCTD, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI, and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
