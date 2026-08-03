# CODE V8-D Validation - ordering, placement, locks, chronology and variants

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-D
Branch  : code-v8-wavetable-builder
Base    : CODE V8-C / 4dd3eeb32a638eb45be96a41606aeb3bcd5f75b5
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : VALIDATED - LOCAL, PRIVATE, WHEEL, AND REMOTE CI GATES PASSED
```

## Implemented contracts

```text
schema-versioned ordering, placement and variant policies
exact selected-set identity preservation from V8-C
five-term public ordering objective
six deterministic ordering strategies
exhaustive small-case and topological greedy large-case solving
required and preference chronology outcomes
required lock ordering and capacity feasibility
sparse unique position assignment across editable positions 1-61
hard required anchors and feasible preference anchors
five deterministic placement biases
explicit occupied and open positions for V8-E
ranked and signature-deduplicated placement variants
moved-candidate and position-delta evidence
complete or rejected results with no partial fallback
canonical JSON and deterministic SHA-256 links
```

## Compatibility contract

The following accepted contracts remain unchanged:

```text
all V8-A request, candidate, policy, lock and chronology schemas
all V8-B metrics, usefulness and complete-link schemas
all V8-C selection policies, decisions and aggregate schemas
all V8-0 and V1-V7 public schemas
version 0.7.0
```

V8-D consumes V8-A through V8-C evidence without mutation and preserves every selected candidate ID exactly once.

## Final validation evidence

```text
compileall                                      : PASS
pip check                                       : PASS
V8-D targeted suite                             : 97 passed
V8-A targeted regression suite                  : 115 passed
V8-B targeted regression suite                  : 112 passed
V8-C targeted regression suite                  : 82 passed
Complete public suite                           : 1928 passed, 4 skipped
Complete private suite                          : 1932 passed
Pre-V8 compliance gate                          : 62/62 supported, debt=0
One, two, eight and 61-position behavior        : PASS
Mixed real/reconstructed provenance             : PASS
Six ordering strategies                         : PASS
Five placement biases                           : PASS
Five-term weighted ordering objective           : PASS
Small-case exhaustive ordering optimality       : PASS through public scorer
Large-case deterministic topological ordering   : PASS
Required locks and chronology                   : PASS
Preference lock and chronology evidence         : PASS
Infeasible anchor-capacity rejection            : PASS with no partial output
Sparse occupied/open position partition         : PASS
Ranked unique placement variants                : PASS
Canonical tuples, frozen models and hashes      : PASS
No interpolation, WCTD, SysEx or MIDI path      : PASS
Isolated PEP 517 wheel build                    : PASS
Wheel wavetable modules                         : 10/10 present
Wheel size                                      : 445706 bytes
Wheel SHA-256                                   : cb85f580d4c7ff9a7755bf51f4c52b1c540ca2e3c975484a8ab5410c4b2b8c6f
git diff --check                                : PASS
Authorized implementation paths                 : 17/17 exact
Implementation insertions                       : 3896 exact
Implementation deletions                        : 1 exact
```

The four public skips are exclusively the existing private real-dump tests. The complete private suite was executed with all four reference dumps mounted and finished with zero failed and zero skipped tests.

The wheel was built with the standard isolated PEP 517 process declared by `pyproject.toml`. The ten `wavetable` modules required through V8-D were present in the generated wheel: `__init__`, `models`, `contracts`, `metrics`, `usefulness`, `deduplication`, `selection`, `ordering`, `placement`, and `variants`.

The line-ending notices emitted by Git on Windows were advisory only. The implementation diff passed `git diff --check`, the exact-path gate, the added-line private-path gate, the media gate, and the final empty-index gate.

## Remote validation evidence

```text
Implementation commit       : f6a986b400269641145693717487739a93add6fd
Implementation parent       : 4dd3eeb32a638eb45be96a41606aeb3bcd5f75b5
Draft pull request          : 7
Pull-request base           : main
Pull-request head           : code-v8-wavetable-builder
Push workflow run           : 30847955609
Pull-request workflow run   : 30847959550
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
[x] the immutable V8-A request, V8-B analysis, and V8-C selection hashes are preserved
[x] every complete ordering is an exact permutation of the selected V8-C candidates
[x] every complete placement assigns every ordered candidate exactly once
[x] occupied positions are unique integers from 0 through 60
[x] assigned positions increase strictly with the final order
[x] required chronology constraints are never silently violated
[x] required position locks are never silently violated
[x] preference constraints expose satisfied, violated, or not-applicable evidence
[x] lock, chronology, capacity, and selected-set conflicts produce explicit blockers
[x] rejected results expose no partial order, placement, or variant
[x] exact small-case ordering is independently verifiable through the public scorer
[x] large cases use deterministic topological greedy solving and canonical tie-breaks
[x] source fidelity, scan smoothness, harmonic diversity, Bass strength, and discontinuity avoidance are explicit
[x] balanced, source-fidelity, scan-smoothness, harmonic-diversity, Bass-strength, and discontinuity-avoidance strategies are deterministic
[x] balanced, early, late, center, and edge-expanded placement biases are deterministic
[x] sparse placements expose every open position for V8-E
[x] placement variants have unique candidate-position signatures and deterministic ranks
[x] moved-candidate counts and mean position deltas are explicit
[x] the primary variant is stable independently of the requested retained-variant count
[x] mixed real and reconstructed candidate provenance is preserved
[x] canonical JSON and SHA-256 links are deterministic
[x] accepted V8-A, V8-B, V8-C, V8-0, and V1-V7 schemas remain unchanged
[x] targeted V8-D suite passes
[x] V8-A, V8-B, and V8-C targeted regression suites pass
[x] complete public suite passes
[x] complete private suite passes with all four reference dumps
[x] pre-V8 gate remains 62/62 supported with zero debt
[x] isolated PEP 517 wheel builds successfully
[x] all ten V8-D-era wavetable modules are present in the wheel
[x] exact 17-file implementation diff and whitespace checks pass
[x] twelve implementation checks pass
[x] implementation commit SHA and workflow runs are recorded
[x] repository is clean after the implementation commit
[x] V8-D generates no transition waveform samples
[x] V8-D does not interpolate transitions or materialize WCTD
[x] no XT allocation, SysEx generation, MIDI opening, or MIDI transmission is introduced
[x] no private dump, generated SysEx, audio capture, local path, or private evidence is committed
```

CODE V8-D is formally closed.

The next stage is CODE V8-E, which consumes the validated V8-D ordering and sparse placement variants, generates deterministic transition waves, allocates adaptive transition density, and produces continuity evidence. This closure does not claim Factory Style, WCTD materialization, hardware acceptance, SysEx generation, or MIDI transmission.

## Safety boundary

CODE V8-D performs immutable planning only. It generates no waveform samples, materializes no WCTD payload, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI, and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
