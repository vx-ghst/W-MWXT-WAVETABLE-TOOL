# CODE V6-F Validation — Aggregate and Release Closure

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V6-F
Branch  : code-v6-cycle-engine
Base    : 84abcacfbcd84f36a409e7e4077110e5d3b13d2d
Release : 0.6.0
```

## Delivered contract

CODE V6-F adds:

```text
CodeV6Analysis
assemble_code_v6_analysis
analyze_audio_source_code_v6
analyze-code-v6
```

The aggregate embeds the accepted CODE V5 analysis and every V6 component. It enforces sample-rate, sample-count, sample-SHA, tool-version, component-hash, upstream-analysis, selected-candidate, ranking, and reconstruction links before producing one final canonical SHA-256.

## Targeted validation

The CODE V6-F targeted suite consists of:

```text
tests/test_analysis_code_v6.py
tests/test_cli_code_v6.py
tests/test_public_api_v6f.py
tests/test_release_v6.py
```

Expected targeted total: `55 passed`.

## Required release gates

1. targeted V6-F suite passes;
2. two real-audio `analyze-code-v6` reports are byte-identical;
3. source audio is byte-identical before and after analysis;
4. every CODE V5 and V6 component hash is valid and linked;
5. final aggregate SHA-256 is independently reproducible;
6. public complete suite passes with only the four private-reference skips;
7. private complete suite passes with zero skips and zero failures;
8. version, package metadata, CLI, README, changelog, roadmap, and release notes all declare `0.6.0`;
9. no private audio, SysEx, project, capture, dump, or generated JSON report enters Git;
10. branch commit is pushed, reviewed through a pull request, merged into `main`, and tagged `v0.6.0`.

## Baseline evidence retained from V6-E

```text
Targeted V6-E : 58 passed
Real audio    : 33/33 controls
Public suite  : 900 passed, 4 skipped
Private suite : 904 passed
```

Final V6-F totals and release identifiers are appended only after their respective gates pass.
