# CODE V5-D Validation

## Scope

CODE V5-D adds a deterministic, auditable engineering-decision layer on top of
the accepted CODE V5-C source classification.

Implemented:

- strict source-classification SHA-256 linkage;
- strict reuse of the canonical sample identity;
- bounded wavetable-readiness and risk scores;
- explicit decision states: ready, review, and not recommended;
- deterministic recommendation priorities and ordering;
- threshold-based recommendations for inactive content, weak tonal evidence,
  temporal instability, noise, transients, and spectral complexity;
- explicit blockers for silent or materially inactive sources;
- non-destructive preservation guidance for stable and evolving tonal sources;
- immutable serializable decision and recommendation models;
- deterministic engineering-decision SHA-256;
- public API propagation;
- dedicated `recommend-audio` CLI command.

Deferred to CODE V5-E:

- final aggregate CODE V5 analysis contract;
- consolidated documentation and release notes;
- release version `0.5.0`;
- pull request, merge, and annotated release tag.

## Decision policy

The decision engine does not modify audio and does not execute a recommendation.
Every recommendation has `automated=false` and includes its measured evidence.

A source is `not_recommended` only when it is silent or has at most five percent
active presence. Other material remains reviewable. A `ready` decision requires
a stable-tonal classification, sufficient classification confidence, a readiness
score of at least 0.72, and no high-priority recommendation. All other usable
sources are marked `review`.

Readiness combines active presence, tonal presence, global stability,
classification confidence, and inverse noise, transient, and complexity evidence.
Risk is exactly one minus readiness.

## Safety

CODE V5-D imports and analyzes audio only. It does not alter audio, generate
SysEx, write synthesizer memory, or transmit MIDI.

## Automated validation

```text
Targeted CODE V5-D : 45 passed
Public full suite   : 560 passed, 4 skipped
Private full suite  : 564 passed
```

The release version remains `0.4.0` during this intermediate gate.
