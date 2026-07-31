# CODE V3 Validation

## Release

- Distribution: `W-MWXT-WAVETABLE-TOOL`
- Python package: `w_mwxt_wavetable_tool`
- Version: `0.3.0`
- Development branch: `code-v3-audio-import`
- Accepted CODE V3-B baseline: `c870baf1fca59ce64a5970da1872fffff8aa39a1`

## Scope

CODE V3 completes the audio-import and minimal-project stage defined by the roadmap.

### CODE V3-A

- WAV, AIFF, and FLAC import;
- content-based container detection;
- source preservation and SHA-256 fingerprinting;
- immutable contiguous `float64` representation;
- deterministic mono conversion;
- anti-phase and silent-channel handling;
- invalid-value policies;
- audio measurements;
- deterministic sample and imported-state hashes;
- `audio-inspect` CLI reporting.

### CODE V3-B

- versioned `.mwxtproj` schema;
- deterministic ZIP archive;
- canonical JSON and little-endian sample storage;
- atomic save and overwrite protection;
- strict shape, schema, length, and hash validation;
- source status checks;
- strict, embedded-fallback, and ignore policies;
- exact imported-state reconstruction;
- `project-create` and `project-open` CLI operations.

### CODE V3-C

- release version raised to `0.3.0` in package metadata and public API;
- runtime version centralized for package and project-persistence fallback;
- release-version propagation tests;
- README updated to the current capabilities and commands;
- changelog completed for CODE V2 and CODE V3;
- consolidated validation evidence recorded.

## Automated evidence

Accepted pre-release results:

```text
CODE V3-A targeted : 49 passed
CODE V3-B targeted : 38 passed
Public full suite  : 203 passed, 4 skipped
Private full suite : 207 passed
```

CODE V3-C adds four release tests. Expected final results:

```text
CODE V3-C targeted : 4 passed
Public full suite  : 207 passed, 4 skipped
Private full suite : 211 passed
```

The public/private difference remains the four hardware-reference tests enabled by `W_MWXT_DUMP_DIR`.

## Manual evidence

### Deterministic audio import

The same source was imported twice with identical:

- source SHA-256;
- mono-sample SHA-256;
- imported-state SHA-256.

The source file SHA-256 remained unchanged after inspection.

### Deterministic project persistence

Two projects created independently from the same source, name, policy, and tool version were byte-identical.

### Source validation

- unchanged source: strict open passed;
- missing source: strict open failed as designed;
- missing source with `allow_embedded`: open passed;
- embedded sample and imported-state SHA-256 remained identical;
- restored source SHA-256 matched the original fingerprint.

## Security and privacy

The release contains no:

- private `.syx` dump;
- source audio file;
- generated `.mwxtproj` file;
- hardware capture;
- MIDI transmission code;
- pickle or executable project payload.

## Acceptance

CODE V3 is accepted when:

1. the four CODE V3-C release tests pass;
2. the public suite reports `207 passed, 4 skipped`;
3. the private suite reports `211 passed`;
4. both version surfaces report `0.3.0`;
5. the worktree contains only the nine intended CODE V3-C files;
6. the branch is committed and pushed;
7. a Pull Request is merged into `main`;
8. merged `main` passes the final public suite;
9. annotated tag `v0.3.0` points to the merged `main` commit.

No additional hardware write is required for CODE V3 because this stage does not change SysEx generation, destination logic, or MIDI transport.
