# W-MWXT

**W-MWXT** is a public Python toolkit for engineering, validating, and eventually generating wavetables and SysEx packages for the **Waldorf Microwave XT**.

The project is being developed in controlled stages. The current release, **CODE V1**, focuses exclusively on a deterministic and reversible SysEx core. Audio analysis, wavetable optimization, package generation, and hardware simulation belong to later stages and are not presented as finished features.

> **Project status:** early development / CODE V1  
> **Current package:** `mwxt-sysex`  
> **Primary platform:** Windows 11  
> **Python:** 3.11 or newer

## Why this project exists

W-MWXT is intended to become a dedicated wavetable engineering environment for the Microwave XT rather than a generic audio converter.

The long-term objective is to provide a reproducible workflow that can:

- import clean WAV, AIFF, and FLAC sources;
- analyze pitch, periodicity, phase, cycles, and spectral evolution;
- optimize source material for the Microwave XT User Wave format;
- construct and place User Waves and User Wavetables safely;
- generate a named Microwave XT patch referencing the generated table;
- export one self-contained `.syx` file containing the required User Waves, User Wavetable, and patch;
- preview and validate the resulting wavetable behavior before transmission.

These functions are roadmap targets. **CODE V1 currently implements only the SysEx foundation described below.**

## CODE V1 capabilities

CODE V1 provides a deterministic Python core for reading, validating, modeling, and re-encoding Microwave II/XT/XTk SysEx data.

Implemented features:

- strict splitting of files containing concatenated SysEx messages;
- validation of `F0` / `F7` framing;
- validation of Waldorf manufacturer ID `3E`;
- validation of Microwave II/XT family ID `0E`;
- Device ID, message type, and 14-bit address decoding;
- Waldorf checksum validation using `sum(payload) & 0x7F`;
- typed models for:
  - Sound programs (`SNDD`);
  - Multi programs (`MULT`);
  - User Waves (`WAVD`);
  - User Wavetables (`WCTD`);
  - Global parameters (`GLOBAL`);
- nibble encoding and decoding;
- decoding of the 64 stored signed samples in a User Wave message;
- decoding of the 64 wave references in a User Wavetable control table;
- reading and editing 16-character patch names;
- Universal Device Identity response decoding;
- byte-identical decode/re-encode round trips;
- command-line inspection, validation, and round-trip checks;
- synthetic unit tests and validation against four real hardware dumps.

## Hardware validation reference

The current implementation has been validated against dumps captured from this physical unit:

```text
Model:           Waldorf Microwave XT
Polyphony:       10 voices
Mainboard:       non-expandable
Device ID:       00
Operating system: 2.33
Identity reply:  F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7
```

The private hardware dumps are **not included in this public repository**. Only their sizes and SHA-256 fingerprints are retained in `reference_dumps/reference_manifest.json` so local validation can be reproduced without publishing personal synth data.

## Formats confirmed by the reference dumps

| Message | Type ID | Payload | Full message | Count in an Everything dump |
|---|---:|---:|---:|---:|
| Sound program | `10h` | 256 bytes | 265 bytes | 256 |
| Multi program | `11h` | 256 bytes | 265 bytes | 128 |
| User Wave | `12h` | 128 bytes | 137 bytes | 250 |
| User Wavetable | `13h` | 256 bytes | 265 bytes | 32 |
| Global parameters | `14h` | 30 bytes | 39 bytes | 1 |

Common message structure:

```text
F0 3E 0E <device> <type> <address_msb_7bit> <address_lsb_7bit>
<payload> <sum(payload) & 7F> F7
```

Validation results for the reference files:

- four hardware dump files parsed successfully;
- all message structures valid;
- all checksums valid;
- all decode/re-encode round trips byte-identical;
- two independently saved Everything dumps confirmed identical;
- 16 automated tests passing in CODE V1.

See [`reports/reference_validation.md`](reports/reference_validation.md) for the recorded validation report.

## Installation

### Requirements

- Windows 11 is the primary tested platform;
- Python 3.11 or newer;
- PowerShell for the included helper scripts.

From PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Command-line usage

### Inspect a dump

```powershell
mwxt-sysex inspect "D:\Dumps\WALDORF_MWXT_BACKUP_EVERYTHING.syx"
```

### Validate a dump

```powershell
mwxt-sysex validate "D:\Dumps\WALDORF_MWXT_ALL_SOUNDS.syx"
```

### Verify a byte-identical round trip

```powershell
mwxt-sysex roundtrip "D:\Dumps\WALDORF_MWXT_ALL_WAVETABLES_AND_WAVES.syx"
```

Expected result:

```text
IDENTICAL
```

### Decode a Universal Device Identity reply

```powershell
mwxt-sysex identity "F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7"
```

## Running the tests

Run the synthetic test suite:

```powershell
python -m pytest -v
```

Run the complete suite against local private reference dumps:

```powershell
$env:MWXT_DUMP_DIR = "D:\Dumps\MicrowaveXT"
python -m pytest -v
```

The files in `MWXT_DUMP_DIR` must match the names and fingerprints recorded in `reference_dumps/reference_manifest.json`.

The helper script can also be used:

```powershell
.\run_tests.ps1
```

## Repository layout

```text
W-MWXT/
├── src/mwxt_sysex/          Python package
│   ├── cli.py               Command-line interface
│   ├── codec.py             Nibble and value codecs
│   ├── constants.py         Protocol constants
│   ├── dump.py              Concatenated dump parsing
│   ├── errors.py            Domain exceptions
│   ├── identity.py          Universal Identity decoder
│   ├── message.py           Low-level SysEx message model
│   └── models.py            Typed Microwave XT data models
├── tests/                   Synthetic and real-dump tests
├── tools/                   Validation utilities
├── reference_dumps/         Fingerprints and local test instructions
├── reports/                 Recorded CODE V1 validation results
├── pyproject.toml           Packaging and dependency configuration
├── CHANGELOG.md             Release history
└── README.md
```

## Roadmap

### CODE V1 — SysEx core

- [x] Parse concatenated Microwave XT SysEx streams
- [x] Validate framing, family, addresses, lengths, and checksums
- [x] Model Sound, Multi, User Wave, User Wavetable, and Global messages
- [x] Decode and re-encode User Wave and Wavetable nibble data
- [x] Decode hardware identity responses
- [x] Achieve byte-identical round trips on real dumps

### CODE V2 — safe SysEx package builder

- [ ] Allocate consecutive User Wave locations safely
- [ ] Select a User Wavetable destination
- [ ] Select a Sound destination or edit buffer
- [ ] Set and validate a 16-character patch name
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
- [ ] Transition generation across the 61 programmable table positions
- [ ] Hardware-calibrated wavetable preview and simulation
- [ ] Direct MIDI transmission with read-back verification
- [ ] Graphical wavetable editor and analysis interface

## Safety

SysEx writes can overwrite patches, User Waves, User Wavetables, Multi programs, or global settings on the hardware.

Before transmitting generated data:

1. create an **Everything** backup of the synth;
2. verify the target Device ID;
3. verify all destination addresses;
4. inspect the generated package manifest;
5. transmit only after confirming what will be overwritten.

CODE V1 does not transmit data directly to the synth and does not yet generate final write packages.

## Determinism and traceability

The project follows two core rules:

1. **No unexplained automatic decisions.** Future DSP and placement decisions must be accompanied by the measurements and rules that produced them.
2. **Reproducible output.** The same source data and configuration must produce the same result.

## Contributing

The project is in an early architectural phase. Contributions should preserve:

- strict protocol validation;
- deterministic behavior;
- byte-level test coverage;
- separation between low-level SysEx code, DSP processing, user interface, and hardware transport;
- explicit documentation of any behavior inferred from hardware testing rather than official documentation.

Before opening a pull request:

```powershell
python -m pytest -v
```

Do not submit proprietary factory dumps, personal backup dumps, copyrighted sound banks, or firmware images.

## Disclaimer

W-MWXT is an independent, unofficial project. It is not affiliated with, endorsed by, or supported by Waldorf Music.

Use generated SysEx data at your own risk and always keep a verified backup of the instrument before writing to its memory.

## License

A public software license has not yet been selected. Add a `LICENSE` file before defining the reuse and redistribution terms for the repository.
