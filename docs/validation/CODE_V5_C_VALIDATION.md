# CODE V5-C Validation

## Scope

CODE V5-C adds deterministic, explainable source-family classification on top
of the accepted CODE V4 signal analysis, CODE V5-A spectral analysis, and CODE
V5-B harmonic/perceptual analysis.

Implemented:

- strict cross-component sample-rate, sample-count, and sample-hash validation;
- strict spectral-analysis hash linkage;
- strict pitch/fundamental-frequency agreement;
- bounded auditable classification features;
- canonical source families: silent, stable tonal, evolving tonal, noisy
  texture, transient rich, and mixed complex;
- normalized per-class scores in canonical order;
- deterministic winner selection and tie-breaking;
- confidence, ambiguity, and winner-margin evidence;
- immutable serializable classification models;
- deterministic classification SHA-256;
- public API propagation;
- dedicated `classify-audio` CLI command.

Deferred to later CODE V5 gates:

- engineering decision policies;
- corrective recommendations;
- final aggregate CODE V5 analysis contract;
- release version `0.5.0`.

## Classification features

Every feature is bounded to `[0, 1]` and retains a plain-language explanation:

- active presence;
- periodicity;
- harmonicity;
- spectral concentration;
- tonal presence;
- global stability;
- temporal instability;
- noise presence;
- transient activity;
- spectral complexity.

The classifier does not alter any accepted measurement. It only combines the
linked analysis contracts through explicit formulas. Class scores are normalized
to sum to one. The selected class is the highest score, using the canonical enum
order as the deterministic tie-break.

## Safety

CODE V5-C imports and analyzes audio only. It does not generate SysEx and does
not transmit MIDI. Classification is descriptive; decision and repair policies
remain deferred to CODE V5-D.

## Automated validation

```text
Targeted CODE V5-C : 45 passed
Public full suite   : 515 passed, 4 skipped
Private full suite  : 519 passed
```

The release version remains `0.4.0` during this intermediate gate.
