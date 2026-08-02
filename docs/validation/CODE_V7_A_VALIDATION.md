# CODE V7-A.1 Validation - Documented XT User Wave Coding and Reconstruction

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V7-A.1
Branch  : code-v7-xt-native-optimization
Version : 0.6.0 (unchanged until CODE V7-F)
```

## Reason for the corrective patch

The first CODE V7-A harness correctly separated WAVD storage evidence from an
independent 128-point observation, but it still inherited two provisional CODE V1
assumptions:

1. User Wave sample bytes were interpreted as two's-complement int8;
2. the 64-to-128 reconstruction architecture was treated as wholly unknown.

The Microwave II/XT manual's SysEx appendix resolves both points:

```text
wire sample coding : offset binary; flip the most-significant bit to obtain signed int8
stored points      : 64
logical points     : 128
second half        : negative values of the first half in reverse order
```

Canonical reconstruction for `n = 0..63`:

```text
full[64 + n] = -full[63 - n]
```

The remaining unresolved edge is the negation of signed full-scale `-128`, whose
mathematical result is `+128` and does not fit signed int8.

## Central codec correction

New codec functions:

```text
decode_offset_binary_i8
encode_offset_binary_i8
```

Golden mapping:

| WAVD raw byte | Signed sample |
|---:|---:|
| `00h` | `-128` |
| `01h` | `-127` |
| `7Fh` | `-1` |
| `80h` | `0` |
| `81h` | `+1` |
| `FEh` | `+126` |
| `FFh` | `+127` |

`UserWave.from_message()` now decodes this mapping. `UserWave.payload` applies the
inverse mapping before nibble encoding.

This changes the logical interpretation of real WAVD samples while preserving exact
byte round-trips:

```text
raw WAVD -> corrected logical samples -> raw WAVD
```

must remain byte-identical.

## Documented reconstruction contract

`UserWave.reconstruct()` now defaults to `documented` and implements:

```text
stored[0..63] + (-reverse(stored))[0..63]
```

Explicit diagnostic policies remain available for the `-128` edge:

```text
documented / mathematical : preserve mathematical +128
wrap_i8                    : +128 wraps to -128
saturate_i8                : +128 clamps to +127
```

No normal V7 optimizer may generate `-128` until this edge is characterized on the
physical XT. The temporary safe generation range is:

```text
-127..+127
```

## Gate schema 2

All CODE V7-A.1 gate manifests use schema version `2`. Schema-1 manifests are rejected
with an instruction to rebuild the package because their sample interpretation and
architecture contract are obsolete.

The schema records:

```text
wire_sample_encoding          : offset_binary_msb_flipped
documented_reconstruction_law : second_half[n] = -first_half[63 - n]
safe_optimizer_sample_range   : [-127, 127]
negative_full_scale_behavior  : pending_hardware_characterization
```

## Diagnostic probes

Three deterministic probes use three consecutive User Wave destinations:

1. `indexed_asymmetric` - ordered, non-palindromic safe-range storage pattern;
2. `offset_binary_golden` - repeats the exact raw-byte golden vector;
3. `negative_full_scale_edge` - places `-128` at three known positions.

A WAVD redump validates the 64 transmitted/stored values exactly. The documentation
already establishes the reverse-negate architecture. An optional independent digital
128-point observation is now used only to characterize the `-128` edge.

## Gate outcomes

### Exact WAVD readback, no 128-point observation

```text
status  : pass
verdict : documented_reconstruction_storage_confirmed_edge_unresolved
V7-B    : allowed only with generated samples constrained to -127..+127
```

### Unique documented edge policy

```text
status  : pass
verdict : documented reconstruction plus mathematical/wrap/saturate edge confirmed
```

### Observation conflict

```text
status  : inconclusive
V7-B    : blocked pending measurement review
```

### WAVD mismatch

```text
status  : fail
V7-B    : blocked
```

## Golden package update

Correct offset-binary encoding changes the synthetic CODE V2 golden package bytes.
The package length and structure remain unchanged.

```text
old SHA-256 : e9a6294b78ef41ec85db24850270dfe85228f3a2ea622e33a70bd6df04858caa
new SHA-256 : c2693b7a5203fec1f4c3b0a0a02cd2331507bc1d74b49c50e14771dfc45ae058
bytes       : 8887
messages    : 63
```

The new hash was independently reproduced from the documented message framing,
offset-binary sample conversion, nibble packing, addresses, checksums, WCTD references,
and SNDD payload.

## Focused automated validation

```text
offset-binary codec and UserWave tests : 5
CODE V7-A.1 gate core tests            : 10
focused CLI tests                      : 3
public XT subpackage API test          : 1
targeted total                         : 19
```

Targeted result during patch construction:

```text
19 passed
```

## Required repository validation after application

Public suite:

```powershell
Remove-Item Env:W_MWXT_DUMP_DIR -ErrorAction SilentlyContinue
& ".\.venv\Scripts\python.exe" -m pytest -q
```

Private suite:

```powershell
$env:W_MWXT_DUMP_DIR = "D:\W-MWXT-PRIVATE-DUMPS"
& ".\.venv\Scripts\python.exe" -m pytest -q
```

Private acceptance requires all four real dumps to remain byte-identical after decode
and re-encode. This is the critical proof that correcting the logical amplitude meaning
did not alter archival SysEx bytes.

## Hardware workflow after software validation

1. rebuild a schema-2 gate package from a fresh pre-write Everything backup;
2. transmit the three WAVD probes manually;
3. redump the three destinations or All Wavetables & Waves;
4. run `W-MWXT-XT-GATE analyze`;
5. require exact storage evidence;
6. restore the generated bundle;
7. redump again and run `verify-restore`;
8. keep `-128` excluded from V7-B until its edge behavior is measured.

## Safety boundary

CODE V7-A.1:

- never transmits MIDI automatically;
- never reuses a schema-1 manifest;
- requires a baseline copy of all overwritten User Waves;
- creates a restore bundle before transmission;
- validates offset-binary storage by exact readback;
- uses the documented reverse-negate law;
- does not implement the V7-B optimizer;
- does not permit normal generation of `-128`.
