# CODE V8-0D Validation - XT-native resampling and effective profiles

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0D
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0C / a72aeb4d050f73541358a32e0b9f63852ae1ff2d
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : VALIDATED - LOCAL, PRIVATE, WHEEL, AND REMOTE CI GATES PASSED
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

## Final validation evidence

```text
compileall                              : PASS
pip check                               : PASS
V8-0D targeted suite                    : 94 passed
Complete public suite                   : 1340 passed, 4 skipped
Complete private suite                  : 1344 passed
Profile count                           : 9 exact
Profile weight sum                      : 1.0 exact for every profile
Resampling algorithms                   : 3 exact
Quantization algorithms                 : 2 exact
Wave transforms                         : 6 exact
Half-wave methods                       : 6 exact
Phase search domain                     : 0..127
61-wave independent operation           : PASS
Strict -127..127 output                 : PASS
Forbidden -128 gate                     : PASS
NaN and infinity rejection              : PASS
Serialization and deterministic hashes  : PASS
Isolated PEP 517 wheel build            : PASS
Wheel module inclusion                  : PASS
Wheel size                              : 353984 bytes
Wheel SHA-256                           : ff9e0a69829bfe365eb52cd642fdee20239af5494b11e03e525901a9f272337e
git diff --check                        : PASS
Authorized implementation paths         : 26/26 exact
```

The four public skips are exclusively the existing private real-dump tests. The complete private suite was executed with all four reference dumps mounted and finished with zero failed and zero skipped tests.

The wheel was built with the standard isolated PEP 517 process declared by `pyproject.toml`. Every new V8-0D production module was present in the generated wheel.

The line-ending notices emitted by Git on Windows were advisory only. The implementation diff passed `git diff --check`, the exact-path gate, and the final empty-index gate.

## Remote validation evidence

```text
Implementation commit       : fb0b7e0840c00699a7ab0e890d786b0666bb0b48
Draft pull request          : 7
Pull-request base           : main
Pull-request head           : code-v8-wavetable-builder
Push workflow run           : 30819338234
Pull-request workflow run   : 30819342100
Unique CI environments      : 6
Push checks                 : 6/6 passed
Pull-request checks         : 6/6 passed
Total implementation checks : 12/12 passed
Cancelled                   : 0
Failed                      : 0
Skipped                     : 0
Pending                     : 0
```

The six operating-system and Python combinations ran through both push and pull-request events. Every job completed project installation, compileall, pip check, and the complete public suite.

## Closure gates

```text
[x] three deterministic periodic resamplers implemented
[x] anti-alias, phase, fundamental, normalization, ringing, overshoot, and extreme-value evidence implemented
[x] two deterministic XT quantizers implemented
[x] generated XT range is strictly limited to -127..127
[x] forbidden -128, wraparound, overflow, NaN, and infinity are rejected
[x] six transforms and all 128 phase/start positions are searchable
[x] six half-wave or reduction methods are implemented
[x] complete time, phase, harmonic, band, seam, amplitude, aliasing, ringing, and perceptual metrics are implemented
[x] source-versus-XT cycle-domain perceptual difference is serialized
[x] multi-note aliasing analysis is implemented
[x] exactly nine effective profiles are implemented
[x] every profile objective vector sums exactly to 1.0
[x] conversion-mode influence is capped and cannot independently force a profile
[x] manual profile and treatment overrides preserve automatic evidence
[x] Experimental controlled-defect preservation is explicit and bounded by hard safety rules
[x] Bass Protect normalization is explicit
[x] separate Sub and Bass scores are implemented
[x] Bass-specific working-pitch comparison is implemented
[x] monophonic Bass instability warning is implemented
[x] exactly 61 waves can be optimized independently under one profile
[x] historical V5, V6, and V7 serialized contracts remain unchanged
[x] targeted V8-0D suite passes
[x] complete public suite passes
[x] complete private suite passes with all four reference dumps
[x] isolated PEP 517 wheel builds successfully
[x] all new production modules are present in the wheel
[x] exact 26-file implementation diff and whitespace checks pass
[x] twelve implementation checks pass
[x] implementation commit SHA and workflow runs are recorded
[x] repository is clean after the implementation commit
[x] no automatic MIDI or SysEx transmission is introduced
[x] no private dump, generated SysEx, audio capture, local path, or private evidence is committed
```

CODE V8-0D is formally closed.

This closure validates V8-0D only. It does not claim implementation of V8-0E complete Auto Repair policies and actions, V8-0F aggregate debt closure, or the later generic 61-position builder.

## Safety boundary

CODE V8-0D opens no MIDI port, transmits no SysEx, modifies no instrument state, and commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
