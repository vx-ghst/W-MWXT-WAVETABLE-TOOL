# CODE V3-B Validation

## Scope

CODE V3-B completes the minimal persistence gate of CODE V3.

Implemented:

- versioned minimal project schema;
- `.mwxtproj` deterministic ZIP container;
- canonical UTF-8 JSON manifest;
- embedded immutable mono `float64` samples in canonical little-endian form;
- atomic project saves;
- explicit overwrite protection;
- strict archive shape and schema validation;
- source, sample, imported-state, content, and archive SHA-256 fingerprints;
- external source status detection;
- strict, embedded-fallback, and ignore source policies;
- exact imported-state reconstruction without re-decoding the source;
- CLI project create/open operations;
- Unicode and long-path support;
- corruption, truncation, duplicate-entry, and unexpected-entry rejection.

## Project container

A minimal project contains exactly two stored ZIP entries in fixed order:

```text
manifest.json
audio/mono-f64le.bin
```

The archive contains no pickle, executable object, source audio copy, SysEx data, or MIDI instruction.

The manifest records:

- project schema and container identifiers;
- tool version;
- project name;
- original source metadata and SHA-256;
- mono-conversion policy, strategy, measurements, and explanation;
- embedded sample count, dtype, entry, and SHA-256;
- imported-state SHA-256;
- complete content SHA-256.

## Source policies

`require_unchanged` is the default:

- the original source must exist;
- it must be a regular file;
- its current SHA-256 must match the stored fingerprint.

`allow_embedded` still checks and reports the source status, but reopens the exact embedded imported state when the source is changed, missing, or unavailable.

`ignore` performs no external-source access and reopens from embedded data only.

## Determinism

Saving the same `AudioSource`, project name, and tool version produces byte-identical `.mwxtproj` files. ZIP timestamps, entry order, permissions, encoding, JSON ordering, and sample byte order are fixed.

## Automated validation

Generated CODE V3-B tests:

```text
38 passed
0 failed
```

Test coverage includes:

- schema and name validation;
- canonical JSON;
- audio-record and manifest round trips;
- content-hash verification;
- exact save/open state reproduction;
- byte-identical repeated saves;
- fixed archive entries and metadata;
- overwrite opt-in;
- Unicode and long paths;
- unchanged, changed, missing, and ignored sources;
- embedded fallback;
- invalid extension and missing project;
- malformed ZIP and JSON;
- extra and duplicate entries;
- truncated and corrupted samples;
- altered manifest content;
- source preservation;
- CLI create/open/report behavior;
- public API availability.

## Expected repository totals

Based on the accepted CODE V3-A branch:

```text
Targeted CODE V3-B : 38 passed
Public full suite   : 203 passed, 4 skipped
Private full suite  : 207 passed
```

The release version remains `0.2.0` during the CODE V3-B validation gate. After automated and manual acceptance, CODE V3 is finalized as version `0.3.0`, merged to `main`, and tagged `v0.3.0`.

CODE V3-B does not modify SysEx generation and performs no MIDI transmission.
