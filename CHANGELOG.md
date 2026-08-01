# Changelog

All notable changes to **W-MWXT-WAVETABLE-TOOL** are documented here.

## 0.6.0 — CODE V6

### Working pitch and source segmentation

- Added deterministic octave-preserving working-pitch candidates, automatic repitch planning, explicit pitch lock, and no-repitch policy.
- Added deterministic attack-aware segmentation with complete source coverage, usable-segment selection, and traceable boundary/classification reasons.

### Cycle discovery, ranking, and reconstruction

- Added source-domain cycle discovery with periodicity, seam, energy, spectral, period-error, and composite quality metrics.
- Added deterministic representative ranking, temporal and segment novelty, top-N selection up to 61 candidates, and explicit forced-cycle override.
- Added spectral, dominant-partial, and hybrid float-domain reconstruction with 128-point defaults, DC control, peak normalization, seam metrics, and spectral-similarity evidence.

### Aggregate, CLI, and release

- Added the immutable `CodeV6Analysis` aggregate with strict CODE V5 → V6 component links and one final SHA-256.
- Added the final `analyze-code-v6` command while preserving all focused V6 commands and the stable CODE V5 `analyze-audio` command.
- Updated public API exports, README, roadmap, validation evidence, release notes, package metadata, and version to `0.6.0`.

### Validation

- CODE V6-A through V6-E targeted suites: 58 passed at every intermediate stage.
- CODE V6-E public/private baselines before release closure: 900 passed, 4 skipped / 904 passed.
- Real-audio gates passed for working pitch, segmentation, cycle discovery, representative selection, and reconstruction with byte-identical reports and unchanged source audio.
- CODE V6-F final aggregate, complete-suite, and release gates are recorded in `docs/validation/CODE_V6_F_VALIDATION.md`.

## 0.5.0 — CODE V5

### Spectral and perceptual analysis

- Added deterministic framed FFT, local and aggregate spectra, band energy, centroid, bandwidth, roll-off, flatness, entropy, flux, dominant-frequency, and stationarity evidence.
- Added harmonic/residual energy, odd/even balance, tristimulus, inharmonicity, spectral slope, Bark-band descriptors, brightness, concentration, and noisiness.

### Explainable classification and decisions

- Added six canonical source families with normalized scores, confidence, ambiguity, evidence, and deterministic tie-breaking.
- Added readiness/risk decisions, blockers, and prioritized recommendations that are always non-automated.
- Added the immutable `CodeV5Analysis` aggregate with complete component-link validation and one final SHA-256.
- Added `spectral-analyze`, `perceptual-analyze`, `classify-audio`, `recommend-audio`, and final `analyze-audio` CLI reports.

### Validation

- CODE V5-A targeted suite: 35 passed.
- CODE V5-B targeted suite: 38 passed.
- CODE V5-C targeted suite: 45 passed.
- CODE V5-D targeted suite: 45 passed.
- CODE V5-E targeted suite: 50 passed.
- Final public/private targets: 610 passed, 4 skipped / 614 passed.
- Manual real-audio classification, decision, and aggregate determinism gates passed before release closure.

## 0.4.0 — CODE V4

### Deterministic signal analysis

- Added global level, clipping, DC, asymmetry, saturation, and envelope analysis.
- Added deterministic fundamental-pitch, note, cents-deviation, periodicity, and pitch-stability analysis.
- Added phase-continuity, cycle-discontinuity, and pitch-motion analysis.
- Added deterministic noise-floor, SNR, and noise-stationarity estimates.
- Added transient, onset, and energy/spectral change-point detection.
- Added the immutable aggregate `SignalAnalysis` contract with shared sample identity.
- Added component SHA-256 fingerprints and one aggregate analysis SHA-256.
- Consolidated the `signal-analyze` CLI around the aggregate contract while preserving accepted component keys.

### Validation

- CODE V4-A targeted suite: 37 passed.
- CODE V4-B targeted suite: 46 passed.
- CODE V4-C targeted suite: 32 passed.
- CODE V4-D targeted suite: 44 passed.
- V4-A public/private gates: 244 passed, 4 skipped / 248 passed.
- V4-B public/private gates: 290 passed, 4 skipped / 294 passed.
- V4-C public/private gates: 322 passed, 4 skipped / 326 passed.
- V4-D public/private gates: 366 passed, 4 skipped / 370 passed.
- Manual real-audio determinism gates passed for pitch/periodicity, phase/motion, noise, and transient/change analysis.

## 0.3.0 — CODE V3

### Audio import

- Added deterministic WAV, AIFF, and FLAC import through libsndfile.
- Added content-based container detection and extension-consistency reporting.
- Added immutable contiguous `float64` internal samples.
- Added deterministic mono conversion policies and explanations.
- Added silent-channel handling and anti-phase stereo protection.
- Added NaN and infinity reject/zero policies.
- Added peak, RMS, mean, extrema, silence, and DC-offset measurements.
- Added source, mono-sample, and imported-state SHA-256 fingerprints.
- Added `audio-inspect` JSON reporting.

### Minimal projects

- Added the deterministic `.mwxtproj` container.
- Added canonical JSON manifests and canonical little-endian embedded mono samples.
- Added atomic saves and explicit overwrite protection.
- Added strict schema, archive-shape, length, and hash validation.
- Added source status detection for unchanged, changed, missing, unavailable, and ignored sources.
- Added strict, embedded-fallback, and source-ignore policies.
- Added exact imported-state reconstruction without re-decoding the source.
- Added `project-create` and `project-open` CLI commands.
- Added Unicode and long-path coverage.

### Validation

- CODE V3-A targeted suite: 49 passed.
- CODE V3-B targeted suite: 38 passed.
- Pre-release public suite: 203 passed, 4 skipped.
- Pre-release private suite: 207 passed.
- Manual source-preservation, deterministic import, deterministic project-save, strict-source, and embedded-fallback gates passed.

## 0.2.0 — CODE V2

- Added safe typed Device ID, Sound, User Wavetable, and User Wave destinations.
- Added explicit broadcast opt-in.
- Added consecutive User Wave allocation and collision analysis.
- Added deterministic ordered `WAVD → WCTD → SNDD` package generation.
- Added JSON and Markdown manifests.
- Added hardware preflight, exact restore bundles, and read-back comparison.
- Validated a controlled XT write at 63/63 exact messages.
- Validated the exact restoration at 63/63 exact messages.
- Confirmed zero unexpected target changes.

## 0.1.0 — CODE V1

- Added strict framing and splitting for concatenated Microwave XT SysEx streams.
- Added validation for Waldorf manufacturer ID, Microwave II/XT equipment ID, Device ID, message lengths, and checksums.
- Added 14-bit MIDI address and nibble codecs.
- Added typed models for Sound, Multi, User Wave, User Wavetable, and Global data.
- Added User Wave stored-sample decoding and explicit 128-point reconstruction policies.
- Added User Wavetable reference decoding.
- Added 16-character Sound name reading and editing.
- Added Universal Device Identity decoding for the reference XT running OS 2.33.
- Added CLI commands: `inspect`, `validate`, `roundtrip`, and `identity`.
- Added synthetic tests and strict round-trip validation against four real hardware dumps.
- Renamed the public project, Python distribution, and CLI to `W-MWXT-WAVETABLE-TOOL`.
