# W-MWXT-WAVETABLE-TOOL

**W-MWXT-WAVETABLE-TOOL** is a public Python project for wave and wavetable engineering on the **Waldorf Microwave XT**.

The project is developed in controlled stages. **CODE V1** establishes a deterministic SysEx foundation: it reads, validates, models, and re-encodes Microwave XT dumps without changing a byte. Audio import, DSP analysis, wavetable optimization, package generation, hardware-calibrated preview, and the graphical editor are later stages.

> **Status:** early development — CODE V1  
> **Distribution and CLI:** `W-MWXT-WAVETABLE-TOOL`  
> **Python import package:** `w_mwxt_wavetable_tool`  
> **Primary platform:** Windows 11  
> **Python:** 3.11 or newer

## Project objective

The long-term objective is a dedicated Microwave XT wavetable engineering environment able to:

- import clean WAV, AIFF, and FLAC files;
- convert imported audio to mono automatically;
- analyze pitch, periodicity, phase, cycles, and spectral evolution;
- optimize source material for Microwave XT User Waves;
- select and place useful waves across the programmable table positions;
- create a User Wavetable and a named Sound patch;
- export one ordered `.syx` package containing the required User Waves, User Wavetable, and Sound patch;
- preview and validate the result before transmission to the hardware.

These are roadmap targets. CODE V1 implements only the SysEx core described below.

## CODE V1 capabilities

- strict splitting of binary files containing concatenated SysEx messages;
- strict `F0` / `F7` framing validation;
- validation of Waldorf manufacturer ID `3E`;
- validation of Microwave II/XT equipment ID `0E`;
- Device ID, dump type, and 14-bit address decoding;
- checksum validation using `sum(payload) & 0x7F`;
- typed models for:
  - Sound programs (`SNDD`, type `10h`);
  - Multi programs (`MULT`, type `11h`);
  - User Waves (`WAVD`, type `12h`);
  - User Wavetables (`WCTD`, type `13h`);
  - Global parameters (`GLOBAL`, type `14h`);
- MIDI-safe nibble encoding and decoding;
- decoding of the 64 signed samples stored in a User Wave dump;
- explicit reconstruction policies for the second 64 samples;
- decoding of the 64 references stored in a User Wavetable control table;
- reading and editing the 16-character Sound name;
- Universal Device Identity reply decoding;
- byte-identical decode/re-encode round trips;
- CLI inspection, validation, and round-trip commands;
- synthetic unit tests and validation against four real hardware dumps.

## Hardware validation reference

CODE V1 has been validated against dumps captured from this physical instrument:

```text
Model:            Waldorf Microwave XT
Polyphony:        10 voices
Mainboard:        non-expandable
Device ID:        00
Operating system: 2.33
Identity reply:   F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7
```

The private hardware dumps are not included in this public repository. Their file sizes and SHA-256 fingerprints are recorded in `reference_dumps/reference_manifest.json` so the validation can be reproduced locally without publishing synth content.

## Formats confirmed by the reference dumps

| Message | Type ID | Payload | Complete message | Count in an Everything dump |
|---|---:|---:|---:|---:|
| Sound program | `10h` | 256 bytes | 265 bytes | 256 |
| Multi program | `11h` | 256 bytes | 265 bytes | 128 |
| User Wave | `12h` | 128 bytes | 137 bytes | 250 |
| User Wavetable | `13h` | 256 bytes | 265 bytes | 32 |
| Global parameters | `14h` | 30 bytes | 39 bytes | 1 |

Common message layout:

```text
F0 3E 0E <device> <type> <address_msb_7bit> <address_lsb_7bit>
<payload> <sum(payload) & 7F> F7
```

Recorded validation result:

- four hardware dump files parsed successfully;
- all known message lengths valid;
- all checksums valid;
- every decode/re-encode round trip byte-identical;
- two independently saved Everything dumps byte-identical;
- 16 automated tests passed.

See `reports/reference_validation.md` and `reports/pytest_reference.txt`.

## Installation on Windows 11

Open PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Check the installed CLI:

```powershell
W-MWXT-WAVETABLE-TOOL --help
```

## Command-line usage

### Inspect a dump

```powershell
W-MWXT-WAVETABLE-TOOL inspect "D:\Dumps\WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22.syx"
```

### Validate one or more dumps

```powershell
W-MWXT-WAVETABLE-TOOL validate "D:\Dumps\WALDORF_MWXT_ALL_SOUNDS.syx"
```

### Verify a byte-identical round trip

```powershell
W-MWXT-WAVETABLE-TOOL roundtrip "D:\Dumps\WALDORF_MWXT_ALL_WAVETABLES_AND_WAVES.syx"
```

Expected result:

```text
IDENTICAL
```

### Decode a Universal Device Identity reply

```powershell
W-MWXT-WAVETABLE-TOOL identity "F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7"
```

## Running tests

Synthetic tests only:

```powershell
python -m pytest -v
```

Complete validation with the four private dumps:

```powershell
$env:W_MWXT_DUMP_DIR = "D:\Dumps\MicrowaveXT"
python -m pytest -v
```

The files must use the exact names and fingerprints recorded in `reference_dumps/reference_manifest.json`.

PowerShell helpers:

```powershell
.\run_tests.ps1
.\validate_dumps.ps1 -DumpDirectory "D:\Dumps\MicrowaveXT"
```

## Repository layout

```text
W-MWXT-WAVETABLE-TOOL/
├── .github/workflows/tests.yml
├── src/w_mwxt_wavetable_tool/
│   ├── __init__.py
│   ├── cli.py
│   ├── codec.py
│   ├── constants.py
│   ├── dump.py
│   ├── errors.py
│   ├── identity.py
│   ├── message.py
│   └── models.py
├── tests/
├── tools/
├── reference_dumps/
├── reports/
├── .gitignore
├── CHANGELOG.md
├── pyproject.toml
├── README.md
├── run_tests.ps1
└── validate_dumps.ps1
```

## Roadmap

### CODE V1 — deterministic SysEx core

- [x] Parse concatenated Microwave XT SysEx streams
- [x] Validate framing, identifiers, addresses, lengths, and checksums
- [x] Model Sound, Multi, User Wave, User Wavetable, and Global data
- [x] Decode and re-encode User Wave and Wavetable nibble payloads
- [x] Decode the hardware identity response
- [x] Achieve byte-identical round trips on real dumps

### CODE V2 — safe SysEx package builder

- [ ] Allocate consecutive User Wave locations safely
- [ ] Select a User Wavetable destination
- [ ] Select a Sound destination or edit buffer
- [ ] Set and validate a 16-character Sound name
- [ ] Build one ordered `.syx` package containing User Waves, User Wavetable, and Sound patch
- [ ] Detect address collisions and range overflows
- [ ] Produce a human-readable package manifest
- [ ] Add golden-vector tests for generated packages

### Later stages

- [ ] WAV, AIFF, and FLAC import
- [ ] Automatic mono conversion
- [ ] Pitch, periodicity, cycle, phase, and spectral analysis
- [ ] Microwave XT User Wave optimization
- [ ] Intelligent selection and placement of useful waves
- [ ] Transition generation across the programmable positions
- [ ] Hardware-calibrated wavetable preview and simulation
- [ ] Direct MIDI transmission with read-back verification
- [ ] Graphical wavetable editor and analysis interface

## Safety

SysEx writes can overwrite Sounds, User Waves, User Wavetables, Multis, or global settings.

Before transmitting generated data:

1. create an Everything backup;
2. verify the target Device ID;
3. verify every destination address;
4. inspect the generated package manifest;
5. transmit only after confirming what will be overwritten.

CODE V1 does not transmit data and does not generate final write packages.

## Determinism and traceability

The project follows two rules:

1. automatic decisions must be explained by recorded measurements and rules;
2. identical source data and configuration must produce identical output.

## Public repository and licensing

The repository is public. The package metadata currently uses the license text `Private project`, as requested by the project owner. This phrase is not a standard open-source license and does not itself define reuse, modification, or redistribution rights. A formal `LICENSE` file can be selected later without changing the CODE V1 implementation.

## Contributing

Contributions must preserve strict protocol validation, deterministic behavior, byte-level tests, and the separation between SysEx, DSP, interface, and transport layers.

Do not submit proprietary factory dumps, personal backups, copyrighted sound banks, or firmware images.

## Disclaimer

W-MWXT-WAVETABLE-TOOL is an independent, unofficial project. It is not affiliated with, endorsed by, or supported by Waldorf Music.

Use generated SysEx data at your own risk and keep a verified backup before writing to the instrument.
