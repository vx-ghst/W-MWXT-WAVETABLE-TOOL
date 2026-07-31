# CODE V3-A Validation

## Scope

CODE V3-A establishes the deterministic audio-import core of CODE V3.

Implemented:

- WAV, AIFF, and FLAC import through libsndfile;
- content-based container detection;
- source SHA-256 fingerprinting;
- source size and modification-time capture;
- source-change detection during import;
- immutable contiguous `float64` mono representation;
- explicit invalid-sample policies;
- deterministic mono conversion;
- silent-channel handling;
- anti-phase protection;
- mono measurements;
- source and imported-state fingerprints;
- JSON CLI inspection through `audio-inspect`;
- Unicode and long-path support.

Deferred to CODE V3-B:

- minimal project schema;
- save/open persistence;
- source-change verification when reopening a project.

## Mono policy

The default `auto` policy is deterministic:

1. mono input is passed through;
2. identical channels are averaged without changing the signal;
3. one active channel is selected when all other channels are silent;
4. strongly anti-phase stereo with comparable levels selects the higher-RMS channel instead of destructively averaging;
5. other multichannel material uses an arithmetic average.

Explicit `average`, `first_channel`, and `dominant_channel` policies remain available.

## Source preservation

The importer never writes to the source file. It records:

- resolved source path;
- byte length;
- modification time in nanoseconds;
- source SHA-256;
- decoded format metadata.

A size or modification-time change during import raises `SourceChangedError`.

## Dependencies

- NumPy `>=1.26,<3`;
- SoundFile `>=0.13,<1`.

SoundFile uses libsndfile and distributes Windows wheels that include the required native library on common Windows platforms.

## Automated validation

Generated CODE V3-A tests:

```text
49 passed
0 failed
```

Test coverage includes:

- PCM and floating-point WAV;
- AIFF;
- FLAC;
- unsupported decodable format rejection;
- missing files and directories;
- Unicode and long paths;
- mono input;
- identical stereo;
- anti-phase stereo;
- silent channel;
- explicit mono policies;
- silence;
- DC offset;
- NaN and infinity reject/zero policies;
- source preservation;
- source-change detection;
- deterministic sample and state hashes;
- immutable sample storage;
- CLI JSON output.

## Expected repository totals

Based on the accepted CODE V2 baseline:

```text
Targeted CODE V3-A : 49 passed
Public full suite   : 165 passed, 4 skipped
Private full suite  : 169 passed
```

CODE V3-A does not modify SysEx generation or perform MIDI transmission.
