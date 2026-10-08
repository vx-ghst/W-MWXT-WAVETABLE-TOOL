# CODE V8-K — XT User-WAVD 64-to-128 model

## Scope

This model applies to User Waves transmitted by a Microwave II/XT WAVD message.
It is not a universal claim about ROM waves, algorithmic waves, or every internal
full-cycle oscillator mode.

## Reconstruction model

```text
full[n]      = stored[n]       for n = 0..63
full[64 + k] = -stored[63-k]   for k = 0..63
```

The software projects a 128-point target into the constrained 64-value stored
form, quantizes within the safe range, evaluates every phase rotation, and ranks
candidates with time-domain, spectral, harmonic, and cycle-boundary metrics.

## Confidence boundary

The model predicts the constrained digital User-Wave representation. It does not
claim a bit-exact emulation of the complete oscillator DSP, converters, or analog
output stage. Three asymmetric hardware probes across MIDI notes 48, 60, and 72
are required to compare this rule against competing reconstruction hypotheses.
