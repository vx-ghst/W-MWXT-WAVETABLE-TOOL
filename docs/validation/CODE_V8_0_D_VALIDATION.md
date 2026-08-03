# CODE V8-0D Validation - XT-native resampling and effective profiles

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0D
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0C / a72aeb4d050f73541358a32e0b9f63852ae1ff2d
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY - PRIVATE SUITE AND REMOTE CI PENDING
```

## Implemented contracts

```text
three deterministic periodic resamplers
overt anti-alias and normalization evidence
two deterministic XT quantizers
strict generated range -127..127
six transforms and 128 phase/start positions
six half-wave/reduction methods
complete XT wave metrics and multi-note aliasing
source-versus-XT cycle-domain perceptual difference
nine effective optimization profiles
capped profile-selection prior and manual override
Bass-specific working-pitch comparison
separate Sub and Bass scores
61-wave independent optimizer aggregate
```

## Compatibility contract

The following accepted schemas are not modified:

```text
CodeV5Analysis
CodeV6Analysis
XtProjectionMetrics
XtPhaseEvaluation
XtProjectedWave
XtProjectionSet
XtWavetableTrajectory
XtTrajectoryQcAnalysis
XtHardwarePackageAnalysis
```

V8-0D adds linked contracts and does not reinterpret historical V7 artifacts.

## Local design validation

```text
compileall                              : PASS on isolated V8-0D source bundle
V8-0D isolated targeted suite          : 94 passed
profile count                          : 9 exact
profile weight sum                     : 1.0 exact for every profile
resampling algorithms                  : 3 exact
quantization algorithms                : 2 exact
wave transforms                        : 6 exact
half-wave methods                      : 6 exact
phase search domain                    : 0..127
61-wave independent operation          : PASS
strict -127..127 output                : PASS
forbidden -128 gate                    : PASS
NaN and infinity rejection             : PASS
serialization and deterministic hashes : PASS
```

## Target-environment gates still required

```text
[ ] compileall passes in the target repository
[ ] pip check passes in the target environment
[ ] V8-0D targeted suite passes in the target repository
[ ] complete public suite passes
[ ] complete private suite passes with all four reference dumps mounted
[ ] isolated PEP 517 wheel includes all new production modules
[ ] exact authorized file set and git diff --check pass
[ ] implementation commit SHA is recorded
[ ] twelve push and pull-request checks pass
[ ] repository is clean after the implementation commit
[ ] final closure evidence is committed in this report
```

## Acceptance assertions

- All output models reject NaN and infinity.
- Quantization cannot emit `-128`.
- No resampler silently clips; any safety scale is serialized.
- Linear resampling is identified as a diagnostic non-anti-aliased baseline.
- Automatic profile selection cannot be forced solely by the conversion mode.
- Manual profile and treatment overrides retain the automatic evidence.
- Experimental controlled-defect preservation is explicit and bounded by hard safety rules.
- Bass/Sub exposes separate Sub and Bass scores and a monophonic warning.
- Exactly 61 waves can be optimized independently under one profile.
- No MIDI or SysEx transmission path is introduced.

## Safety boundary

CODE V8-0D opens no MIDI port, transmits no SysEx, modifies no instrument state, and commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
