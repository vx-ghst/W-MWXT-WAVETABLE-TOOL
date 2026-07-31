# Changelog

All notable changes to **W-MWXT-WAVETABLE-TOOL** are documented here.

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
