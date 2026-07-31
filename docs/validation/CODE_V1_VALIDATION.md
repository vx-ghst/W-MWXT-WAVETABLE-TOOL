# W-MWXT-WAVETABLE-TOOL
## CODE V1 Public Validation Report

**Project:** W-MWXT-WAVETABLE-TOOL  
**Version:** `0.1.0`  
**Milestone:** CODE V1 — deterministic Microwave XT SysEx core  
**Reference date:** 2026-07-30  
**Status:** **PASS**

---

# 1. Scope validated

CODE V1 validates the deterministic SysEx foundation:

- concatenated SysEx message splitting;
- strict `F0` / `F7` framing;
- Waldorf manufacturer identifier;
- Microwave II/XT equipment identifier;
- Device ID;
- dump type;
- address decoding;
- expected message length;
- payload checksum;
- typed Sound, Multi, User Wave, User Wavetable, and Global models;
- MIDI-safe nibble encoding and decoding;
- User Wave payload decoding;
- explicit second-half reconstruction policy;
- User Wavetable reference decoding;
- 16-character Sound name handling;
- Universal Device Identity reply decoding;
- byte-identical decode/re-encode round trips;
- CLI inspection, validation, identity, and round-trip commands.

---

# 2. Reference instrument

```text
Instrument          : Waldorf Microwave XT
Polyphony            : 10 voices
Mainboard            : non-expandable revision
Device ID            : 00
Operating system     : 2.33
Identity reply       : F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7
```

Decoded identity:

```json
{
  "manufacturer_id": "0x3E",
  "family_code": "0x000E",
  "member_code": "0x0003",
  "version": "2.33",
  "xt_10_voice_non_expandable": true
}
```

---

# 3. Global result

- Reference dump files validated: **4**
- Total SysEx messages parsed: **1,461**
- Known structures and checksums valid: **yes**
- Strict byte-identical round trips: **yes**
- Independently captured Everything backups identical: **yes**
- Automated tests: **16 passed**
- Failed tests: **0**

The private binary dump files are not included in the public repository.

---

# 4. Public reference fingerprints

## 4.1 All Sounds

```text
Size        : 67,840 bytes
SHA-256     : 5a0996e68b183e9ca3af5e2f0996945bd13493ba987f5d9af2d13673dd17451
Messages    : 256
Types       : SOUND × 256
Length      : 265 bytes × 256
Round trip  : byte-identical
Issues      : 0
```

## 4.2 All Wavetables & Waves

```text
Size        : 42,730 bytes
SHA-256     : 19e24c0c58a45eeb22e80268e156d4baa594debc2aed3a17bb17150ea6878808
Messages    : 282
Types       : USER_WAVE × 250
              USER_WAVETABLE × 32
Lengths     : 137 bytes × 250
              265 bytes × 32
Round trip  : byte-identical
Issues      : 0
```

## 4.3 Everything reference backup

```text
Size        : 144,529 bytes
SHA-256     : 4488e5fcb1a1991f429ff76044ea5f3bcba3061c3cc11ba60401f626d3510244
Messages    : 667
Types       : GLOBAL × 1
              MULTI × 128
              SOUND × 256
              USER_WAVE × 250
              USER_WAVETABLE × 32
Lengths     : 137 bytes × 250
              265 bytes × 416
              39 bytes × 1
Round trip  : byte-identical
Issues      : 0
```

Two independently captured Everything backups produced the same size and SHA-256 fingerprint.

---

# 5. Confirmed dump inventory

```text
Sounds                         : 256
Sound display locations        : A001–A128, B001–B128
Multis                         : 128
User Waves                     : 250
User Wave numbers              : 1000–1249
User Wavetables                : 32
Observed internal table range  : 96–127
Corresponding display range    : 097–128
Global messages                : 1
Reference Device ID            : 00
```

Observed message formats:

| Message | Type | Payload | Complete message |
|---|---:|---:|---:|
| Sound | `10h` | 256 bytes | 265 bytes |
| Multi | `11h` | 256 bytes | 265 bytes |
| User Wave | `12h` | 128 nibble bytes | 137 bytes |
| User Wavetable | `13h` | 256 nibble bytes | 265 bytes |
| Global | `14h` | 30 bytes | 39 bytes |

---

# 6. Automated tests

```text
test_14bit_codec_boundaries
test_byte_nibble_roundtrip
test_u16_nibble_roundtrip
test_invalid_nibble_is_rejected
test_users_xt_identity_reply
test_synthetic_message_roundtrip
test_checksum_is_payload_sum_modulo_128
test_corrupt_checksum_is_rejected
test_bad_framing_is_rejected
test_user_wave_roundtrip_and_reconstruction
test_user_wavetable_roundtrip
test_sound_name_field
test_all_four_real_dumps_validate_and_roundtrip
test_reference_backups_are_byte_identical
test_sound_addresses_and_names
test_real_user_wave_and_wavetable_ranges
```

Result:

```text
16 passed
0 failed
0 errors
```

Public CI does not require the private hardware dump files. The hardware-backed tests are skipped when the private dump directory is unavailable.

---

# 7. Reproduction commands

Install the project in a virtual environment:

```powershell
python -m pip install -e ".[dev]"
```

Run public tests:

```powershell
Remove-Item Env:W_MWXT_DUMP_DIR -ErrorAction SilentlyContinue
.\run_tests.ps1
```

Expected public result:

```text
12 passed, 4 skipped
```

Run the full private reference suite:

```powershell
$env:W_MWXT_DUMP_DIR = "D:\PRIVATE-DUMP-DIRECTORY"
.\run_tests.ps1
```

Expected private result:

```text
16 passed
```

Validate and round-trip all private dumps:

```powershell
.\validate_dumps.ps1 -DumpDirectory "D:\PRIVATE-DUMP-DIRECTORY"
```

Expected result for every reference file:

```text
OK
IDENTICAL
```

---

# 8. CODE V1 acceptance gate

```text
[x] Deterministic SysEx core
[x] Strict framing and identifier validation
[x] Checksum validation
[x] Typed data models
[x] User Wave decode/re-encode
[x] User Wavetable decode/re-encode
[x] Sound name handling
[x] Universal Device Identity decoding
[x] Four reference dump files validated
[x] Four byte-identical round trips
[x] Two Everything backups identical
[x] Sixteen automated tests passed
[x] Private SysEx files excluded from Git
```

---

# 9. Deliberate CODE V1 limits

CODE V1 does not yet implement:

- destination allocation;
- write-package generation;
- audio import;
- DSP analysis;
- User Wave generation;
- new Wavetable construction;
- complete Sound generation;
- MIDI transmission;
- automated read-back;
- audio simulation.

Those features begin at CODE V2 and later stages.

---

# 10. Milestone decision

```text
Milestone       : CODE V1
Result          : PASS
Version         : v0.1.0
Next authorized : CODE V2 — safe SysEx package builder
```

Any future claim about real hardware write behavior, interpolation, reconstruction, or audio output must still pass its mapped hardware gate.
