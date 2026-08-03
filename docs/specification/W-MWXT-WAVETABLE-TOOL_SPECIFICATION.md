# W-MWXT-WAVETABLE-TOOL
## Public Functional and Technical Specification

**Project:** W-MWXT-WAVETABLE-TOOL  
**Owner:** R-MiT  
**Document type:** public specification  
**Document version:** 1.0  
**Target:** `v1.0.0-prototype`  
**Primary platform:** Windows 11  
**Target instrument:** Waldorf Microwave XT only

---

# 1. Purpose

W-MWXT-WAVETABLE-TOOL is a dedicated engineering environment for analyzing audio, creating and optimizing Microwave XT User Waves, building User Wavetables, preparing Sound programs, previewing results, generating reports, and producing safe SysEx packages.

It is not limited to converting a WAV file into a fixed sequence of 61 waves. The prototype is intended to combine four major engines:

1. **DSP engine** — signal, pitch, cycle, spectral, phase, defect, and perceptual analysis.
2. **Decision engine** — deterministic and explainable selection of processing mode, pitch, cycles, repair policy, profile, and placement strategy.
3. **Microwave XT engine** — native reduction, User Wave reconstruction, 64-point optimization, 61-position construction, WCTD generation, Sound generation, and SysEx packaging.
4. **Studio environment** — project persistence, editor, preview, reports, exports, command-line operation, batch operation, GUI, MIDI transport, and read-back verification.

---

# 2. Scope

## 2.1 Included target

The software targets the **Waldorf Microwave XT** and the confirmed Microwave II/XT SysEx message family used by the reference hardware.

## 2.2 Excluded targets

The prototype will not provide export modes for:

- Waldorf Blofeld;
- Waldorf M;
- Microwave I;
- generic PPG formats;
- unrelated wavetable synthesizers;
- generic multi-synth conversion.

The internal architecture may remain modular, but no unsupported target shall be presented to the user.

## 2.3 Audio formats

Supported source formats:

- WAV;
- AIFF;
- FLAC.

MP3 is deliberately excluded because destructive compression can introduce artifacts that interfere with cycle, phase, and spectral analysis.

---

# 3. Source import and project handling

The program shall:

- open one audio file;
- process an entire folder in Batch mode;
- recognize files exported from software instruments, hardware instruments, samplers, or recordings as ordinary audio sources;
- detect sample rate;
- detect bit depth or audio subtype when available;
- detect duration;
- detect channel count;
- detect peak level;
- identify the source format;
- calculate a source fingerprint;
- preserve the original file;
- store the work in a reopenable project.

## 3.1 Mono conversion

Stereo sources shall be converted to mono before the DSP pipeline.

Supported conversion policies shall include:

- average or mono sum;
- left channel;
- right channel;
- Mid component;
- channel with the best periodicity;
- deterministic automatic selection.

The selected policy and its measurements shall be recorded.

After conversion, all DSP analysis shall operate on the mono representation. No separate stereo-analysis engine is required for the prototype.

## 3.2 Time-region policy

The source is assumed to be intentionally selected and relevant.

The program may automatically detect:

- attacks;
- stable regions;
- evolving regions;
- noisy tails;
- redundant sections;
- useful cycle regions.

A mandatory manual time-range selection is not part of the prototype. The user may later select or lock candidate cycles in the editor, but the core workflow must remain automatic.

---

# 4. General signal analysis

The DSP engine shall measure or estimate:

- fundamental frequency;
- musical note;
- cents deviation;
- pitch stability;
- pitch drift;
- vibrato;
- glissando;
- portamento;
- fast frequency modulation;
- periodicity;
- quasi-periodicity;
- non-periodic content;
- phase stability;
- phase evolution;
- amplitude stability;
- dynamic evolution;
- peak;
- RMS;
- crest factor;
- DC offset;
- clipping;
- noise;
- signal-to-noise ratio;
- transients;
- saturation;
- waveform asymmetry;
- spectral density;
- signal complexity;
- beating between oscillators;
- unison or detune;
- significant temporal changes.

The signal shall be classifiable as one or more of:

- periodic;
- quasi-periodic;
- evolving;
- variable-pitch;
- transient;
- noisy;
- non-periodic;
- hybrid.

Every automatic classification shall include confidence and an explanation.

---

# 5. Spectral and harmonic analysis

The software shall calculate:

- FFT;
- spectrogram;
- average spectrum;
- local spectra;
- dominant fundamental;
- fundamental energy;
- H2, H3, and higher-harmonic energy;
- low, low-mid, mid, and high-band energy;
- spectral centroid;
- perceived brightness proxy;
- spectral roll-off;
- spectral flux;
- harmonic evolution over time;
- harmonic density;
- harmonic partials;
- inharmonic partials;
- formant candidates;
- two close fundamentals;
- oscillator beating rate;
- saturation evolution;
- spectral correlation between regions or cycles;
- harmonic loss caused by XT reduction;
- aliasing risk after conversion and transposition.

Measurements shall feed explicit decisions. A metric may not be collected solely for display if it has no defined interpretation or report role.

---

# 6. Psychoacoustic analysis

The engine shall estimate:

- perceived low-frequency power;
- perceived fundamental presence;
- perceived brightness;
- hardness or harshness;
- perceived saturation;
- perceived density;
- sense of motion;
- perceptual distance between waves;
- audible redundancy;
- audible difference between the source and XT reconstruction;
- perceived continuity during a wavetable scan.

These metrics are intended to prevent technically different but perceptually redundant waves from consuming unnecessary structural positions.

---

# 7. Musical classification

The program may return multiple labels with confidence values.

Target classes include:

- Sub;
- Bass;
- Reese;
- FM Bass;
- Dirty Bass;
- Hoover;
- Acid;
- Lead;
- Pad;
- Drone;
- Organ;
- PWM;
- Supersaw;
- Wavetable;
- Bell;
- FM Bell;
- Pluck;
- Vocal;
- Choir;
- Texture;
- Digital Noise;
- Noise;
- Piano;
- Guitar;
- Percussion;
- FX;
- Hybrid.

Classification shall influence optimization priorities and patch recommendations, but shall not independently force a conversion strategy.

---

# 8. Conversion modes

The decision engine shall select from the following explainable strategies.

## 8.1 Stable Cycle

For stable periodic material such as:

- sine waves;
- saw waves;
- square waves;
- stable PWM;
- stable FM;
- fixed basses and leads.

Primary task: identify and extract the best representative cycle.

## 8.2 Evolving Harmonics

For material whose timbre changes over time, including:

- Reese sounds;
- supersaws;
- filter movement;
- progressive saturation;
- evolving pads;
- modulated basses.

Primary task: select representative harmonic states.

## 8.3 Dynamic Pitch

For material containing:

- vibrato;
- glissando;
- portamento;
- wow and flutter;
- strong FM;
- pitch drift.

The engine shall choose whether to:

- stabilize pitch;
- temporarily repitch;
- freeze several pitch states;
- reconstruct an average cycle;
- preserve part of the movement.

## 8.4 Spectral Reconstruction

For material without reliable cycles, including:

- voice;
- piano;
- guitar;
- noise;
- textures;
- percussion;
- highly inharmonic sources.

The engine shall synthesize a usable cycle from spectral or partial information.

## 8.5 Hybrid

Different sections of one table may use different methods.

Example:

```text
positions 01–20 : stable cycles
positions 21–40 : evolving harmonic states
positions 41–61 : spectral reconstruction
```

## 8.6 Manual overrides

The user shall be able to:

- force a conversion mode;
- lock pitch;
- disable repitching;
- force selected cycle candidates;
- select a correction amount;
- preserve controlled imperfections.

A standalone Reese-only architecture is explicitly excluded. Reese remains a classification and usually maps to Evolving Harmonics or Hybrid processing.

---

# 9. Pitch analysis and working-pitch optimization

The program shall determine:

- average fundamental;
- note;
- cents offset;
- pitch stability;
- pitch range;
- likely tuning;
- local frequency over time.

It shall compare candidate working pitches, including values around:

- 55.00 Hz;
- 65.41 Hz;
- 82.41 Hz;
- 110.00 Hz;
- 130.81 Hz;
- 164.81 Hz.

For each candidate, it shall evaluate:

- samples per period;
- pitch-detection stability;
- zero-crossing quality;
- phase precision;
- retained harmonic count;
- resampling quality;
- aliasing risk;
- bass-preservation score.

Temporary repitching may be applied in semitones and cents.

The decision report shall contain:

- original pitch;
- working pitch;
- transposition;
- expected advantages;
- expected losses;
- reason for the selected pitch.

---

# 10. Cycle discovery and ranking

The program shall search the source for all usable cycle candidates.

Each candidate may be measured by:

- length;
- agreement with the fundamental;
- rising or falling zero crossing;
- start/end mismatch;
- loop error;
- derivative error at the join;
- phase coherence;
- correlation with the following cycle;
- local pitch stability;
- amplitude stability;
- harmonic content;
- noise;
- clipping;
- spectral richness;
- XT compatibility;
- psychoacoustic quality.

The program shall:

- rank candidates;
- reject unstable candidates;
- avoid selecting the first superficially clean cycle by default;
- select representative rather than merely clean cycles;
- retain candidates from several useful regions;
- expose top candidates for editor review.

---

# 11. Automatic region segmentation

The source may be segmented into:

- attack;
- onset stabilization;
- stable sustain;
- harmonic evolution;
- new saturation stage;
- redundant region;
- decay or disappearance;
- noise or residual effects.

The engine shall:

- reject an unusable attack automatically;
- preserve an attack when it contains useful structural information;
- detect meaningful spectral changes;
- ignore long nearly identical regions;
- favor moments that introduce a new harmonic color;
- distribute sampling density according to signal interest rather than uniform time spacing;
- expose selected and rejected regions in reports and GUI views.

---

# 12. Generation of 61 user positions

The program shall always produce 61 user positions for a complete Microwave XT table plan.

It may:

- extract 61 real cycles;
- combine real and reconstructed cycles;
- create transitions;
- generate deterministic variants;
- use linear or non-linear progression;
- allocate more positions to rapidly evolving regions;
- allocate fewer positions to stable regions;
- guarantee that every user position contains a valid wave reference or generated wave.

Each position shall store metadata including:

- quality score;
- usefulness score;
- stability;
- harmonic richness;
- brightness;
- bass power;
- role in the table;
- source time;
- generation method;
- real or interpolated status;
- structural or transition status.

---

# 13. Structural-wave count and redundancy

Even when 61 positions are populated, the software shall report how many states are genuinely distinct.

It shall detect:

- redundant waves;
- near-duplicate groups;
- stable plateaus;
- spectral breakpoints;
- structural key waves;
- transition-only waves.

Example report:

```text
61 populated positions
8 structural waves
53 transitions
essential positions: 01, 08, 19, 37, 52, 61
```

---

# 14. Placement optimization

The final order is not required to match raw chronology.

The program may:

- reposition waves;
- reorder waves;
- minimize distance between adjacent positions;
- preserve a musically meaningful trajectory;
- create increasing brightness, saturation, or density curves;
- preserve chronological events when musically relevant;
- lock specific waves to specific positions;
- compare multiple orderings;
- optimize a weighted compromise between:
  - source fidelity;
  - scan smoothness;
  - harmonic diversity;
  - bass strength;
  - discontinuity avoidance.

The placement engine shall be deterministic and explainable.

---

# 15. Transition generation

When only a small number of source states are structurally useful, the remaining positions shall be filled by interpolation.

Supported approaches may include:

- waveform interpolation;
- amplitude interpolation;
- phase-aware interpolation;
- spectral interpolation;
- harmonic-amplitude interpolation;
- perceptually spaced interpolation.

The engine shall:

- choose an interpolation method per interval;
- allocate more steps where the audible change is stronger;
- smooth transitions;
- maintain phase continuity where appropriate;
- avoid accidental loss of the fundamental;
- avoid level dips;
- avoid unintended polarity inversion;
- render a test scan before final acceptance.

---

# 16. XT Symmetry Optimizer

This is a central Microwave XT-specific module.

For each wave, the optimizer shall be able to test:

- cycle rotations;
- alternative start points;
- phase alignments;
- polarity inversion;
- time reversal;
- mirror representations;
- multiple half-wave candidates;
- multiple reduction methods.

It shall search for the transmitted 64-sample representation that produces the best reconstructed 128-sample wave under the confirmed XT User Wave rule.

Metrics shall include:

- RMS error;
- maximum error;
- harmonic difference;
- phase difference;
- perceptual difference;
- fundamental preservation;
- H2 and H3 preservation;
- mid-frequency preservation;
- high-frequency preservation;
- low-frequency power loss.

For Bass and Sub profiles, the weighting shall prioritize:

1. fundamental;
2. H2 and H3;
3. useful midrange;
4. high-frequency detail.

The optimizer shall operate independently on all 61 generated waves.

---

# 17. Wave representations

The program shall compare at least:

- high-resolution source;
- 128-point working wave;
- 64 transmitted XT samples;
- simulated 128-point reconstruction;
- before-repair version;
- after-repair version.

The selected processing method shall be automatic by default but overridable in the editor.

Any assumption about the exact hardware reconstruction shall remain versioned and testable. A hardware result that contradicts the current model shall trigger a specification and implementation update.

---

# 18. Resampling and quantization

The engine shall provide:

- high-quality resampling;
- anti-alias filtering;
- comparison of candidate algorithms;
- phase preservation;
- fundamental preservation;
- normalization before and after reduction when required;
- ringing control;
- extreme-value control;
- quantization matching the effective XT format;
- quantization simulation;
- before/after error measurements.

No operation may silently overflow, wrap, clip, or normalize away important low-frequency energy.

---

# 19. Auto Repair

The program shall detect and optionally repair:

- DC offset;
- clipping;
- incorrect zero crossing;
- loop discontinuity;
- derivative discontinuity;
- phase inversion;
- polarity inversion;
- excessive start/end mismatch;
- inconsistent amplitude;
- cycle that is too short or too long;
- incorrect pitch estimate;
- parasitic noise;
- loss of the fundamental;
- spectral jump between adjacent waves;
- inter-wave level mismatch;
- redundant wave;
- excessive aliasing.

For each repair, the user shall be able to choose:

- AUTO;
- COMPARE;
- IGNORE;
- PRESERVE.

Every applied repair shall be logged and available for before/after comparison.

---

# 20. Bass and Sub optimization

The Bass/Sub profile shall:

- preserve the fundamental;
- prioritize H2 and H3;
- monitor subharmonics;
- avoid phase cancellation;
- reduce high harmonics that do not survive usefully;
- maintain coherent amplitude across positions;
- preserve perceived low-note power;
- avoid normalization that thins the sound;
- weight low-frequency errors more strongly;
- keep early positions solid and playable;
- compare multiple working pitches;
- warn when the source is too unstable for a solid monophonic bass;
- report separate Sub and Bass scores.

---

# 21. Musical optimization profiles

Profiles shall include:

- Bass/Sub;
- Lead;
- Pad;
- Bell/FM;
- Vocal/Choir;
- Texture;
- Drone;
- Percussive;
- Experimental.

The Experimental profile may intentionally preserve controlled:

- aliasing;
- asymmetry;
- saturation;
- phase error;
- roughness;
- abrupt transitions.

Such preservation must be explicit, never accidental.

---

# 22. Waldorf Factory-style placement

An optional placement constraint may organize the table as:

```text
positions 01–20 : stable and directly playable forms
positions 20–45 : main evolution
positions 45–61 : extreme forms
```

This mode is a musical organizational profile. It shall not claim to reproduce proprietary historical factory procedures.

---

# 23. Microwave XT preview and simulator

The preview system shall support:

- playback of one User Wave;
- playback of the reconstructed wave;
- interpolation between table positions;
- Wave parameter scans;
- LFO scans;
- envelope scans;
- configurable start and end;
- movement speed;
- direction;
- fixed-position hold;
- multiple notes and octaves;
- quantization and resampling preview;
- a complete 61-position table.

Audition presets shall include:

- single wave;
- slow sweep;
- fast sweep;
- forward/backward sweep;
- envelope sweep;
- several octaves;
- before/after optimization;
- original ordering versus optimized ordering.

Artifact detection shall include:

- clicks;
- discontinuities;
- bass loss;
- level modulation;
- phase artifacts;
- excessive transitions;
- aliasing;
- poor looping.

## 23.1 Simulation accuracy levels

### Level 1 — SysEx and structural accuracy

Expected to be exact through documented formats, dumps, generated vectors, write tests, and read-back.

### Level 2 — User Wave and Wavetable behavior

Requires hardware confirmation of:

- reconstruction;
- quantization;
- amplitude limits;
- extreme values;
- invalid references;
- interpolation;
- positions 60–63.

### Level 3 — Calibrated audible simulation

Requires controlled recordings of the real XT and measured comparison with the software renderer.

### Level 4 — Bit-exact DSP emulation

Not a prototype requirement and must not be claimed without substantially stronger evidence.

The rational prototype target is structurally exact and audibly calibrated simulation within documented conditions.

---

# 24. Integrated wavetable editor

The editor shall support non-destructive operations:

- move;
- delete;
- duplicate;
- replace;
- lock;
- polarity inversion;
- time reversal;
- phase rotation;
- normalize;
- gain adjustment;
- smoothing;
- emphasis;
- interpolate;
- fill a range;
- reorder a range;
- audition one position;
- compare versions;
- undo;
- redo;
- preserve multiple variants;
- re-run optimization on a selection only.

All operations shall be represented as commands so the complete edit history can be reversed.

---

# 25. Graphical interface

The GUI shall display:

- mono source waveform;
- detected regions;
- zero crossings;
- cycle candidates;
- pitch curve;
- FFT;
- spectrogram;
- harmonic partials;
- harmonic evolution;
- phase;
- level;
- saturation;
- useful and redundant regions;
- 61 user positions;
- each wave;
- table evolution;
- wave scores;
- essential positions;
- source origin for each position;
- before/after comparison;
- original versus XT reconstruction;
- 64 transmitted points;
- full reconstructed wave;
- preview controls.

The GUI shall remain a separate layer. DSP and domain logic must remain accessible without the GUI.

---

# 26. Command-line interface

The full workflow shall be available from the command line.

The CLI shall support:

- automatic analysis;
- forced conversion mode;
- forced musical profile;
- pitch lock;
- repitch disable;
- forced cycle candidates;
- Auto Repair policy;
- imperfection-preservation policy;
- report selection;
- export selection;
- Batch mode;
- external configuration file;
- deterministic execution;
- explicit seed only if a future algorithm genuinely requires one.

---

# 27. Batch mode

Batch mode shall process a complete folder.

It shall produce:

- one table per valid source;
- one individual report set per source;
- one export folder per source;
- a global report;
- XT compatibility ranking;
- error list;
- rejected-file list;
- score comparison;
- selected-mode summary;
- complete processing log.

One source failure shall not stop the remaining sources unless fail-fast mode is explicitly enabled.

---

# 28. Reports

The program shall generate distinct reports.

## 28.1 DSP Analysis Report

Includes:

- file properties;
- pitch;
- note;
- cents;
- stability;
- periodicity;
- phase;
- noise;
- clipping;
- DC offset;
- dynamics;
- saturation;
- harmonic evolution;
- detected regions;
- classification.

## 28.2 Decision Report

Explains:

- selected conversion mode;
- selected profile;
- working pitch;
- repitch;
- accepted cycles;
- rejected cycles;
- reconstruction method;
- placement method;
- interpolation method;
- applied repairs.

## 28.3 XT Native Report

Per wave:

- reconstruction error;
- harmonic preservation;
- bass preservation;
- selected alignment;
- polarity;
- rotation;
- 64-point quality;
- reconstruction result.

## 28.4 Wavetable Map

Per position:

- role;
- source;
- source time;
- harmonic richness;
- usefulness;
- importance;
- score;
- real or interpolated;
- structural or redundant.

## 28.5 Quality Report

Scores include:

- Loop;
- Phase;
- Interpolation;
- Harmonic Preservation;
- Bass Preservation;
- Sub;
- Bass;
- Lead;
- Pad;
- Sweep;
- Aliasing;
- XT Compatibility;
- Overall.

## 28.6 XT Patch Guide

Provides justified starting recommendations for:

- Wave Start;
- Wave End;
- Wave Envelope Amount;
- interpolation;
- Sync;
- FM;
- Keytracking;
- filter type;
- Cutoff;
- Resonance;
- Drive;
- filter envelope;
- amplitude envelope;
- LFO;
- rate;
- modulation amount;
- Velocity;
- Aftertouch;
- Mod Wheel.

## 28.7 Additional reports

- Build Manifest;
- Safety Report;
- Batch Report;
- Transmission Report;
- Read-back Comparison Report.

---

# 29. Exports

The program shall be able to export:

- 61 individual WAV files;
- concatenated table WAV;
- native data for each wave;
- reconstructed waves;
- before/after versions;
- TXT reports;
- Markdown reports;
- JSON data;
- analysis log;
- processing configuration;
- project file;
- analysis plots;
- patch guide;
- one SysEx package.

A typical export bundle may use:

```text
PROJECT/
├── source/
├── waves/
│   ├── wave_01.wav
│   └── ...
├── table/
│   └── MicrowaveXT_Table.wav
├── preview/
├── reports/
├── project/
├── logs/
└── sysex/
    └── MICROWAVE_XT_PACKAGE.syx
```

---

# 30. SysEx package

The software shall produce one `.syx` file containing multiple ordered SysEx messages.

Typical complete package:

```text
01. WAVD User Wave 1000
02. WAVD User Wave 1001
...
61. WAVD User Wave 1060
62. WCTD User Wavetable 097
63. SNDD named Sound to A001
```

This is one user-facing file, not one undocumented monolithic message.

## 30.1 Confirmed address families

- 250 User Waves: `1000–1249`;
- 61 consecutive User Waves allow a maximum starting location of `1189`;
- 32 User Wavetables: displayed `097–128`;
- observed internal table addresses: `96–127`;
- Sounds: `A001–A128`, `B001–B128`, or Edit Buffer;
- Sound name: up to 16 ASCII characters;
- Device ID: `0–126`;
- Device ID `127`: broadcast, opt-in only.

The WCTD format has no confirmed name field. A friendly wavetable name may exist in project metadata and reports only.

## 30.2 Safety

Before generation or transmission, the software shall show:

- every User Wave destination that will be overwritten;
- the User Wavetable destination;
- the Sound destination;
- collisions with the active project;
- Device ID;
- broadcast status;
- required backup warning.

The software shall support:

- export without transmission;
- configurable inter-message delay;
- direct MIDI transmission in a later validated stage;
- read-back request;
- byte-for-byte comparison;
- validation report.

No silent write is permitted.

---

# 31. Hardware-validation protocol

The development process shall maintain explicit hardware gates.

Required evidence includes:

- Everything backup before write testing;
- All Wavetables & Waves backup;
- Global backup where relevant;
- unit dumps for one known Sound, one User Wavetable, and one User Wave;
- MIDI capture from a known working editor when useful;
- asymmetric-cycle transmission and redump test;
- value-extreme tests;
- interpolation test with known references;
- tests for positions 60, 61, 62, and 63;
- controlled audio recordings;
- multiple notes and octaves;
- slow and fast scans;
- Aliasing settings;
- Time Quantization settings;
- Clipping modes;
- phase tests;
- repeated-note tests.

Hardware claims shall be categorized as:

- exact SysEx evidence;
- confirmed memory behavior;
- calibrated audible behavior;
- unresolved hypothesis.

---

# 32. Audio-calibration capture requirements

Reference captures shall be:

- mono;
- 24-bit;
- 96 kHz preferred, 48 kHz minimum;
- unprocessed;
- recorded with unchanged gain;
- free of EQ, compression, limiting, and normalization.

A neutral test patch shall use:

- oscillator 1 only;
- oscillator 2 at zero;
- Ring Mod at zero;
- Noise at zero;
- effects disabled;
- filter as neutral as possible;
- zero resonance;
- stable amplitude envelope;
- no modulation unless the test requires it;
- fixed phase when required.

---

# 33. Software quality requirements

The project shall guarantee:

- deterministic output;
- complete reproducibility;
- explainable decisions;
- visible metrics;
- versioned configuration;
- complete logging;
- modular architecture;
- explicit errors;
- unit tests;
- DSP tests;
- hardware tests;
- non-regression tests;
- preservation of original sources;
- non-destructive editing;
- ability to disable each correction;
- before/after comparison;
- Windows 11 compatibility;
- strict separation of DSP, GUI, export, and MIDI layers.

No private factory bank, user backup, copyrighted sound bank, or firmware image may be committed to the public repository.

---

## 33.1 Executable requirements and capability contract

The implementation shall bundle a versioned machine-readable compliance registry. The registry shall preserve every atomic cahier-des-charges requirement and shall record:

- stable requirement ID and exact requirement text;
- final scope status;
- observed baseline support state;
- existing evidence and tests;
- unresolved gap;
- corrected implementation destination;
- target modules, tests and acceptance path;
- source-document fingerprints;
- canonical registry SHA-256.

The initial registry schema contains exactly 206 requirements: 195 active obligations, nine deliberate exclusions and two post-prototype architecture items. Requirement IDs must be unique, ordered and non-empty. No active requirement may have an empty destination, target-module field or target-test field.

Schema evolution shall be explicit. Current payloads shall be validated strictly, supported legacy audit rows shall be adapted through a documented migration, and unknown future schema versions shall be rejected rather than interpreted on a best-effort basis.

The nine explicit exclusions shall have executable non-reintroduction gates. A documented exclusion is not considered forgotten functionality.


# 34. Prototype acceptance

`v1.0.0-prototype` is accepted only when a user can complete the following workflow without modifying source code:

```text
create or open project
→ import WAV/AIFF/FLAC
→ automatic mono conversion
→ analysis and classification
→ explainable mode/profile selection
→ pitch and cycle optimization
→ XT-native wave optimization
→ 61-position construction
→ Wavetable build
→ Sound build
→ preview
→ reports
→ safe destination selection
→ package build
→ package validation
→ optional transmission
→ read-back comparison
→ project save and reopen
```

All required automated tests, hardware gates, documentation, and safety checks must pass before the prototype tag is created.

---

# 35. Explicit exclusions

The public prototype specification excludes:

- MP3 import;
- mandatory manual time-range selection;
- stereo-content analysis after mono conversion;
- generic support for other synthesizers;
- generic PPG export;
- a Reese-only application architecture;
- mandatory WaveEdit dependency;
- opaque AI decisions;
- unverified claims of bit-exact DSP emulation.

These exclusions are deliberate scope decisions, not forgotten features.
