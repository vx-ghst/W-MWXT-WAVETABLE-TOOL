# CODE V5-E Validation

## Scope

CODE V5-E closes release `0.5.0` by adding one immutable aggregate contract over
the accepted CODE V4, V5-A, V5-B, V5-C, and V5-D components.

Implemented:

- `CodeV5Analysis` schema version 1;
- canonical tool version, sample rate, sample count, and sample SHA-256;
- nested preservation of every accepted component report;
- canonical component-hash map;
- strict sample-identity agreement across all components;
- strict harmonic-to-spectral, classification-to-component, and
  decision-to-classification linkage;
- strict pitch/fundamental consistency;
- deterministic aggregate serialization and SHA-256;
- assembly of precomputed accepted components;
- complete canonical analysis from one imported `AudioSource`;
- public API propagation;
- `analyze-audio` CLI command;
- version, CHANGELOG, README, roadmap, release notes, and package metadata updated to 0.5.0.

## Aggregate report shape

```text
audio
code_v5_analysis
  schema_version
  tool_version
  sample_rate
  sample_count
  sample_sha256
  component_sha256
  signal_analysis
  spectral_analysis
  harmonic_perceptual_analysis
  source_classification
  engineering_decision
  analysis_sha256
```

## Validation rules

Acceptance requires all of the following:

1. every component has the same sample rate, sample count, and sample SHA-256;
2. every stored component hash is a lowercase SHA-256 digest;
3. harmonic/perceptual analysis links to the supplied spectral analysis;
4. source classification links to the supplied signal, spectral, and
   harmonic/perceptual analyses;
5. engineering decision links to the supplied source classification;
6. the signal pitch and harmonic fundamental have identical availability and,
   when present, agree within `1e-9 Hz`;
7. two runs on the same imported source produce byte-identical JSON reports;
8. the aggregate hash is stable and changes when nested report content changes.

## Automated validation

```text
Targeted CODE V5-E : 50 passed
Public full suite   : 610 passed, 4 skipped
Private full suite  : 614 passed
```

## Manual real-audio gate

Source retained outside the repository:

```text
D:\DEV\V3A_TEST\odium-key-1.wav
```

Required result:

- two identical report-file SHA-256 values;
- all sample identities and component hash links valid;
- tool version `0.5.0`;
- source class `stable_tonal`;
- engineering status `ready`;
- readiness plus risk equal one;
- no blocker;
- all recommendations remain non-automated;
- a valid deterministic CODE V5 aggregate SHA-256.

## Release safety

CODE V5-E contains no audio, SysEx dump, project archive, hardware capture, MIDI
transmission, audio mutation, automatic repair, or automatic recommendation
execution.
