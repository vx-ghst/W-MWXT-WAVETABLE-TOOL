# CODE V8-0C Addendum - scope and taxonomy correction

## Purpose

This addendum resolves one audit-text inconsistency and records the exact V8-0C boundary before implementation evidence is closed.

## Canonical musical taxonomy

The normative public specification enumerates the following 27 musical classes:

```text
sub, bass, reese, fm_bass, dirty_bass, hoover, acid, lead, pad,
drone, organ, pwm, supersaw, wavetable, bell, fm_bell, pluck,
vocal, choir, texture, digital_noise, noise, piano, guitar,
percussion, fx, hybrid
```

A non-normative registry gap sentence used the phrase "28-label taxonomy" while the requirement text itself and the execution plan both enumerate 27 labels. V8-0C treats 27 as canonical and does not invent an unsupported class. The executable compliance registry is not rewritten during this stage because its canonical V8-0A hash remains frozen; the correction is recorded here and must be incorporated when the registry is formally refreshed at the V8-0F/V8-G closure gate.

## SPEC and PSY boundary

V8-0C closes source-domain spectral and perceptual requirements:

```text
four-band spectral split
harmonic evolution and density
harmonic and inharmonic partial inventory
formant candidates
spectral correlation between source spans
perceived low-frequency power and fundamental presence
brightness and hardness proxies
perceived saturation and density
motion proxy
perceptual distance and audible redundancy
ordered-sweep continuity
```

The following XT-relative measurements remain assigned to V8-0D because they require the XT-native reduction and resampling outputs that do not exist before that stage:

```text
SPEC-012 harmonic loss caused by XT reduction
SPEC-013 post-conversion aliasing risk
PSY-006 audible difference between source and XT reconstruction
```

V8-0C sweep continuity is a generic ordered-feature contract. It does not claim calibrated Microwave XT scan audibility; hardware-calibrated interpretation remains a later gate.

## Additive compatibility rule

The accepted V5 spectral, harmonic/perceptual, six-class classification, engineering-decision, and CodeV5Analysis schema-1 contracts remain unchanged. V8-0C adds linked schema-1 extension models and new decision contracts.

## File-list addendum

The execution plan already authorizes the new production modules and nine focused test files. This stage additionally creates:

```text
tests/v8c_helpers.py
docs/validation/CODE_V8_0_C_ADDENDUM.md
```

The helper contains deterministic synthetic fixtures only. It is not package data and contains no private audio, dump, SysEx, or absolute local path.
