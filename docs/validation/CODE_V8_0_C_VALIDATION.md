# CODE V8-0C Validation - spectrum, perceptual analysis, classification, and modes

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0C
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0B / 5455d228a862ba545d1194341be7b92adeb6be32
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY - PRIVATE SUITE AND REMOTE CI PENDING
```

## Closed source-domain requirements

```text
SPEC-004  low, low-mid, mid, and high spectral energy
SPEC-006  harmonic evolution and harmonic-density trajectories
SPEC-007  harmonic and inharmonic partial inventory
SPEC-008  broad formant-candidate analysis
SPEC-011  spectral correlation between arbitrary source spans
PSY-001   perceived low-frequency power and fundamental presence
PSY-002   perceived brightness and hardness proxies
PSY-003   perceived saturation and density proxies
PSY-004   sense-of-motion proxy
PSY-005   perceptual distance and audible redundancy
PSY-007   generic ordered-sweep continuity
CLS-001   canonical 27-class multi-label musical classification
CLS-002   classification guides priorities but cannot alone force a mode
MODE-001  Stable Cycle
MODE-002  Evolving Harmonics
MODE-003  Dynamic Pitch
MODE-004  Spectral Reconstruction
MODE-005  Hybrid
MODE-006  explicit manual conversion-mode override
```

XT-relative loss, aliasing, and source-versus-XT perceptual difference remain assigned to V8-0D as recorded in the addendum.

## Compatibility architecture

The following accepted schema-1 contracts remain unchanged:

```text
SpectralAnalysis
HarmonicPerceptualAnalysis
SourceClassification
EngineeringDecision
CodeV5Analysis
CodeV6Analysis
```

V8-0C adds linked contracts rather than extending serialized historical payloads in place.

## Formant contract

`FormantAnalysis` derives broad spectral-envelope peaks from the accepted mean spectrum. Every candidate records frequency, bandwidth, envelope power, prominence, and confidence. The contract explicitly reports zero evidence for silence and does not claim phonetic identity.

## Spectral-evolution contract

`SpectralEvolutionAnalysis` records:

```text
low, low-mid, mid, and high energy per active frame
harmonic and inharmonic energy per active frame
spectral density
adjacent-frame spectral correlation
harmonic-evolution score
density-evolution score
useful-change score
harmonic and inharmonic partial inventory
```

`SpectralCorrelationMatrix` compares arbitrary labeled source spans in canonical pair order.

## Perceptual contract

`PerceptualFeatureVector` contains nine bounded deterministic engineering proxies:

```text
low_frequency_power
fundamental_presence
brightness
hardness
saturation
density
motion
tonalness
noisiness
```

The values are linked to accepted signal, signal-extension, spectral, harmonic, spectral-evolution, and formant hashes. They are engineering estimates and do not claim calibrated loudness or hardware audibility.

`PerceptualDistance` uses explicit versioned weights. `PerceptualDistanceMatrix` produces transitive redundancy groups. `SweepContinuityAnalysis` reports every adjacent transition, mean and maximum distance, discontinuity count, and a bounded continuity score.

## Musical-classification contract

The taxonomy contains exactly 27 classes in canonical specification order. Every result contains:

```text
one score and explanation for every class
one or more selected labels
explicit score threshold and maximum-label count
confidence and complementary ambiguity
evidence and deterministic SHA-256
```

The classification is multi-label. Its influence on mode selection is capped and serialized; changing only the musical label cannot independently force a different conversion mode.

## Conversion-mode contract

The decision layer contains exactly five modes:

```text
stable_cycle
evolving_harmonics
dynamic_pitch
spectral_reconstruction
hybrid
```

Every mode maps to an importable existing callable path. Automatic decisions serialize all five raw and normalized scores. Manual overrides preserve the automatic evidence and produce explicit warnings when the override conflicts with measured periodicity or tonality. Silent or materially inactive sources produce an explicit rejected decision with no hidden fallback.

## Local validation

```text
compileall                         : PASS
pip check                          : PENDING IN TARGET ENVIRONMENT
V8-0C targeted suite              : 118 passed
Complete public suite             : 1246 passed, 4 skipped
Complete private suite            : PENDING IN TARGET ENVIRONMENT
Formant and partial corpus         : PASS
Four-band conservation             : PASS
Perceptual bounds and JSON safety  : PASS
Distance symmetry and grouping     : PASS
Five executable mode paths         : PASS
27-class canonical taxonomy        : PASS
Override and refusal states        : PASS
Deterministic hashes               : PASS
git diff --check                  : PENDING IN TARGET ENVIRONMENT
Wheel module inclusion             : PENDING IN TARGET ENVIRONMENT
```

The four public skips are the existing private real-dump tests because private evidence is not stored in the repository.

## Gates still required before V8-0C closure

```text
[ ] pip check passes in the target environment
[ ] complete private suite passes with all four reference dumps mounted
[ ] isolated PEP 517 wheel includes all new production modules
[ ] exact authorized file set and git diff --check pass
[ ] implementation commit SHA is recorded
[ ] twelve push and pull-request checks pass
[ ] repository is clean after the implementation commit
[ ] final closure evidence is committed in this report
```

## Safety boundary

CODE V8-0C opens no MIDI port, transmits no SysEx, modifies no instrument state, and commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
