# W-MWXT-WAVETABLE-TOOL
## Public Roadmap and Requirements Traceability Matrix

**Project:** W-MWXT-WAVETABLE-TOOL  
**Owner:** R-MiT  
**Document type:** public development roadmap and traceability register  
**Document version:** 2.5-public<br>
**Baseline:** CODE V7 / `v0.7.0`<br>
**Target:** `v1.0.0-prototype`  
**Primary platform:** Windows 11  
**Status:** authoritative public execution order; CODE V8-0A through V8-0D closed, CODE V8-0E active

---

# 0. Purpose

This roadmap converts the public specification into controlled implementation stages.

Every requirement must map to:

```text
requirement → CODE stage → module → automated test → hardware test when required → acceptance gate
```

A CODE stage is not complete because it compiles. It is complete only when:

- its mapped tests pass;
- previous tests still pass;
- required hardware evidence exists;
- reports are generated;
- documentation is updated;
- the branch is reviewed;
- the acceptance gate is signed off.

The private French roadmap contains the full atomic working matrix and remains the detailed internal execution register. This public edition preserves the same scope, stage order, safety gates, and acceptance logic without publishing private working notes or local paths.

---

# 1. Scope statuses

| Status | Meaning |
|---|---|
| **IN** | Required for `v1.0.0-prototype` |
| **MODIFIED** | Retained under a later confirmed scope correction |
| **EXCLUDED** | Deliberately outside the prototype |
| **VERIFY** | Requires documentary or hardware confirmation |
| **POST-PROTOTYPE** | Architecture may prepare for it, but acceptance does not require it |

Priority order when sources conflict:

1. final scope corrections;
2. confirmed CODE V1 and hardware-dump evidence;
3. official technical documentation;
4. hardware experiments;
5. older provisional wording.

---

# 2. Final prototype workflow

```text
1. Create or open a project
2. Import WAV, AIFF, or FLAC
3. Convert to mono deterministically
4. Analyze signal, pitch, periodicity, phase, spectrum, and defects
5. Classify signal behavior and likely musical role
6. Select an explainable conversion mode
7. Select or optimize working pitch
8. Extract or reconstruct cycles
9. Apply the selected Auto Repair policy
10. Optimize every wave for XT representation
11. Build 61 user positions
12. Identify structural waves and transitions
13. Place, reorder, and interpolate positions
14. Build the User Wavetable
15. Build or adapt a Sound
16. Preview waves and scans
17. Generate reports and patch recommendations
18. Select safe XT destinations
19. Detect collisions and overwrite scope
20. Build one ordered .syx package
21. Save and reopen the project
22. Run the same workflow from the CLI
23. Process folders in Batch mode
24. Edit the table non-destructively
25. Optionally transmit to the XT
26. Read back and compare
```

---

# 3. Release map

| Stage | Version | Primary deliverable |
|---|---:|---|
| CODE V1 | `0.1.0` | Deterministic SysEx core |
| CODE V2 | `0.2.0` | Safe SysEx destinations and package builder |
| CODE V3 | `0.3.0` | Audio import, mono conversion, minimal project |
| CODE V4 | `0.4.0` | Time-domain DSP, pitch, periodicity, phase |
| CODE V5 | `0.5.0` | Spectral/perceptual analysis, classification, decisions |
| CODE V6 | `0.6.0` | Working pitch, segmentation, cycle ranking, reconstruction |
| CODE V7 | `0.7.0` | XT-native projection, first deterministic 61-position trajectory, QC, package, hardware acceptance |
| CODE V8-0 | part of `0.8.0` | Exhaustive post-V7 compliance closure, missing DSP/decision/repair contracts |
| CODE V8 | `0.8.0` | Generic WavetableBuild, placement, transitions, WCTD and hardware gates |
| CODE V9 | `0.9.0-alpha.1` | Sound, reports, exports, complete project format |
| CODE V10 | `0.9.0-alpha.2` | Preview, simulator, hardware calibration |
| CODE V11 | `0.9.0-alpha.3` | Non-destructive integrated editor |
| CODE V12 | `0.9.0-beta.1` | Final CLI, configuration, Batch |
| CODE V13 | `0.9.0-beta.2` | Studio GUI |
| CODE V14 | `0.9.0-rc.1` | MIDI transport and read-back |
| CODE V15 | `0.9.0-rc.2` | Hardening, packaging, documentation |
| Final prototype | `1.0.0-prototype` | Integrated accepted workflow |

---

# 4. CODE V1 — Deterministic SysEx core

## Objective

Create an exact parser, validator, model layer, and re-encoder for confirmed Microwave XT SysEx dumps.

## Implemented modules

```text
codec.py
constants.py
dump.py
errors.py
identity.py
message.py
models.py
cli.py
```

## Acceptance evidence

- 16 automated tests passed;
- four reference hardware dumps validated;
- all checksums valid;
- all message lengths valid;
- four byte-identical round trips;
- two independently captured Everything dumps identical;
- identity reply decoded;
- no private `.syx` committed.

## Gate

```text
STATUS: PASS
NEXT: CODE V2
```

---

# 5. CODE V2 — Hardened protocol and safe SysEx package builder

## Objective

Create safe destination types, allocation rules, collision analysis, ordered package generation, and human-readable manifests.

## Scope

- User Wave range `1000–1249`;
- one to 250 allocated waves;
- 61-wave start range `1000–1189`;
- User Wavetable displayed range `097–128`;
- observed internal range `96–127`;
- Sound destination A, B, or Edit Buffer;
- Sound name validation;
- Device ID `0–126`;
- broadcast `127` only through explicit opt-in;
- collision and overwrite report;
- deterministic ordered package;
- JSON and Markdown manifests;
- dry-run planning;
- package reopen and verification.

## Modules

```text
destinations.py
allocation.py
safety.py
package.py
manifest.py
```

## Models

```text
UserWaveRange
UserWavetableDestination
SoundDestination
DeviceAddress
PackageRequest
WaveAllocation
CollisionReport
SafetyReport
PackageManifest
PackageBuildResult
```

## Automated tests

- valid boundary addresses;
- invalid boundary addresses;
- 61 waves from 1000;
- 61 waves from 1189;
- rejection from 1190;
- displayed/internal Wavetable conversion;
- A/B/Edit Buffer Sound destinations;
- 16-character name behavior;
- broadcast opt-in;
- collision detection;
- deterministic package order;
- message checksums;
- package reparse;
- golden package;
- no CODE V1 regression.

## Hardware gate

After software acceptance:

1. create a fresh Everything backup;
2. reserve non-critical test destinations;
3. transmit manually with a proven SysEx utility;
4. redump written data;
5. compare sent and read-back data;
6. document any XT normalization or address transformation.

## Acceptance

A package containing:

```text
61 WAVD
1 WCTD
1 SNDD
```

must be valid, deterministic, collision-free, reopenable, documented, and confirmed by controlled read-back before CODE V3 begins.

---

# 6. CODE V3 — Audio import, mono conversion, minimal project

## Objective

Normalize supported audio into one deterministic internal representation and establish minimal project persistence.

## Scope

- WAV, AIFF, FLAC;
- format and metadata detection;
- source fingerprint;
- float internal representation;
- deterministic mono conversion;
- DC and invalid-value checks;
- source preservation;
- minimal project save/open.

## Modules

```text
audio/importers.py
audio/formats.py
audio/mono.py
audio/preprocessing.py
audio/measurements.py
audio/models.py
project/minimal_schema.py
project/persistence.py
```

## Tests

- common PCM and float WAV;
- AIFF;
- FLAC;
- unsupported format rejection;
- mono input;
- identical stereo;
- anti-phase stereo;
- silent channel;
- Unicode and long paths;
- NaN and infinity policy;
- silence;
- DC offset;
- save/open;
- source change detection;
- deterministic import.

## Acceptance

Every supported source becomes a valid `AudioSource` with mono samples, metadata, measurements, and fingerprint. Reopening the minimal project must reproduce the same imported state.

---

# 7. CODE V4 — Time-domain DSP, pitch, periodicity, and phase

## Objective

Produce stable, serializable, testable signal measurements.

## Scope

- fundamental;
- note and cents;
- local pitch track;
- pitch confidence;
- drift;
- vibrato;
- glissando;
- portamento;
- fast modulation;
- periodicity and quasi-periodicity;
- non-periodic energy;
- phase stability and discontinuity;
- amplitude envelope and stability;
- peak, RMS, crest factor;
- clipping;
- noise and SNR;
- transients;
- temporal change points.

## Modules

```text
analysis/pitch.py
analysis/pitch_motion.py
analysis/periodicity.py
analysis/phase.py
analysis/envelope.py
analysis/levels.py
analysis/noise.py
analysis/transients.py
analysis/change_points.py
analysis/models.py
```

## Test corpus

- sine;
- triangle;
- square;
- saw;
- detuned pair;
- vibrato;
- glissando;
- portamento;
- FM;
- AM;
- clipping;
- DC offset;
- noise at known SNR;
- transient;
- stable sustain;
- silence.

## Acceptance

All metrics shall include units, confidence where relevant, and documented tolerances. The same input must produce the same report.

---

# 8. CODE V5 — Spectral, perceptual, classification, and decision engine

## Objective

Convert the accepted CODE V4 measurements into deterministic spectral evidence,
explainable source classification, and auditable engineering guidance.

## Accepted release scope

### Spectral analysis

- deterministic framed FFT and active-frame selection;
- average and local spectra;
- dominant frequency and dominant-energy ratio;
- low, mid, and high band energy;
- centroid, bandwidth, roll-off, flatness, entropy, and flux;
- spectral stationarity and change evidence;
- component-level deterministic SHA-256.

### Harmonic and perceptual analysis

- fundamental-linked harmonic peaks;
- harmonic and residual energy;
- harmonic-to-residual ratio;
- odd/even balance and tristimulus;
- inharmonicity and spectral slope;
- Bark-band centroid, spread, and entropy;
- brightness, concentration, and noisiness;
- component-level deterministic SHA-256.

### Explainable source classification

Canonical families:

```text
silent
stable_tonal
evolving_tonal
noisy_texture
transient_rich
mixed_complex
```

Every classification includes bounded features, normalized scores, confidence,
ambiguity, evidence, deterministic tie-breaking, and a non-empty reason.

### Engineering decision layer

Canonical states:

```text
ready
review
not_recommended
```

Every decision includes readiness, risk, blockers where applicable, prioritized
recommendations, measured evidence, and a non-empty reason. Recommendations are
advisory and never automated.

### Final aggregate contract

`CodeV5Analysis` preserves every component report, validates the complete hash
chain and canonical sample identity, and produces one deterministic aggregate
SHA-256. The `analyze-audio` command exposes the complete report.

## Explicitly deferred scope

The following original roadmap concepts are not claimed as implemented in 0.5.0:

- dedicated formant and close-fundamental/beating models;
- explicit aliasing-risk estimation;
- musical multi-label role and profile selection;
- final conversion-mode selection;
- scan-continuity prediction tied to generated cycles;
- segmentation, working-pitch selection, reconstruction, and XT optimization.

These items remain assigned to later stages where cycle material and XT-native
representation exist.

## Implemented modules

```text
analysis/spectral.py
analysis/harmonic_perceptual.py
analysis/classification.py
analysis/decisions.py
analysis/code_v5.py
cli.py
```

## Acceptance evidence

```text
Targeted CODE V5-E : 50 passed
Public full suite   : 610 passed, 4 skipped
Private full suite  : 614 passed
```

Real-audio acceptance requires two byte-identical aggregate reports, valid
component links, an aggregate SHA-256, and preserved non-automated recommendations.
No opaque AI-only decision is permitted.

## Gate

```text
STATUS: PASS after automated and manual aggregate validation
NEXT: CODE V6
```

---

# 9. CODE V6 — Working pitch, segmentation, cycle ranking, reconstruction

## Status

```text
STATUS: COMPLETE
RELEASE: v0.6.0
FINAL AGGREGATE: CodeV6Analysis
FINAL CLI: analyze-code-v6
```

## Delivered scope

- octave-preserving working-pitch candidates;
- automatic, locked, and no-repitch policies;
- attack-aware deterministic segmentation;
- source-domain cycle discovery and quality metrics;
- representative ranking and deterministic top-N selection;
- explicit forced-cycle override with rejected-candidate safety gate;
- spectral, dominant-partial, and hybrid reconstruction;
- deterministic 128-point float-domain waves;
- complete CODE V5 → V6 hash-chain validation;
- final immutable aggregate and release CLI.

## Delivered modules

```text
analysis/pitch_candidates.py
analysis/repitch.py
analysis/segmentation.py
analysis/cycle_detection.py
analysis/cycle_selection.py
analysis/reconstruction.py
analysis/code_v6.py
```

## Acceptance evidence

```text
V6-A targeted: 58 passed
V6-B targeted: 58 passed
V6-C targeted: 58 passed
V6-D targeted: 58 passed
V6-E targeted: 58 passed
V6-E public baseline: 900 passed, 4 skipped
V6-E private baseline: 904 passed
Real-audio gates: PASS for V6-A through V6-E
```

The final V6-F validation records the aggregate, release-version, documentation, public/private full-suite, deterministic real-audio, commit, pull-request, merge, and tag gates.

## Safety boundary

CODE V6 does not quantize XT waves, allocate User Wave destinations, build SysEx, transmit MIDI, or mutate instrument memory. These remain gated by CODE V7 and later stages.

---

# 10. CODE V7 — XT-native representation, trajectory, QC, and hardware acceptance

## Status

```text
STATUS: COMPLETE
RELEASE: v0.7.0
BRANCH: code-v7-xt-native-optimization
HARDWARE: WALDORF MICROWAVE XT OS 2.33
```

## Delivered scope

- documented offset-binary WAVD coding and byte-identical round trips;
- documented 64-to-128 reverse-negate reconstruction;
- safe generated integer range `-127..127`;
- deterministic 128-to-64 XT-native projection;
- exhaustive 128-phase evaluation;
- deterministic global phase-path optimization;
- complete 61-position editable trajectory;
- deterministic QC of 60 transitions and 59 curvature points;
- deterministic mathematical previews;
- deterministic 61-WAVD + 1-WCTD + 1-SNDD package;
- exact restore bundle;
- manual write, restore, final installation, and audio acceptance.

## Acceptance evidence

```text
Pre-release public suite  : 1027 passed, 4 skipped
Pre-release private suite : 1031 passed
Final public suite        : 1035 passed, 4 skipped
Final private suite       : 1039 passed
First installation        : 63/63 exact
Restore                    : 63/63 exact
Final installation        : 63/63 exact
Hardware audio acceptance : PASS
Package SHA-256            : 82724d493c889afe27a44f0550355bce1764e0054621f4a35b373c9c8f08c425
Restore SHA-256            : a1ee24820a1dd77b5e283d3595d160cc8cbb8ee08a176f980eea9adf913861d6
```

## Scope sequencing note

The broader provisional Auto Repair scope is not claimed by release `0.7.0`. It requires separate policies, tests, and acceptance gates.

## Safety boundary

CODE V7 never opens a MIDI port or writes the instrument automatically. Private dumps, audio captures, generated SysEx files, and private evidence remain outside Git.

---

# 10A. CODE V8-0 — Exhaustive post-V7 compliance closure

## Purpose

CODE V8-0 is mandatory before the generic V8 builder. It closes every active cahier-des-charges requirement required by V8 that is absent or only partial after release `v0.7.0`. It does not rewrite the accepted V7 hardware path.

## V8-0A — executable compliance registry

V8-0A introduces a strict machine-readable registry containing all 206 requirements. The contract records the exact requirement text, scope, V7 baseline status, explicit support state, evidence, tests, gap, corrected destination, target modules, target tests, source fingerprints and a canonical registry SHA-256.

The registry acceptance gates are:

```text
206 unique IDs
195 active obligations
9 deliberate exclusions with executable non-reintroduction gates
2 post-prototype architecture items
0 empty destination
0 empty target module field
0 empty target test field
strict schema version 1
adapter and migration tests
Ubuntu and Windows CI on Python 3.11, 3.12 and 3.13
```

V8-0A is a traceability and contract stage. It does not claim that partial or planned capabilities are already implemented. Their closure remains assigned to V8-0B through V8-0F or the later version recorded by each requirement.

## V8-0B - import, signal, behavior, and regions

V8-0B closes the incomplete import, signal, behavior, and region requirements without mutating the accepted V4-V6 aggregate schemas. It adds:

```text
complete mono policy and scored automatic selection
rapid frequency-modulation analysis
time-varying saturation and asymmetry analysis
density and complexity analysis
beating, unison and detune analysis
eight explainable behavior classes
eight named active region classes plus silence coverage
useful-change and long-region redundancy scoring
interest-weighted advisory allocation
```

The historical CODE V5 source classifier and CODE V6 segmentation remain available unchanged. New results are linked through `SignalExtensionAnalysis`, `BehaviorClassification`, and `RegionInterestAnalysis`. Final wave selection and placement remain assigned to later CODE V8 stages.

## V8-0C - spectrum, perceptual analysis, classification, and modes

V8-0C adds source-domain spectral and perceptual extensions without mutating accepted V5/V6 schemas:

```text
four-band spectral evolution and partial inventory
broad formant candidates and source-span spectral correlation
nine bounded perceptual feature proxies
weighted perceptual distance and transitive redundancy groups
ordered-sweep continuity
27 canonical multi-label musical classes
five explainable conversion modes
manual override, warnings, ambiguity and explicit refusal
```

Every declared conversion mode resolves to an importable existing callable. Musical labels guide priorities through a capped prior and cannot independently force a conversion mode.

## V8-0D - XT-native resampling and effective profiles

V8-0D closes the XT-relative comparison and treatment contracts while preserving the accepted V7 serialized path:

```text
periodic windowed-sinc, Fourier, and linear resampling
explicit anti-aliasing, normalization, phase, fundamental, ringing, and extreme evidence
nearest and deterministic error-feedback XT quantization
strict generated range -127..127 and forbidden -128 gate
six transforms and all 128 phase/start positions
six half-wave or reduction methods
complete source-versus-XT wave metrics and multi-note aliasing analysis
nine effective optimization profiles and capped profile selection
Bass-specific working-pitch comparison, Sub/Bass scores, and sequence consistency
independent optimization of every wave, including exactly 61-wave sets
```

V8-0D does not change the V7 `XtProjectionSet`, trajectory, QC, package, or hardware evidence.

## V8-0E - complete Auto Repair policies and actions

V8-0E unifies the previously distributed protection and correction logic under one additive deterministic repair contract:

```text
17 canonical defect detectors and action mappings
AUTO, COMPARE, IGNORE, and PRESERVE policies
canonical defaults and per-defect overrides
explicit context refusal and review-required states
separate before, candidate, and selected branches
complete metrics, logs, evidence, and deterministic hashes
profile-aware controlled-defect preservation
ordered wave-sequence processing, including exactly 61 waves
```

V8-0E does not change historical V5, V6, V7, or V8-0D schemas. Reports, preview audition, editor controls, and the final 61-position builder remain assigned to their later stages.

## Remaining V8-0 order

```text
V8-0E complete Auto Repair policies and actions
V8-0F aggregate pre-V8 contract and zero required debt gate
```

---

# 11. CODE V8 — 61-position generation, placement, and transitions

## Objective

Build a complete musically useful table plan.

## Scope

- always 61 user positions;
- real/reconstructed mix;
- structural-wave detection;
- redundancy detection;
- transition labeling;
- essential-position report;
- deterministic variants;
- placement optimization;
- locked positions;
- chronology constraints;
- waveform, spectral, harmonic, and perceptual interpolation;
- adaptive step density;
- continuity checks;
- fundamental, level, and polarity protection;
- Waldorf Factory-style profile;
- positions 61–63 fixed behavior.

## Modules

```text
wavetable/builder.py
wavetable/usefulness.py
wavetable/deduplication.py
wavetable/selection.py
wavetable/ordering.py
wavetable/placement.py
wavetable/interpolation.py
wavetable/continuity.py
wavetable/variants.py
wavetable/factory_style.py
```

## Hardware gates

- WCTD containing two known references;
- intermediate XT positions;
- positions 60, 61, 62, 63;
- slow and fast scans;
- read-back of the table.

## Acceptance

The stage shall output a valid 61-position plan, structural-wave count, essential positions, transition map, continuity report, and valid WCTD model.

---

# 12. CODE V9 — Sound, reports, exports, complete project

## Objective

Turn a table plan into a complete reproducible project and export bundle.

## Scope

### Sound

- template or existing Sound source;
- Wavetable selection;
- essential oscillator and modulation parameters;
- 16-character name;
- A/B/Edit Buffer destination;
- preserve untouched bytes;
- neutral calibration template;
- musical templates.

### Reports

- DSP Analysis;
- Decision;
- XT Native;
- Wavetable Map;
- Quality;
- XT Patch Guide;
- Build Manifest;
- Safety.

### Exports

- 61 WAV files;
- concatenated table WAV;
- native data;
- reconstructed data;
- before/after;
- Markdown;
- TXT;
- JSON;
- plots;
- logs;
- project;
- patch guide;
- SysEx package.

### Project

- versioned schema;
- source fingerprint;
- analysis state;
- decision state;
- wave state;
- table state;
- Sound state;
- destination state;
- build state;
- cache policy;
- migration policy.

## Modules

```text
sound/templates.py
sound/parameters.py
sound/naming.py
sound/patch_builder.py
reports/*.py
exports/*.py
project/schema.py
project/persistence.py
project/migrations.py
```

## Acceptance

Saving, reopening, and rebuilding a project shall produce the same binary package and reports. A friendly table name may exist in project metadata but must not be written into WCTD.

---

# 13. CODE V10 — Preview, simulator, and hardware calibration

## Objective

Render and analyze the generated material before hardware transmission.

## Scope

- single-wave oscillator;
- XT reconstruction;
- table interpolation;
- position scans;
- LFO scans;
- envelope scans;
- start/end;
- direction;
- speed;
- fixed position;
- multiple notes;
- multiple octaves;
- slow/fast/bidirectional presets;
- before/after;
- original/optimized order;
- artifact detectors;
- controlled capture protocol;
- calibration profiles;
- published limits.

## Modules

```text
preview/oscillator.py
preview/interpolation.py
preview/scanner.py
preview/modulation.py
preview/renderer.py
preview/artifacts.py
calibration/protocol.py
calibration/measurements.py
calibration/comparison.py
calibration/profile.py
```

## Hardware evidence

Controlled mono captures at 24-bit and 96 kHz preferred, 48 kHz minimum, with stable gain and no processing.

Test corpus:

- known waves;
- multiple notes;
- multiple octaves;
- slow and fast scans;
- Aliasing 0–5;
- Time Quantization 0–5;
- Clipping modes;
- phase settings;
- repeated notes.

## Acceptance

The simulator shall be structurally exact where confirmed, audibly calibrated within documented conditions, and explicit about unresolved differences. Bit-exact DSP emulation shall not be claimed.

---

# 14. CODE V11 — Non-destructive integrated editor

## Objective

Allow controlled manual refinement without breaking reproducibility.

## Operations

- move;
- delete;
- duplicate;
- replace;
- lock;
- polarity;
- time reversal;
- rotation;
- normalize;
- gain;
- smooth;
- emphasize;
- interpolate;
- fill range;
- reorder range;
- audition;
- compare;
- undo/redo;
- variants;
- re-optimize selection.

## Architecture

Every edit is a domain command with:

- input state;
- parameters;
- output state;
- inverse operation or history restoration;
- log entry;
- affected requirement IDs.

## Modules

```text
editor/commands.py
editor/history.py
editor/selection.py
editor/variants.py
editor/comparison.py
```

## Acceptance

A complete undo sequence must restore the original build byte-for-byte and metadata-for-metadata.

---

# 15. CODE V12 — Final CLI, configuration, and Batch

## Objective

Expose the complete engine without the GUI and support reproducible folder processing.

## CLI scope

- analyze;
- build;
- preview;
- report;
- export;
- package;
- validate;
- batch;
- project;
- configuration file;
- profile/mode overrides;
- pitch and repitch controls;
- repair policy;
- output selection;
- deterministic execution.

## Batch scope

- discovery;
- one isolated job per source;
- one export directory per source;
- one report set per source;
- global ranking;
- rejected files;
- errors;
- selected modes;
- scores;
- fail-fast option;
- default continuation after isolated errors.

## Modules

```text
cli/commands.py
cli/config.py
cli/output.py
batch/discovery.py
batch/runner.py
batch/isolation.py
batch/report.py
batch/ranking.py
config/schema.py
config/determinism.py
```

## Acceptance

The CLI shall reproduce GUI-independent builds and Batch shall continue safely after a source-level failure unless fail-fast is selected.

---

# 16. CODE V13 — Studio GUI

## Objective

Provide an accessible Windows workflow over already validated domain engines.

## Main views

- Project;
- Import;
- Analysis;
- Cycle candidates;
- User Waves;
- Wavetable;
- Sound;
- Preview;
- Package and safety;
- Validation and read-back;
- Reports;
- Batch.

## Visuals

- source waveform;
- regions;
- zero crossings;
- pitch;
- FFT;
- spectrogram;
- harmonics;
- phase;
- levels;
- saturation;
- 61 positions;
- wave metrics;
- essential positions;
- source origin;
- 64/128 comparison;
- before/after comparison.

## Architecture

GUI widgets may not implement DSP or SysEx domain logic. Controllers and view models must remain testable without Qt.

## Acceptance

The complete pre-MIDI workflow shall be usable on Windows 11 at common display scales, with actionable errors and no hidden destructive action.

---

# 17. CODE V14 — MIDI transport and read-back

## Objective

Transmit validated packages to the XT and verify the resulting memory state.

## Scope

- MIDI-port discovery;
- port selection;
- Device ID;
- inter-message delay;
- message-by-message progress;
- stop control;
- transmission log;
- backup confirmation;
- overwrite confirmation;
- read-back request;
- byte comparison;
- normalized-difference reporting;
- retry policy;
- transmission report.

## Modules

```text
midi/ports.py
midi/transport.py
midi/pacing.py
midi/readback.py
midi/verification.py
midi/models.py
```

## Safety gate

Transmission remains blocked until:

- backup acknowledged;
- port confirmed;
- Device ID confirmed;
- destinations confirmed;
- manifest reviewed;
- broadcast explicitly authorized when used;
- overwrite confirmation completed.

## Acceptance

A controlled package shall transmit in the correct order, the XT shall return data, and the comparison report shall classify the result as confirmed, normalized-but-explained, different, partial, or failed.

---

# 18. CODE V15 — Hardening, packaging, and documentation

## Objective

Prepare a reproducible prototype distribution.

## Scope

- dependency review;
- license review;
- supported Python matrix;
- Windows packaging;
- clean-machine installation;
- configuration migrations;
- project migrations;
- performance review;
- cancellation and progress;
- logging;
- error catalogue;
- security review;
- public documentation;
- private hardware protocol;
- backup/restore guide;
- release checklist.

## CI matrix

At minimum:

- supported Python versions;
- Linux test runner;
- Windows test runner;
- public tests without private dumps;
- packaging test;
- install-and-run test.

## Acceptance

A clean Windows 11 machine shall install and run the prototype, complete a documented sample workflow, and pass the public test suite.

---

# 19. `v1.0.0-prototype` integration gate

The final prototype is accepted only when:

- all CODE gates are closed;
- the full public test suite passes;
- private hardware tests pass or carry documented limits;
- no private dump is committed;
- the complete workflow needs no source-code modification;
- project reopen produces the same build;
- the package is valid and reopenable;
- overwrite scope is explicit;
- read-back works for the validated hardware path;
- simulation limits are published;
- CLI, GUI, Batch, editor, reports, and exports are documented;
- backup and restore procedures are documented.

Tag:

```text
v1.0.0-prototype
```

---

# 20. Public grouped traceability matrix

The private matrix contains 206 atomic or tightly grouped requirements. The table below preserves complete family coverage in a public reviewable form.

| Requirement family | IDs | Status | CODE stage(s) | Primary modules | Test evidence | Acceptance gate |
|---|---|---|---|---|---|---|
| Import and source handling | `CDC-IMP-001..010` | IN / MODIFIED / EXCLUDED | V3, V6, V12 | `audio/*`, `project/*`, `batch/*` | format fixtures, path fixtures, mono policies, project reopen, MP3 rejection | WAV/AIFF/FLAC deterministic; mono before DSP; no MP3; no mandatory time range |
| General signal analysis | `CDC-SIG-001..015` | IN / EXCLUDED | V3–V5 | `analysis/*`, `spectral/*`, `decision/*` | synthetic pitch, modulation, noise, level, transient, phase corpus | all measurements serialized; signal class and confidence produced |
| Spectral and harmonic analysis | `CDC-SPEC-001..013` | IN | V5, V7, V10 | `spectral/*`, `xt/wave_metrics.py`, `preview/*` | tones, harmonic series, formants, beating, morphs, multi-note aliasing | metrics numerically validated and linked to decisions |
| Psychoacoustic analysis | `CDC-PSY-001..007` | IN | V5, V7, V8, V10 | `perceptual/*`, `wavetable/*`, `calibration/*` | ordered perceptual fixtures and hardware comparisons | perceptual scores stable and useful for selection/continuity |
| Musical classification | `CDC-CLS-001..002` | IN | V5 | `decision/musical_classifier.py`, `mode_selector.py` | labelled/synthetic corpus and ambiguous cases | multi-label output, confidence, explanation; no class-only forcing |
| Conversion modes and overrides | `CDC-MODE-001..010` | IN / EXCLUDED | V5, V6, V7, V11–V13 | `decision/*`, `analysis/*`, `repair/*`, `editor/*` | one fixture per mode, override tests, lock tests | selected mode explained; overrides honored; manual time range absent |
| Pitch optimization | `CDC-PITCH-001..005` | IN | V4, V6, V7 | `analysis/pitch*.py`, `repitch.py`, `profiles/*` | known pitches and working-pitch comparisons | original/working pitch and trade-offs reported |
| Cycle detection and ranking | `CDC-CYC-001..006` | IN | V6, V7, V11, V13 | `analysis/cycle*.py`, `xt/wave_metrics.py`, `editor/*` | clean, noisy, atypical, representative cycles | top candidates ranked with full metrics and reasons |
| Region segmentation | `CDC-REG-001..006` | IN | V5, V6, V8, V13 | `analysis/segmentation.py`, `spectral/flux.py`, `wavetable/*` | multi-segment and non-uniform evolution fixtures | useful regions selected automatically and shown |
| 61-position generation | `CDC-W61-001..007` | IN | V6–V9 | `wavetable/builder.py`, models, reports | all modes, low/high candidate counts, schema tests | exactly 61 valid user positions with complete metadata |
| Structural usefulness | `CDC-USE-001..004` | IN | V8, V9 | `usefulness.py`, `deduplication.py`, reports | duplicate/keyframe/interpolation fixtures | structural count and essential positions reported |
| Placement optimization | `CDC-PLC-001..007` | IN | V8, V11 | `placement.py`, `ordering.py`, `continuity.py`, profiles | alternative orders and locked slots | deterministic weighted order and visible variants |
| Transition generation | `CDC-TRN-001..007` | IN | V8 | `interpolation.py`, `continuity.py`, repair | waveform/spectral/perceptual pathological cases | no unhandled fundamental loss, level dip, or polarity error |
| XT-native optimization | `CDC-XT-001..007` | IN / VERIFY | V7, V11, V13 | `xt/reconstruction.py`, `symmetry.py`, metrics | golden vectors plus asymmetric hardware test | confirmed versioned reconstruction and best-candidate trace |
| Resampling and quantization | `CDC-RSM-001..007` | IN | V7 | `xt/resampling.py`, `quantization.py`, metrics | sweeps, impulses, extremes, bass fixtures | exact target shape/domain and bounded documented error |
| Auto Repair | `CDC-REP-001..003` | IN | V7, V10, V11, V13 | `repair/*`, reports, preview | one fixture per detector and policy | exact logged action; before/after available |
| Bass/Sub specialization | `CDC-BASS-001..007` | IN | V5–V9 | profiles, metrics, continuity, reports | bass corpus, phase/subharmonic cases | fundamental/H2/H3 priority and separate Sub/Bass scores |
| Musical profiles | `CDC-PROF-001..003` | IN | V5, V7, V8 | `profile_selector.py`, weights, factory style | one fixture per profile | profile-specific weights; Experimental preservation explicit |
| Simulation and preview | `CDC-SIM-001..009` | IN / POST-PROTOTYPE | V10, V13, V15 | `preview/*`, `calibration/*` | golden rendering, artifact fixtures, XT captures | structurally exact where confirmed; calibrated limits published; no bit-exact claim |
| Editor | `CDC-EDT-001..003` | IN | V11, V13 | `editor/*` | one test per command, full undo, variants | every command reversible; original state exactly restorable |
| GUI | `CDC-GUI-001..005` | IN | V13 | views, controllers, view models | controller tests, snapshots, workflow test | all required views; no DSP in widgets |
| CLI | `CDC-CLI-001..005` | IN | V12 | `cli/*`, `config/*` | end-to-end commands and config combinations | requested outputs only; deterministic reruns |
| Batch | `CDC-BAT-001..005` | IN | V12 | `batch/*` | mixed folder, invalid file, partial error | isolated outputs and complete global report |
| Reports | `CDC-RPT-001..005` | IN | V5, V9, V12, V14 | `reports/*`, explanations | schemas, snapshots, mode/profile cases | all report sections present and justified |
| Exports | `CDC-EXP-001..005` | IN | V2, V9 | `exports/*`, `sysex/package.py`, project | each format, bundle snapshot, golden package | readable manifested files; WCTD has no invented name |
| Quality | `CDC-QLT-001..011` | IN | all stages | config, logging, errors, tests, architecture | double-build hashes, architecture checks, CI | deterministic, modular, non-destructive, Windows-compatible |
| Explicit exclusions | `CDC-EXC-001..005` | EXCLUDED | all audits | documentation, CLI/GUI audit | non-introduction tests | no other synth target, PPG export, Reese-only design, WaveEdit dependency, or opaque AI |
| SysEx protocol and safety | `CDC-SYX-001..016` | IN / VERIFY | V1, V2, V7–V9, V13, V14 | constants, allocation, package, Sound, MIDI | dumps, limits, golden messages, read-back | exact ranges/messages/order; overwrite list; backup and broadcast controls |
| Hardware validation levels | `CDC-HW-001..011` | IN / VERIFY / POST-PROTOTYPE | pre-V2, V2, V7–V10, V14 | private reference set, calibration, hardware protocol | dumps, MIDI captures, asymmetric test, controlled audio | evidence classified and stored; unresolved claims remain explicit |

---

# 21. Mandatory hardware test order

## HW-00 — Safety backup

Before any write:

- Everything;
- All Wavetables & Waves;
- Global when relevant;
- hashes recorded;
- restore path documented.

## HW-01 — User Wavetable mapping

Confirm:

```text
displayed 097–128
internal 96–127
```

Any documentation inconsistency must be resolved against the actual instrument and redump.

## HW-02 — User Wave sign and extremes

Send known signed values, redump, and compare.

## HW-03 — Asymmetric full-cycle versus half-cycle

This is the critical V7 gate that determines the reconstruction architecture.

## HW-04 — WCTD interpolation

Use two known references and measure intermediate positions.

## HW-05 — Fixed positions

Confirm positions 61, 62, and 63 and the boundary at position 60.

## HW-06 — Sound

Verify name, table index, selected parameters, destination, and preservation of untouched bytes.

## HW-07 — Complete package

Send ordered WAVD → WCTD → SNDD, redump all affected objects, and compare.

## HW-08 — Audio calibration

Record the controlled corpus and update the versioned simulator calibration profile.

No later CODE stage may claim hardware behavior that belongs to an unfinished earlier hardware gate.

---

# 22. Validation chain for every CODE stage

```text
1. Confirm mapped requirements
2. Create a dedicated branch
3. Implement small atomic commits
4. Add unit tests
5. Add integration tests
6. Run all earlier regression tests
7. Run local manual tests
8. Run required hardware tests
9. Preserve evidence
10. Generate validation report
11. Correct discrepancies
12. Re-run the full suite
13. Mark PASS or PASS WITH DOCUMENTED LIMITS
14. Open pull request
15. Review CI and evidence
16. Merge
17. Tag the stage
18. Start the next CODE stage
```

Allowed statuses:

```text
PASS
PASS WITH DOCUMENTED LIMITS
NEEDS CORRECTION
BLOCKED BY HARDWARE TEST
BLOCKED BY MISSING EVIDENCE
```

---

# 23. Evidence to preserve

For each stage:

- test log;
- package or golden-vector hashes;
- validation report;
- before/after measurements;
- hardware dump hashes where relevant;
- MIDI capture where relevant;
- audio capture manifest where relevant;
- screenshots only when they add unique GUI evidence;
- commit SHA;
- pull request;
- tag;
- known limitations.

Private binary material remains outside Git.

---

# 24. Target repository structure

```text
src/w_mwxt_wavetable_tool/
├── sysex/
├── audio/
├── analysis/
├── spectral/
├── perceptual/
├── decision/
├── reconstruction/
├── xt/
├── repair/
├── profiles/
├── wavetable/
├── sound/
├── project/
├── reports/
├── exports/
├── preview/
├── calibration/
├── editor/
├── cli/
├── batch/
├── midi/
└── gui/

tests/
├── unit/
├── integration/
├── golden/
├── dsp/
└── hardware_contracts/

docs/
├── specification/
├── roadmap/
├── validation/
├── user/
├── developer/
└── safety/

private_docs/          # ignored by Git
private_dumps/         # ignored by Git
private_captures/      # ignored by Git
```

---

# 25. First action after CODE V1

Create and work on:

```text
code-v2-package-builder
```

First commit sequence:

```text
CODE V2: add destination range constants
CODE V2: add typed destination models
CODE V2: add consecutive wave allocation
CODE V2: add collision and overwrite reporting
CODE V2: add allocation boundary tests
CODE V2: add ordered package request model
CODE V2: add deterministic package serializer
CODE V2: add public and private manifests
CODE V2: add golden package tests
CODE V2: document hardware read-back gate
```

Do not begin audio import until the CODE V2 package and read-back gate are accepted.

---

# 26. Reference status

This roadmap remains active until replaced by a versioned successor.

A major scope change requires:

- specification update;
- requirement-matrix update;
- affected CODE-stage update;
- test-plan update;
- acceptance-gate update;
- changelog entry.
