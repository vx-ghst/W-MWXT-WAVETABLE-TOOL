# CODE V7-F Validation — Hardware and Release Closure

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V7-F
Branch  : code-v7-xt-native-optimization
Base    : f994c43526923455eabfb59656f52e520e0391ff
Release : 0.7.0
```

## Accepted targets

```text
Device ID             : 0
User Waves            : 1189..1249
User Wavetable        : display 128 / internal 127
Sound                 : B128
Controlled Sound name : ODIUM KEY V7E
Messages              : 63
```

## Canonical package evidence

```text
Package SHA-256 : 82724d493c889afe27a44f0550355bce1764e0054621f4a35b373c9c8f08c425
Restore SHA-256 : a1ee24820a1dd77b5e283d3595d160cc8cbb8ee08a176f980eea9adf913861d6
```

## Hardware gates

```text
First installation : 63/63 PASS_EXACT
Audio acceptance    : PASS
Restore             : 63/63 PASS_EXACT
Final installation : 63/63 PASS_EXACT
```

Audio acceptance covered MIDI notes 36, 48, and 60 plus a manual Startwave sweep from `00` to `60`, with zero clipping and no silent region, violent internal click, abrupt level drop, or corrupted wave.

## Pre-release software baseline

```text
Baseline commit  : f994c43526923455eabfb59656f52e520e0391ff
pip check        : PASS
compileall       : PASS
Public suite     : 1027 passed, 4 skipped
Private suite    : 1031 passed
Repository state : clean before and after
```

## Final pre-commit software validation

```text
Editable package version : 0.7.0
Distribution version     : 0.7.0
CLI version              : 0.7.0
Targeted migration suite : 292 passed
Final public suite       : 1035 passed, 4 skipped
Final private suite      : 1039 passed
git diff --check         : PASS
Public evidence leakage  : NONE
Private binaries in Git  : NONE
```

## Release gate status

1. version metadata declares `0.7.0`: **PASS**;
2. editable distribution metadata is refreshed: **PASS**;
3. targeted V6/V7 release tests pass: **PASS**;
4. public and private complete suites pass: **PASS**;
5. documentation agrees on `0.7.0`: **PASS**;
6. `git diff --check` passes: **PASS**;
7. no private evidence enters Git: **PASS**;
8. release commit, pull request, merge, and tag `v0.7.0`: **PENDING**.

## Safety boundary

All hardware transmission was manual and external to the application. Private source dumps, redumps, generated SysEx files, audio captures, and detailed private evidence remain outside Git.
