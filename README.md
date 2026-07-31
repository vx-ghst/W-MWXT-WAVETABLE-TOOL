# W-MWXT-WAVETABLE-TOOL

**W-MWXT-WAVETABLE-TOOL** is a deterministic Python toolkit for wave, wavetable, audio-source, and SysEx engineering for the **Waldorf Microwave XT**.

> **Current release:** `0.4.0` — CODE V4  
> **Distribution and CLI:** `W-MWXT-WAVETABLE-TOOL`  
> **Python package:** `w_mwxt_wavetable_tool`  
> **Primary platform:** Windows 11  
> **Python:** 3.11 or newer

The project is developed through controlled, testable stages. CODE V1 established the strict SysEx core, CODE V2 added safe deterministic package construction and hardware read-back validation, CODE V3 added deterministic audio import and minimal project persistence, and CODE V4 adds the complete deterministic time-domain signal-analysis contract.

## Current capabilities

### CODE V1 — deterministic Microwave XT SysEx core

- split concatenated SysEx streams;
- validate `F0`/`F7` framing, Waldorf identifiers, addresses, payload lengths, and checksums;
- decode and re-encode Sounds, Multis, User Waves, User Wavetables, and Global parameters;
- decode User Wave samples and User Wavetable references;
- read and edit 16-character Sound names;
- decode a Universal Device Identity reply;
- preserve byte-identical round trips.

### CODE V2 — safe package builder and hardware validation

- typed Device ID, Sound, User Wavetable, and User Wave destinations;
- explicit broadcast opt-in;
- consecutive User Wave allocation;
- collision and overwrite analysis;
- deterministic `WAVD → WCTD → SNDD` package generation;
- JSON and Markdown package manifests;
- hardware preflight and exact restore-bundle generation;
- read-back comparison with exact payload and address diagnostics;
- controlled hardware write and restoration validated at `63/63` exact messages.

The tool does **not** transmit MIDI automatically. Hardware transmission remains a deliberate manual step using an external SysEx utility.

### CODE V3 — deterministic audio import and minimal projects

- import WAV, AIFF, and FLAC through libsndfile;
- detect the actual container independently of the file extension;
- preserve source metadata and SHA-256 fingerprints;
- decode to immutable contiguous `float64` samples;
- convert mono, stereo, or multichannel sources to mono deterministically;
- protect strongly anti-phase stereo from destructive averaging;
- detect silence, DC offset, invalid samples, peak, RMS, and extrema;
- produce deterministic sample and imported-state hashes;
- save deterministic `.mwxtproj` archives;
- embed canonical little-endian mono samples;
- reopen the exact imported state without re-decoding the source;
- detect unchanged, changed, missing, or ignored external sources;
- allow an explicit embedded-data fallback when the source is unavailable.

### CODE V4 — deterministic signal analysis

- global level, clipping, DC, asymmetry, saturation, and envelope measurements;
- fundamental pitch, note, cents deviation, periodicity, and pitch stability;
- phase continuity, cycle-discontinuity, and pitch-motion analysis;
- deterministic noise-floor, SNR, and noise-stationarity estimates;
- transient, onset, and energy/spectral change-point detection;
- immutable `SignalAnalysis` aggregate with one sample identity and component hashes;
- deterministic `signal-analyze` JSON reports with a complete aggregate SHA-256.

## Installation on Windows 11

Open PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Verify the release:

```powershell
W-MWXT-WAVETABLE-TOOL --version
python -c "import w_mwxt_wavetable_tool as tool; print(tool.__version__)"
```

Both commands must report:

```text
0.4.0
```

## Command-line usage

### Inspect a SysEx dump

```powershell
W-MWXT-WAVETABLE-TOOL inspect "D:\Dumps\backup.syx"
```

### Validate one or more dumps

```powershell
W-MWXT-WAVETABLE-TOOL validate "D:\Dumps\backup.syx"
```

### Verify a byte-identical round trip

```powershell
W-MWXT-WAVETABLE-TOOL roundtrip "D:\Dumps\backup.syx"
```

### Decode an XT identity reply

```powershell
W-MWXT-WAVETABLE-TOOL identity "F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7"
```

### Inspect an audio source

```powershell
W-MWXT-WAVETABLE-TOOL audio-inspect `
  "D:\Audio\source.wav" `
  --report "D:\Reports\source.audio.json"
```

The JSON report includes format metadata, source SHA-256, mono policy and explanation, measurements, sample SHA-256, and imported-state SHA-256.

### Analyze a complete signal

```powershell
W-MWXT-WAVETABLE-TOOL signal-analyze `
  "D:\Audio\source.wav" `
  --report "D:\Reports\source.signal.json"
```

The report preserves the accepted component keys and adds the CODE V4 aggregate schema, tool version, canonical sample identity, component hashes, and overall `analysis_sha256`.

### Create a minimal project

```powershell
W-MWXT-WAVETABLE-TOOL project-create `
  "D:\Audio\source.wav" `
  "D:\Projects\source.mwxtproj" `
  --name "Source project"
```

The save is deterministic. Repeating the command with the same source, name, policy, and release produces a byte-identical project archive.

### Open and verify a project

Strict source validation is the default:

```powershell
W-MWXT-WAVETABLE-TOOL project-open `
  "D:\Projects\source.mwxtproj"
```

Allow the exact embedded mono state when the source is missing or changed:

```powershell
W-MWXT-WAVETABLE-TOOL project-open `
  "D:\Projects\source.mwxtproj" `
  --source-policy allow_embedded
```

Ignore the external source and use only embedded data:

```powershell
W-MWXT-WAVETABLE-TOOL project-open `
  "D:\Projects\source.mwxtproj" `
  --source-policy ignore
```

### Build a controlled hardware acceptance package

```powershell
W-MWXT-WAVETABLE-TOOL hardware-build-test `
  "D:\Dumps\everything-before.syx" `
  --source-wave-start 1000 `
  --source-wavetable 126 `
  --source-sound A015 `
  --target-wave-start 1189 `
  --target-wavetable 128 `
  --target-sound B128 `
  --output-dir "D:\HardwareTest"
```

Use `hardware-preflight` before manual transmission and `hardware-compare` after a fresh read-back dump. Preserve and use the generated restore bundle.

## Running tests

Public suite:

```powershell
Remove-Item Env:W_MWXT_DUMP_DIR -ErrorAction SilentlyContinue
python -m pytest -v
```

Private hardware-reference suite:

```powershell
$env:W_MWXT_DUMP_DIR = "D:\W-MWXT-PRIVATE-DUMPS"
python -m pytest -v
```

Private `.syx` files, audio sources, hardware captures, and generated projects must remain outside the repository.

## Determinism and traceability

The project follows two rules:

1. identical source data and configuration must produce identical outputs;
2. automatic decisions must be accompanied by measurements, policies, and explicit explanations.

CODE V4 preserves the CODE V3 source and project fingerprints and adds component-level and aggregate signal-analysis fingerprints.

## Safety

SysEx writes can overwrite Sounds, User Waves, User Wavetables, Multis, or global settings.

Before any hardware write:

1. create and verify an Everything backup;
2. confirm the XT Device ID;
3. reserve non-critical destination addresses;
4. inspect the package and preflight reports;
5. transmit manually with a proven SysEx utility;
6. create a fresh read-back dump;
7. compare every target;
8. restore and verify the original targets when testing is complete.

## Roadmap

Completed:

- [x] CODE V1 — deterministic SysEx core
- [x] CODE V2 — safe package builder and hardware validation
- [x] CODE V3 — audio import, mono conversion, and minimal project persistence
- [x] CODE V4 — time-domain DSP, pitch, periodicity, phase, levels, noise, transients, and change points

Next:

- [ ] CODE V5 — spectral, perceptual, classification, and decision engine
- [ ] CODE V6 — segmentation, cycle ranking, and reconstruction
- [ ] CODE V7 — XT-native optimization, quantization, and Auto Repair
- [ ] CODE V8 — complete 61-position wavetable generation and transitions
- [ ] CODE V9+ — complete project export, preview, transport, and graphical interface

See `docs/roadmap/W-MWXT-WAVETABLE-TOOL_ROADMAP_AND_TRACEABILITY_MATRIX.md` for the full staged plan.

## Public repository and licensing

The repository is public. The package metadata currently uses the license text `Private project`, which is not a standard open-source license and does not grant conventional reuse rights by itself. A formal license can be selected later.

## Disclaimer

W-MWXT-WAVETABLE-TOOL is an independent, unofficial project. It is not affiliated with, endorsed by, or supported by Waldorf Music.

Use generated SysEx data at your own risk and keep a verified backup before writing to the instrument.
