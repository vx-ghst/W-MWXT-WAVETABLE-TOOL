# CODE V7 Release — 0.7.0

## Scope

CODE V7 completes the first hardware-validated XT-native engineering path of **W-MWXT-WAVETABLE-TOOL**: documented User Wave coding, safe XT-native projection, a complete 61-position trajectory, deterministic QC, deterministic package generation, exact restoration, and physical hardware acceptance.

## Delivered stages

```text
CODE V7-A     — reconstruction hardware gate
CODE V7-A.1   — offset-binary and reconstruction correction
CODE V7-A.2   — controlled XT audio gate
CODE V7-A.2.1 — complete 16-capture corpus
CODE V7-B     — deterministic 128-to-64 projection
CODE V7-C     — deterministic 61-position trajectory
CODE V7-D     — trajectory QC and previews
CODE V7-E     — deterministic hardware package dry-run
CODE V7-F     — write, restore, final installation, and release closure
```

## Accepted XT contract

```text
wire coding     : offset binary with MSB flip
stored points   : 64
logical points  : 128
reconstruction  : second_half[n] = -first_half[63 - n]
safe generation : -127..127
excluded edge   : -128
```

## Hardware package

```text
61 User Wave WAVD messages
 1 User Wavetable WCTD message
 1 controlled Sound SNDD message
63 messages total
```

Package SHA-256: `82724d493c889afe27a44f0550355bce1764e0054621f4a35b373c9c8f08c425`
Restore SHA-256: `a1ee24820a1dd77b5e283d3595d160cc8cbb8ee08a176f980eea9adf913861d6`

## Physical acceptance

```text
First installation : 63/63 exact
Restore             : 63/63 exact
Final installation : 63/63 exact
Audio acceptance    : PASS
```

## Software validation

```text
pip check                  : PASS
compileall                  : PASS
Pre-release public baseline : 1027 passed, 4 skipped
Pre-release private baseline: 1031 passed
Targeted migration suite    : 292 passed
Final public suite          : 1035 passed, 4 skipped
Final private suite         : 1039 passed
git diff --check            : PASS
Public/private leakage      : PASS
Repository integrity        : PASS
```

## Safety boundary

No CODE V7 command opens a MIDI port or transmits SysEx automatically. Private dumps, generated SysEx, restore files, captures, and private evidence are excluded from the public repository.
