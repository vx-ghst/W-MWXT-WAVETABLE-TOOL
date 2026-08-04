# CODE V8-B Validation - usefulness, structure, breakpoints and deduplication

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-B
Branch  : code-v8-wavetable-builder
Base    : CODE V8-A / ef7827060b474d3241d20df752b57bf0e14fb436
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : VALIDATED - LOCAL, PRIVATE, WHEEL, AND REMOTE CI GATES PASSED
```

## Implemented contracts

```text
schema-versioned wave-shape metrics
fixed 128-point reconstruction and 32-bin deterministic DFT
exact, polarity-equivalent, near and distinct pair analysis
source-ordered stable, transition and breakpoint intervals
moderate/strong transition threshold evidence
waveform, spectral, level, brightness, Bass and polarity breakpoint kinds
per-candidate structural/usefulness classification
feature-extreme preservation evidence
deterministic complete-link duplicate grouping
required-lock and required-chronology protection
explicit representative, redundant, protected and removable candidate states
distinct-wave count and >61 warning
linked CodeV8BAnalysis aggregate
canonical JSON and deterministic SHA-256
```

## Compatibility contract

The following accepted contracts remain unchanged:

```text
all V8-A candidate, fixed-tail, request, constraint, slot, build and build-set schemas
all V8-0 and V1-V7 public schemas
version 0.7.0
```

V8-B consumes `WavetableBuildRequest` and never mutates the request or candidate objects.

## Final validation evidence

```text
compileall                                        : PASS
pip check                                         : PASS
V8-B targeted suite                               : 112 passed
V8-A plus V8-B isolated bundle                    : 227 passed
Complete public suite                             : 1749 passed, 4 skipped
Complete private suite                            : 1753 passed
Pre-V8 compliance gate                            : 62/62 supported, debt=0
Invalid sample length/type/range gates             : PASS
Zero, sine, square and deterministic corpus        : PASS
Metric bounds, frozen models and finite values     : PASS
Pair symmetry and exact/polarity identities        : PASS
Stable, moderate/strong transition and breakpoint  : PASS
Source-order and interval-hash links                : PASS
Ineligible and feature-extreme classification      : PASS
Exact, polarity and near duplicate groups           : PASS
Complete-link anti-chain gate                       : PASS
Required lock/chronology protection                 : PASS
Representative ranking and >61 warning              : PASS
Request/structure/dedup aggregate hash links        : PASS
No selection, placement, interpolation or WCTD      : PASS
Isolated PEP 517 wheel build                        : PASS
Wheel wavetable modules                             : 6/6 present
Wheel size                                          : 414243 bytes
Wheel SHA-256                                       : c1fe752821501ff50a469e732eac8b6b4fe847657059e76e151b034e7dad2349
git diff --check                                    : PASS
Authorized implementation paths                     : 16/16 exact
Implementation insertions                           : 3145 exact
Implementation deletions                            : 3 exact
```

The four public skips are exclusively the existing private real-dump tests. The complete private suite was executed with all four reference dumps mounted and finished with zero failed and zero skipped tests.

The wheel was built with the standard isolated PEP 517 process declared by `pyproject.toml`. The six `wavetable` modules required through V8-B were present in the generated wheel: `__init__`, `models`, `contracts`, `metrics`, `usefulness`, and `deduplication`.

The line-ending notices emitted by Git on Windows were advisory only. The implementation diff passed `git diff --check`, the exact-path gate, the added-line private-path gate, the media gate, and the final empty-index gate.

## Remote validation evidence

```text
Implementation commit       : 9f68ae2e36c77ece85c31e1fbe260c35814334b7
Implementation parent       : ef7827060b474d3241d20df752b57bf0e14fb436
Draft pull request          : 7
Pull-request base           : main
Pull-request head           : code-v8-wavetable-builder
Push workflow run           : 30839447623
Pull-request workflow run   : 30839586598
Unique CI environments      : 6
Push checks                 : 6/6 passed
Pull-request checks         : 6/6 passed
Total implementation checks : 12/12 passed
Cancelled                   : 0
Failed                      : 0
Skipped                     : 0
Pending                     : 0
```

The six operating-system and Python combinations ran through both push and pull-request events. Every job completed project installation, compileall, pip check, and the complete public suite.

## Closure gates

```text
[x] V8-A immutable candidate, request, constraint, and provenance contracts remain unchanged
[x] every V8-A candidate is analyzed exactly once without mutation
[x] deterministic 64-point and reconstructed 128-point shape metrics are present
[x] the fixed 32-bin DFT and all serialized numeric values are deterministic
[x] exact, polarity-equivalent, near, and distinct pair classes are explicit
[x] stable, moderate transition, strong transition, and breakpoint intervals are explicit
[x] waveform, spectral, level, brightness, Bass, polarity, and composite breakpoint evidence is explicit
[x] structural, feature-extreme, stable, transition, breakpoint, and ineligible candidate classes are explicit
[x] source-order and adjacent-interval hash links are validated
[x] complete-link duplicate grouping prevents transitive near-duplicate chains
[x] required position locks protect referenced candidates
[x] required chronology constraints protect referenced candidates
[x] representative, redundant, protected, and removable states are explicit
[x] distinct-wave count equals the deterministic duplicate-group count
[x] more than 61 distinct groups produces an explicit V8-C warning
[x] the engineering perceptual-distance proxy is not claimed as calibrated auditory truth
[x] V8-B does not remove candidates or choose final keyframes
[x] V8-B does not assign positions, order the final table, or generate variants
[x] V8-B does not interpolate transitions or materialize WCTD
[x] canonical JSON and SHA-256 links are deterministic
[x] accepted V8-A, V8-0, and V1-V7 schemas remain unchanged
[x] targeted V8-B suite passes
[x] complete public suite passes
[x] complete private suite passes with all four reference dumps
[x] pre-V8 gate remains 62/62 supported with zero debt
[x] isolated PEP 517 wheel builds successfully
[x] all six V8-B-era wavetable modules are present in the wheel
[x] exact 16-file implementation diff and whitespace checks pass
[x] twelve implementation checks pass
[x] implementation commit SHA and workflow runs are recorded
[x] repository is clean after the implementation commit
[x] no XT allocation, SysEx generation, MIDI opening, or MIDI transmission is introduced
[x] no private dump, generated SysEx, audio capture, local path, or private evidence is committed
```

CODE V8-B is formally closed.

The next stage is CODE V8-C, which selects the final structural and essential keyframes for the 61 editable positions from the immutable V8-A request and the complete V8-B structure/deduplication evidence. This closure does not claim final ordering, placement, interpolation, WCTD materialization, hardware acceptance, SysEx generation, or MIDI transmission.

## Safety boundary

CODE V8-B performs immutable analysis only. It builds no wavetable, materializes no WCTD payload, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path or private evidence file.
