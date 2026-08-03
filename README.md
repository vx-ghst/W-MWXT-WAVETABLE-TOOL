# W-MWXT-WAVETABLE-TOOL

**W-MWXT-WAVETABLE-TOOL** is a deterministic Python toolkit for wave, wavetable, audio-source, and SysEx engineering for the **Waldorf Microwave XT**.

> **Current release:** `0.7.0` — CODE V7<br>
> **Distribution and CLI:** `W-MWXT-WAVETABLE-TOOL`  
> **Python package:** `w_mwxt_wavetable_tool`  
> **Primary platform:** Windows 11  
> **Python:** 3.11 or newer

The project is developed through controlled, testable stages. CODE V1 established the strict SysEx core, CODE V2 added safe deterministic package construction and hardware read-back validation, CODE V3 added deterministic audio import and minimal project persistence, CODE V4 added time-domain signal analysis, CODE V5 added spectral/perceptual decisions, CODE V6 added working-pitch planning, segmentation, cycle discovery, representative selection, and waveform reconstruction, and CODE V7 adds documented XT coding, XT-native projection, a deterministic 61-position trajectory, trajectory QC, hardware-package generation, and physical instrument acceptance.

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

### CODE V5 — spectral, perceptual, classification, and decisions

- deterministic framed FFT analysis with local and aggregate spectral descriptors;
- harmonic, residual, inharmonicity, tristimulus, Bark-band, brightness, concentration, and noisiness evidence;
- explainable canonical source-family classification with normalized scores, confidence, ambiguity, and measured evidence;
- deterministic readiness and risk decisions with blockers and prioritized non-automated recommendations;
- strict SHA-256 links across every CODE V4 and CODE V5 component;
- immutable `CodeV5Analysis` aggregate with one canonical sample identity and one final aggregate SHA-256;
- deterministic `analyze-audio` JSON reports containing the complete accepted analysis chain.

### CODE V6 — working pitch, segmentation, cycle selection, and reconstruction

- octave-preserving working-pitch candidates with automatic, locked, and no-repitch policies;
- deterministic attack-aware source segmentation with complete source coverage;
- source-domain cycle discovery with periodicity, seam, energy, spectral, and composite metrics;
- deterministic representative ranking, temporal/segment novelty, top-N selection, and explicit forced-cycle override;
- spectral, dominant-partial, and hybrid 128-point float-domain reconstruction;
- strict SHA-256 links from the accepted CODE V5 analysis through every V6 component;
- immutable `CodeV6Analysis` aggregate with one final analysis SHA-256;
- final `analyze-code-v6` JSON report containing the complete accepted CODE V5 + V6 chain.

CODE V6 remains non-destructive: it does not quantize XT values, allocate synth memory, build SysEx, or transmit MIDI. Those operations remain gated by later stages.

### CODE V7 — XT-native projection, trajectory, QC, and hardware acceptance

- documented offset-binary User Wave coding and reverse-negate reconstruction;
- safe generated sample range `-127..127`, with `-128` excluded;
- deterministic 128-to-64 projection with exhaustive phase evaluation;
- complete 61-position XT-safe trajectory construction;
- QC of 60 adjacent transitions and 59 interior curvature points;
- deterministic mathematical audition WAV files;
- deterministic 63-message package and exact restore bundle;
- exact first-write, restore, and final-write hardware validation at `63/63` messages.

CODE V7 never transmits MIDI automatically. Hardware writes remain deliberate manual actions followed by a fresh redump and exact comparison.

### CODE V8-0A — executable compliance registry (development branch)

- strict schema-versioned registry for all 206 cahier-des-charges requirements;
- explicit V7 support state and corrected closure destination for every requirement;
- canonical registry SHA-256 and pinned source fingerprints;
- adapters and migrations for the validated legacy audit-matrix format;
- executable non-reintroduction gates for all nine deliberate exclusions;
- six-job Ubuntu/Windows Python 3.11–3.13 CI matrix.

CODE V8-0A is a traceability contract, not a claim that partial or planned features are already implemented. Those requirements remain assigned to their recorded CODE stages.

### CODE V8-0B - import, signal, behavior, and regions (development branch)

- complete deterministic mono policies: sum, average, left, right, Mid, best periodicity, and automatic selection;
- structured candidate scores and backward-compatible minimal-project parsing;
- dedicated rapid-FM, saturation, asymmetry, density, complexity, beating, unison, and detune contracts;
- eight explainable source-behavior classes without changing the historical CODE V5 classifier;
- contiguous region-interest analysis for establishment, sustain, evolution, saturation, redundancy, disappearance, and noise;
- deterministic interest-weighted advisory allocation without building or transmitting a wavetable.

CODE V8-0B extends accepted V4-V6 results through linked schema-versioned aggregates. It does not mutate the frozen V7 XT path and never transmits MIDI or SysEx.

### CODE V8-0C - spectrum, perceptual analysis, classification, and modes (development branch)

- four-band spectral evolution, harmonic/inharmonic partial inventory, formant candidates, and source-span spectral correlation;
- bounded perceptual proxies for low-frequency power, fundamental presence, brightness, hardness, saturation, density, motion, tonality, and noise;
- explicit perceptual distance, audible-redundancy grouping, and ordered-sweep continuity;
- the canonical 27-class multi-label musical taxonomy with scores, confidence, ambiguity, evidence, and explanations;
- five explainable conversion modes with importable execution paths, manual override, warnings, and explicit refusal for inactive sources.

CODE V8-0C remains additive: accepted V5/V6 schemas and the frozen V7 XT modules are unchanged.

### CODE V8-0D - XT-native resampling and effective profiles (development branch)

- deterministic periodic windowed-sinc, Fourier, and linear resampling with explicit anti-alias, normalization, phase, fundamental, ringing, overshoot, and extreme-value evidence;
- strict nearest and error-feedback XT quantization in the safe generated range `-127..127`;
- six transforms, 128 phase/start positions, six half-wave/reduction methods, and automatic or manually overridden treatment selection;
- complete XT time, phase, harmonic, band, perceptual, aliasing, ringing, seam, amplitude, Sub, and Bass metrics;
- nine effective optimization profiles with normalized weights and capped musical-classification/conversion-mode influence;
- Bass-specific working-pitch comparison, monophonic warnings, inter-wave consistency, and independent optimization of exactly 61 waves.

CODE V8-0D remains mathematical and non-destructive. It does not build the final 61-position table, open MIDI ports, transmit SysEx, or claim calibrated XT audibility.

### CODE V8-0E - complete Auto Repair policies and actions (development branch)

- deterministic detection and action mapping for all 17 required repair defects;
- exact `AUTO`, `COMPARE`, `IGNORE`, and `PRESERVE` policies with per-defect overrides;
- explicit review states when neighbor, reference, pitch, target-level, or aliasing context is unavailable;
- separate before, candidate, and selected branches with complete metrics and action logs;
- profile-aware controlled-defect preservation and hard numeric safety;
- deterministic ordered sequence processing, including exactly 61 waves.

CODE V8-0E remains additive and non-destructive. It exposes canonical data for later reports, preview audition, and editor controls without opening MIDI ports or transmitting SysEx.

### CODE V8-0F - pre-V8 aggregate and zero required-debt gate (development branch)

- immutable closure evidence for all 62 active obligations whose corrected destination begins with `V8-0`;
- exact link to the historical V8-0A registry without rewriting baseline support states;
- validated V3 imported-state, V4/V5/V6 aggregate, and V7 projection/trajectory/QC/package provenance;
- one linked decision plan covering V8-0B signal/region extensions, V8-0C classification/modes, V8-0D profiles/XT optimization, and V8-0E repair records;
- explicit ready or rejected preflight status, canonical JSON, and one final SHA-256;
- executable gate requiring zero missing, partial, or absent debt before CODE V8-A.

CODE V8-0F does not build a wavetable or transmit MIDI/SysEx. It only authorizes entry into the generic CODE V8 builder when implementation debt and component provenance are valid.

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
0.7.0
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

### Analyze the complete CODE V5 chain

```powershell
W-MWXT-WAVETABLE-TOOL analyze-audio `
  "D:\Audio\source.wav" `
  --report "D:\Reports\source.code-v5.json"
```

The report contains the imported-audio summary plus one `code_v5_analysis` object. That aggregate preserves the complete signal, spectral, harmonic/perceptual, classification, and engineering-decision reports, validates every component link, and adds the final CODE V5 `analysis_sha256`.

The component commands `spectral-analyze`, `perceptual-analyze`, `classify-audio`, and `recommend-audio` remain available for focused inspection.

### Analyze the complete CODE V6 chain

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

The report contains the imported-audio summary plus one `code_v6_analysis` object. It embeds the accepted CODE V5 aggregate, the working-pitch plan, source segmentation, cycle discovery, representative selection, reconstructed float waves, exact component links, and one final `analysis_sha256`.

The focused V6 commands `pitch-plan`, `segment-audio`, `discover-cycles`, `select-cycles`, and `reconstruct-waves` remain available. The existing `analyze-audio` command remains the stable CODE V5 aggregate command.

### Run the CODE V7 XT-native stages

```powershell
W-MWXT-XT-GATE --help
W-MWXT-XT-AUDIO-GATE --help
W-MWXT-XT-PROJECT --help
W-MWXT-XT-TRAJECTORY --help
W-MWXT-XT-QC --help
W-MWXT-XT-PACKAGE --help
```

Stage order: reconstruction gate -> controlled audio gate -> XT-native projection -> 61-position trajectory -> trajectory QC -> deterministic package -> manual transmission and exact read-back validation.

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
$env:W_MWXT_DUMP_DIR = "D:\path\to\private-reference-dumps"
python -m pytest -v
```

Private `.syx` files, audio sources, hardware captures, and generated projects must remain outside the repository.

## Determinism and traceability

The project follows two rules:

1. identical source data and configuration must produce identical outputs;
2. automatic decisions must be accompanied by measurements, policies, and explicit explanations.

CODE V7 preserves the complete CODE V6 lineage and adds deterministic hashes for XT projections, trajectory slots, QC reports, generated artifacts, hardware packages, restore bundles, and read-back comparisons.

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
- [x] CODE V5 — spectral, perceptual, classification, decisions, and aggregate analysis
- [x] CODE V6 — working pitch, segmentation, cycle ranking, selection, reconstruction, and aggregate analysis
- [x] CODE V7 — XT-native projection, 61-position trajectory, QC, package generation, and hardware acceptance

In progress:

- [ ] CODE V8-0 — exhaustive post-V7 compliance closure; V8-0A and V8-0B closed, V8-0C implemented locally pending private/remote gates

Next:

- [ ] CODE V8 — generic WavetableBuild, placement policies, interpolation, WCTD and hardware gates
- [ ] CODE V9+ — complete project export, preview, transport, and graphical interface

See `docs/roadmap/W-MWXT-WAVETABLE-TOOL_ROADMAP_AND_TRACEABILITY_MATRIX.md` for the full staged plan.

## Public repository and licensing

The repository is public. The package metadata currently uses the license text `Private project`, which is not a standard open-source license and does not grant conventional reuse rights by itself. A formal license can be selected later.

## Disclaimer

W-MWXT-WAVETABLE-TOOL is an independent, unofficial project. It is not affiliated with, endorsed by, or supported by Waldorf Music.

Use generated SysEx data at your own risk and keep a verified backup before writing to the instrument.
