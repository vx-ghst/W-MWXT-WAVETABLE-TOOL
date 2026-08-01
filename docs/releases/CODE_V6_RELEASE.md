# CODE V6 Release — 0.6.0

## Scope

CODE V6 completes the deterministic source-to-cycle engineering layer of **W-MWXT-WAVETABLE-TOOL**. It adds working-pitch planning, source segmentation, cycle discovery, representative ranking and top-N selection, spectral/partial/hybrid reconstruction, and the final immutable `CodeV6Analysis` aggregate.

## Delivered stages

```text
CODE V6-A — working pitch and repitch policy
CODE V6-B — segmentation and attack policy
CODE V6-C — cycle discovery and metrics
CODE V6-D — representative ranking and top-N selection
CODE V6-E — spectral, partial, and hybrid reconstruction
CODE V6-F — aggregate, CLI, documentation, and release closure
```

## Final aggregate

`CodeV6Analysis` contains and validates:

```text
CodeV5Analysis
WorkingPitchPlan
SegmentationAnalysis
CycleDiscoveryAnalysis
SelectedCycleSet
ReconstructedWaveSet
```

The aggregate preserves one canonical sample identity and verifies the complete CODE V5 → V6 SHA-256 chain, including selected candidate indexes, candidate hashes, ranking hashes, source-cycle hashes, reconstructed-wave hashes, component hashes, and one final `analysis_sha256`.

## Final CLI

```powershell
W-MWXT-WAVETABLE-TOOL analyze-code-v6 `
  "D:\Audio\source.wav" `
  --pitch-policy auto `
  --attack-policy auto `
  --selection-policy auto `
  --top-n 16 `
  --reconstruction-strategy auto `
  --target-sample-count 128 `
  --report "D:\Reports\source.code-v6.json"
```

Focused commands remain available: `pitch-plan`, `segment-audio`, `discover-cycles`, `select-cycles`, and `reconstruct-waves`. The stable CODE V5 `analyze-audio` command remains available for compatibility.

## Safety boundary

CODE V6 does not:

- alter or overwrite source audio;
- quantize float waves to XT 8-bit values;
- allocate User Wave or User Wavetable destinations;
- generate or transmit SysEx;
- modify Microwave XT memory;
- execute any irreversible action.

CODE V7 remains responsible for XT-native representation, symmetry, resampling, quantization, optimization, and Auto Repair.

## Validation history

```text
V6-A targeted: 58 passed
V6-B targeted: 58 passed
V6-C targeted: 58 passed
V6-D targeted: 58 passed
V6-E targeted: 58 passed
V6-E public baseline: 900 passed, 4 skipped
V6-E private baseline: 904 passed
V6-A through V6-E real-audio gates: PASS
```

The final V6-F validation, full-suite totals, deterministic aggregate evidence, commit, pull request, merge commit, and tag are recorded in `docs/validation/CODE_V6_F_VALIDATION.md` and the release workflow.
