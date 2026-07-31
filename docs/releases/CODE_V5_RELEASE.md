# CODE V5 Release — 0.5.0

## Release identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Release : 0.5.0
Stage   : CODE V5
Branch  : code-v5-spectral-engine
```

CODE V5 converts the accepted CODE V4 time-domain measurements into a complete,
deterministic spectral-analysis and engineering-decision chain. Every component
retains the canonical sample identity and exposes its own SHA-256. The final
`CodeV5Analysis` contract validates all links and produces one aggregate hash.

## Delivered stages

### CODE V5-A — spectral foundation

- deterministic framed FFT analysis;
- active-frame detection;
- average and local spectra;
- centroid, bandwidth, roll-off, flatness, entropy, flux, band energy, dominant
  frequency, and stationarity;
- immutable spectral models and deterministic spectral SHA-256;
- `spectral-analyze` CLI command.

Commit:

```text
d57ab43b53f962a058a97710a80aa52b4591ebc7
```

### CODE V5-B — harmonic and perceptual descriptors

- fundamental-linked harmonic detection;
- harmonic and residual energy;
- harmonic-to-residual ratio;
- odd/even balance and tristimulus;
- inharmonicity and spectral slope;
- Bark-band centroid, spread, and entropy;
- brightness, concentration, and noisiness;
- deterministic harmonic/perceptual SHA-256;
- `perceptual-analyze` CLI command.

Commit:

```text
94a43d22b4d28632e7c9edc2368d683b955af104
```

### CODE V5-C — explainable source classification

Canonical source families:

```text
silent
stable_tonal
evolving_tonal
noisy_texture
transient_rich
mixed_complex
```

The classifier exposes bounded features, normalized class scores, deterministic
tie-breaking, confidence, ambiguity, a winner margin, evidence, and a plain-
language reason. It does not alter accepted measurements.

Commit:

```text
d851ad62ef14cd013abbd796018684b71b2aab59
```

### CODE V5-D — engineering decisions

Canonical decision states:

```text
ready
review
not_recommended
```

The engine exposes readiness and risk, blockers, prioritized recommendations,
measured evidence, and a decision reason. Recommendations are advisory and always
carry `automated=false`.

Commit:

```text
597882ad0494252290107c3774b9c026e3a6b319
```

### CODE V5-E — aggregate contract and release closure

- immutable `CodeV5Analysis` aggregate;
- strict sample-rate, sample-count, and sample-hash agreement;
- strict component SHA-256 linkage from signal analysis through decision;
- pitch/fundamental consistency validation;
- deterministic aggregate SHA-256;
- public `assemble_code_v5_analysis` and `analyze_audio_source_code_v5` APIs;
- final `analyze-audio` CLI report;
- release metadata, changelog, roadmap, README, validation, and release documentation
  updated to `0.5.0`.

## Canonical hash chain

```text
AudioSource.sample_sha256
    ├── SignalAnalysis.analysis_sha256 ───────────────┐
    └── SpectralAnalysis.analysis_sha256              │
            └── HarmonicPerceptualAnalysis.analysis_sha256
                                                        │
Signal + Spectral + Harmonic/Perceptual ────────────────┘
            └── SourceClassification.analysis_sha256
                    └── EngineeringDecision.analysis_sha256

All accepted components ─── CodeV5Analysis.analysis_sha256
```

The links represent validated dependencies, not mutation. Signal and spectral
analysis derive independently from the same canonical mono source; classification
links all three evidence families, and the aggregate validates every component.

## Command-line interface

Complete CODE V5 report:

```powershell
W-MWXT-WAVETABLE-TOOL analyze-audio `
  "D:\Audio\source.wav" `
  --report "D:\Reports\source.code-v5.json"
```

Component commands remain available:

```text
signal-analyze
spectral-analyze
perceptual-analyze
classify-audio
recommend-audio
```

## Accepted real-audio evidence

Reference source used outside the repository:

```text
D:\DEV\V3A_TEST\odium-key-1.wav
```

Accepted results before aggregate closure:

```text
source_class                 : stable_tonal
classification_confidence    : 0.8244970349579748
decision_status              : ready
readiness_score              : 0.9226534967831393
risk_score                   : 0.07734650321686065
recommendation_count         : 2
blocker_count                : 0
source_classification_sha256 : b8399706d8a151828c05d4a277af3d99741ad9a5fc704b70ad5469c157098de0
engineering_decision_sha256  : f28296f245731c74896b96d60b68d86b68a76f0ec185b968876316c3a5475ba7
```

CODE V5-E acceptance additionally requires two byte-identical `analyze-audio`
reports and a valid aggregate SHA-256.

## Validation target

```text
Targeted CODE V5-E : 50 passed
Public full suite   : 610 passed, 4 skipped
Private full suite  : 614 passed
```

## Explicit boundaries

CODE V5 does not:

- segment audio or select cycles;
- repitch, reconstruct, resample, quantize, or repair audio;
- generate the 61-position wavetable;
- select final XT destinations or build new audio-derived SysEx;
- transmit MIDI;
- execute any recommendation automatically;
- claim the deferred formant, close-fundamental, explicit aliasing-risk,
  multi-label musical-profile, or conversion-mode work as implemented.

Those capabilities remain assigned to later CODE stages.

## Safety

The new aggregate command reads audio and writes an optional JSON report. It does
not modify source audio, synth memory, SysEx data, or MIDI state.
