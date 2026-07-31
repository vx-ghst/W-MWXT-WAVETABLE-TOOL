# CODE V4 Validation

## Scope

CODE V4-E closes the complete deterministic time-domain analysis stage on top
of accepted gates V4-A through V4-D.

Implemented in the final gate:

- immutable aggregate `SignalAnalysis` contract;
- one canonical sample identity shared by every component;
- strict cross-component sample-rate, sample-count, and sample-hash validation;
- strict reuse of the pitch frame grid by phase and noise analysis;
- component SHA-256 map and one aggregate analysis SHA-256;
- consolidated `signal-analyze` CLI serialization while preserving accepted
  component keys;
- public API propagation;
- README and changelog consolidation;
- release propagation to `0.4.0`.

The complete CODE V4 release includes levels, envelope, pitch, periodicity,
phase continuity, cycle discontinuity, pitch motion, noise floor, SNR,
transients, and change points.

## Determinism

The aggregate hash is computed from canonical JSON containing the release
version, canonical sample identity, component hashes, and complete component
reports. Identical samples and configuration therefore produce identical
component and aggregate fingerprints.

## Compatibility

The CLI keeps the accepted top-level keys:

- `time_domain_analysis`;
- `pitch_periodicity_analysis`;
- `phase_motion_analysis`;
- `noise_analysis`;
- `transient_change_analysis`.

It adds aggregate schema metadata, the component hash map, and the final
`analysis_sha256` at the report root.

## Safety

CODE V4 imports and analyzes audio only. It does not generate SysEx and does not
transmit MIDI.

## Accepted intermediate gates

```text
V4-A targeted : 37 passed
V4-B targeted : 46 passed
V4-C targeted : 32 passed
V4-D targeted : 44 passed
```

The release is accepted only after targeted, complete public, complete private,
manual real-audio determinism, release metadata, pull-request, merge, and tag
gates pass.

## Final-gate expected totals

```text
Targeted CODE V4-E : 35 passed
Public full suite   : 397 passed, 4 skipped
Private full suite  : 401 passed
```

The isolated package-construction snapshot passed `353` public tests. The
accepted user repository contains the complete prior-stage test history, so its
expected final totals are the values above.
