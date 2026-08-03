# CODE V8-0E Validation - complete Auto Repair policies and actions

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0E
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0D / aa319b396c12845c914efb5d0e5f7555d9327eb8
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : IMPLEMENTED LOCALLY - PRIVATE SUITE AND REMOTE CI PENDING
```

## Implemented contracts

```text
17 canonical Auto Repair defect detectors
17 canonical deterministic action kinds
four exact policies: AUTO, COMPARE, IGNORE, PRESERVE
canonical default policy and per-defect overrides
profile-aware explicit controlled-defect preservation
separate before, candidate, and selected branches
complete per-branch metrics and defect counts
one action record for every defect
metadata-only pitch correction evidence
dependency-aware deterministic action order
context refusal and review-required states
ordered wave-sequence repair
exact 61-wave sequence support
canonical JSON serialization and SHA-256 links
```

## Compatibility contract

The following accepted schemas are not modified:

```text
CodeV5Analysis
CodeV6Analysis
XtProjectionMetrics
XtProjectionSet
XtWavetableTrajectory
XtTrajectoryQcAnalysis
XtHardwarePackageAnalysis
XtWaveOptimization
XtWaveSetOptimization
```

CODE V8-0E adds linked repair contracts. Version `0.7.0` remains unchanged.

## Local design validation

```text
compileall                              : PASS on isolated V8-0E source bundle
V8-0E isolated targeted suite          : 126 passed
V8-0D targeted regression              : 94 passed
Complete isolated public suite         : 1466 passed, 4 skipped
canonical defect count                 : 17 exact
canonical action count                 : 17 exact
canonical policy count                 : 4 exact
all findings and actions ordered       : PASS
AUTO selected branch                   : PASS
COMPARE candidate isolation            : PASS
IGNORE source preservation             : PASS
PRESERVE intentional preservation      : PASS
context refusal and review states      : PASS
metadata-only pitch action             : PASS
61-wave sequence operation             : PASS
NaN, infinity, and overflow rejection  : PASS
serialization and deterministic hashes : PASS
historical public schemas unchanged    : PASS
```

The four public skips are the existing private real-dump tests because private evidence is not stored in the repository.

## Target-environment gates still required

```text
[ ] compileall passes in the target repository
[ ] pip check passes in the target environment
[ ] V8-0E targeted suite passes in the target repository
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

- Every required defect has a dedicated deterministic detector and action mapping.
- Every result contains one finding and one action record for every canonical defect.
- AUTO actions are selected only when the relevant evidence and context are sufficient.
- COMPARE actions never modify the selected branch.
- IGNORE and PRESERVE never modify samples and remain distinguishable in the log.
- A metadata-only correction is not falsely reported as a sample mutation.
- Unavailable neighbor, reference, pitch, or aliasing evidence is never fabricated.
- Before, candidate, and selected samples and metrics are always available.
- Sequence processing preserves canonical order and supports exactly 61 waves.
- All output models reject NaN and infinity.
- No output sample exceeds the normalized range `[-1, 1]`.
- No MIDI or SysEx transmission path is introduced.

## Safety boundary

CODE V8-0E opens no MIDI port, transmits no SysEx, modifies no instrument state, and commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
