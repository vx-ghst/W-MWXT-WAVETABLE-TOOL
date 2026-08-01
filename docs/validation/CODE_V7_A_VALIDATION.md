# CODE V7-A Validation — XT Reconstruction and Symmetry Hardware Gate

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V7-A
Branch  : code-v7-xt-native-optimization
Version : 0.6.0 (unchanged until CODE V7-F)
```

## Purpose

CODE V7-A prevents the XT-native optimizer from freezing an unverified 64/128-point reconstruction model.

The established wire fact is:

```text
one WAVD payload = 128 MIDI-safe nibbles = 64 signed int8 stored samples
```

A WAVD redump can prove that these 64 values survived transmission and storage. It cannot, by itself, expose the oscillator's internal samples 64–127. CODE V7-A therefore separates two gates that earlier wording risked conflating:

```text
Gate 1 — protocol/storage gate
    send WAVD → redump WAVD → compare 64 stored values

Gate 2 — reconstruction gate
    obtain an independent phase-aligned 128-sample observation
    → compare every supported reconstruction hypothesis
    → require one unique exact match
```

No nearest-match heuristic is allowed to decide the architecture.

## Delivered contract

Public subpackage:

```text
w_mwxt_wavetable_tool.xt
```

Models and functions:

```text
XtGatePattern
XtReconstructionHypothesis
XtProbeStorageStatus
XtGateStatus
XtGateVerdict
XtGateProbe
XtReconstructionGatePlan
XtGateBuild
XtProbeReadbackEvidence
XtHypothesisScore
XtGateAnalysis
XtGateAnalysisResult
generate_xt_gate_probes
build_xt_reconstruction_gate
analyze_xt_reconstruction_gate
verify_xt_reconstruction_gate_restore
parse_observation_document
reconstruct_probe
```

Focused CLI:

```text
W-MWXT-XT-GATE
```

Commands:

```text
build
analyze
verify-restore
```

## Diagnostic probes

Three deterministic probes are used on three consecutive User Wave destinations:

1. `indexed_asymmetric` — distinguishes direct, mirror, repeat, and sign transforms;
2. `edge_extremes` — includes `-128` and `+127` to distinguish mathematical, wrapped-int8, and saturated negation;
3. `seeded_random` — reduces accidental agreement with a simple unmodeled transform.

Each probe records both:

```text
stored_samples          : 64 values actually encoded in WAVD
requested_full_samples  : 128-value intentionally asymmetric diagnostic source
```

The generated manifest is hashed and preserves the exact probes, destinations, baseline identity, package identity, restore identity, and evidence boundary.

## Supported reconstruction hypotheses

```text
preserve_requested_128
zero_fill_second_half
repeat_first_half
mirror_first_half
negate_first_half
reverse_negate_mathematical
reverse_negate_wrap_i8
reverse_negate_saturate_i8
```

The `edge_extremes` probe makes the three reversed-antisymmetry edge policies distinguishable at `-128`.

## Gate outcomes

### Storage exact, no independent observation

```text
status  : pending_observation
verdict : protocol_storage_confirmed_reconstruction_unresolved
action  : do_not_freeze_symmetry_optimizer
```

### One unique hypothesis

```text
status  : pass
verdict : hypothesis-specific hardware verdict
action  : V7-B may freeze the corresponding representation
```

### Multiple or zero hypotheses

```text
status  : inconclusive
action  : improve measurement or add a tested hypothesis
```

### WAVD read-back mismatch

```text
status  : fail
verdict : readback_failed
action  : resolve transmission, addressing, protocol, or decoder mismatch first
```

## Safe hardware workflow

Build the gate from a verified pre-write Everything backup:

```powershell
W-MWXT-XT-GATE build `
  "D:\W-MWXT-PRIVATE-DUMPS\everything-before.syx" `
  --target-wave-start 1247 `
  --output-dir "D:\W-MWXT-V7A-GATE"
```

The command generates:

```text
CODE_V7_A_XT_RECONSTRUCTION_GATE.probe.syx
CODE_V7_A_XT_RECONSTRUCTION_GATE.restore.syx
CODE_V7_A_XT_RECONSTRUCTION_GATE.manifest.json
CODE_V7_A_XT_RECONSTRUCTION_GATE.manifest.md
CODE_V7_A_XT_RECONSTRUCTION_GATE.observation-template.json
```

After manual transmission and a fresh redump:

```powershell
W-MWXT-XT-GATE analyze `
  "D:\W-MWXT-V7A-GATE\CODE_V7_A_XT_RECONSTRUCTION_GATE.probe.syx" `
  "D:\W-MWXT-V7A-GATE\readback-after-probe.syx" `
  "D:\W-MWXT-V7A-GATE\CODE_V7_A_XT_RECONSTRUCTION_GATE.manifest.json" `
  --output-dir "D:\W-MWXT-V7A-GATE"
```

Without an independent 128-point observation, the expected correct result is `pending_observation`, not `pass`.

When a valid observation document exists:

```powershell
W-MWXT-XT-GATE analyze `
  "D:\W-MWXT-V7A-GATE\CODE_V7_A_XT_RECONSTRUCTION_GATE.probe.syx" `
  "D:\W-MWXT-V7A-GATE\readback-after-probe.syx" `
  "D:\W-MWXT-V7A-GATE\CODE_V7_A_XT_RECONSTRUCTION_GATE.manifest.json" `
  --observations "D:\W-MWXT-V7A-GATE\observed-128.json" `
  --output-dir "D:\W-MWXT-V7A-GATE"
```

Restore immediately after the experiment, redump the targets, then verify:

```powershell
W-MWXT-XT-GATE verify-restore `
  "D:\W-MWXT-V7A-GATE\CODE_V7_A_XT_RECONSTRUCTION_GATE.restore.syx" `
  "D:\W-MWXT-V7A-GATE\readback-after-restore.syx" `
  "D:\W-MWXT-V7A-GATE\CODE_V7_A_XT_RECONSTRUCTION_GATE.manifest.json" `
  --output-dir "D:\W-MWXT-V7A-GATE"
```

## Safety boundary

CODE V7-A:

- never transmits MIDI automatically;
- never selects destinations without an explicit target range;
- requires an existing baseline copy of all three targets;
- creates an exact restore bundle before transmission;
- refuses a probe payload that equals its baseline target;
- verifies strict SysEx round-trips;
- refuses to infer oscillator reconstruction from WAVD read-back alone;
- does not quantize V6 reconstructed waves;
- does not implement the V7-B symmetry optimizer.

## Automated validation

```text
Core gate, manifest, hypothesis, read-back, and restore tests : 10
Focused CLI tests                                           : 3
Public subpackage API test                                  : 1
Targeted total                                              : 14
```

## Current acceptance state

```text
Software harness       : PASS
Deterministic probes   : PASS
Storage analyzer       : PASS
Hypothesis comparator  : PASS
Restore verification   : PASS
Physical XT write      : PENDING
Physical WAVD redump   : PENDING
Independent 128 points : PENDING
Final hardware verdict : PENDING
```

CODE V7-A is not hardware-closed until the physical test produces a unique, independently supported reconstruction verdict and the restore read-back passes exactly. CODE V7-B must remain blocked until that point.
