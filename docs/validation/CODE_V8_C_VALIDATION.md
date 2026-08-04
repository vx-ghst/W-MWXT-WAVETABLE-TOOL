# CODE V8-C Validation - structural and essential keyframe selection

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-C
Branch  : code-v8-wavetable-builder
Base    : CODE V8-B / a973d41d2e46448bc0ec284fac3969bccb99cbec
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : VALIDATED - LOCAL, PRIVATE, WHEEL, AND REMOTE CI GATES PASSED
```

## Implemented contracts

```text
schema-versioned keyframe-selection policy
one deterministic representative per V8-B complete-link group
required lock and chronology participant preservation
optional source-endpoint representative preservation
explicit 1, 2, 8, 61 and above-61 capacity behavior
complete or explicit rejected selection status
bounded utility, diversity, temporal, structural and group objective
public subset scorer for small-case optimality verification
exact combinatorial search under explicit limits
deterministic greedy search above exact limits
one immutable decision per input candidate
selected, essential, forced and omitted candidate sets
redundancy versus capacity omission evidence
canonical JSON and deterministic SHA-256 links
```

## Compatibility contract

The following accepted contracts remain unchanged:

```text
all V8-A candidate, request, fixed-tail, policy and constraint schemas
all V8-B metrics, usefulness, interval and complete-link schemas
all V8-0 and V1-V7 public schemas
version 0.7.0
```

V8-C consumes V8-A and V8-B evidence without mutation and does not reinterpret their hashes or classifications.

## Final validation evidence

```text
compileall                                      : PASS
pip check                                       : PASS
V8-C targeted suite                             : 82 passed
V8-A targeted regression suite                  : 115 passed
V8-B targeted regression suite                  : 112 passed
Complete public suite                           : 1831 passed, 4 skipped
Complete private suite                          : 1835 passed
Pre-V8 compliance gate                          : 62/62 supported, debt=0
One, two, eight and 61 distinct candidates      : PASS
Above-61 reduction to exactly 61                : PASS
Exact and polarity duplicate representative use: PASS
Mixed real/reconstructed provenance             : PASS
Required locks and chronology participants      : PASS
Infeasible forced-capacity rejection            : PASS with no partial selection
Requested count and endpoint policy             : PASS
Small-case exhaustive optimality                : PASS through public scorer
Greedy large-case determinism                   : PASS
One decision per input candidate                : PASS
Finite bounded objective components             : PASS
Canonical tuples, frozen models and hashes      : PASS
No position, ordering, variant, WCTD or MIDI path: PASS
Isolated PEP 517 wheel build                    : PASS
Wheel wavetable modules                         : 7/7 present
Wheel size                                      : 424360 bytes
Wheel SHA-256                                   : d0209b3b69b9d59e75bfcc86579b4fee8818fe9c927073bdcb2e5db32b0157d0
git diff --check                                : PASS
Authorized implementation paths                 : 14/14 exact
Implementation insertions                       : 2208 exact
Implementation deletions                        : 1 exact
```

The four public skips are exclusively the existing private real-dump tests. The complete private suite was executed with all four reference dumps mounted and finished with zero failed and zero skipped tests.

The wheel was built with the standard isolated PEP 517 process declared by `pyproject.toml`. The seven `wavetable` modules required through V8-C were present in the generated wheel: `__init__`, `models`, `contracts`, `metrics`, `usefulness`, `deduplication`, and `selection`.

The line-ending notices emitted by Git on Windows were advisory only. The implementation diff passed `git diff --check`, the exact-path gate, the added-line private-path gate, the media gate, and the final empty-index gate.

## Remote validation evidence

```text
Implementation commit       : 82dff4b247817cf79325ae8394032ae0f3d64c33
Implementation parent       : a973d41d2e46448bc0ec284fac3969bccb99cbec
Draft pull request          : 7
Pull-request base           : main
Pull-request head           : code-v8-wavetable-builder
Push workflow run           : 30842955192
Pull-request workflow run   : 30842958781
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
[x] the exact immutable V8-A request and V8-B analysis hashes are preserved
[x] every input candidate receives exactly one explicit selection decision
[x] one deterministic representative per V8-B complete-link group is used
[x] unprotected removable duplicates are omitted before capacity selection
[x] required position-lock candidates are never silently omitted
[x] both endpoints of required chronology constraints are never silently omitted
[x] optional source-endpoint preservation uses deterministic group representatives
[x] complete selections contain one through 61 candidate IDs
[x] inventories above 61 are reduced deterministically to exactly 61 when feasible
[x] infeasible mandatory capacity returns rejected status, blockers, and no partial selection
[x] selected IDs remain in canonical source order and do not claim final table ordering
[x] utility, diversity, temporal, structural, and group objective components are bounded and visible
[x] exact small-case optimization is independently verifiable through the public subset scorer
[x] large cases use deterministic greedy selection and canonical tie-breaks
[x] selected, essential, forced, redundant, protected, and capacity-omitted evidence is explicit
[x] mixed real and reconstructed candidate provenance is preserved
[x] canonical JSON and SHA-256 links are deterministic
[x] accepted V8-A, V8-B, V8-0, and V1-V7 schemas remain unchanged
[x] targeted V8-C suite passes
[x] V8-A and V8-B targeted regression suites pass
[x] complete public suite passes
[x] complete private suite passes with all four reference dumps
[x] pre-V8 gate remains 62/62 supported with zero debt
[x] isolated PEP 517 wheel builds successfully
[x] all seven V8-C-era wavetable modules are present in the wheel
[x] exact 14-file implementation diff and whitespace checks pass
[x] twelve implementation checks pass
[x] implementation commit SHA and workflow runs are recorded
[x] repository is clean after the implementation commit
[x] V8-C does not assign positions, solve final ordering, or generate variants
[x] V8-C does not interpolate transitions or materialize WCTD
[x] no XT allocation, SysEx generation, MIDI opening, or MIDI transmission is introduced
[x] no private dump, generated SysEx, audio capture, local path, or private evidence is committed
```

CODE V8-C is formally closed.

The next stage is CODE V8-D, which orders and places the selected V8-C keyframes into the editable positions, resolves required locks and chronology constraints, and generates deterministic placement variants. This closure does not claim interpolation, WCTD materialization, hardware acceptance, SysEx generation, or MIDI transmission.

## Safety boundary

CODE V8-C performs immutable selection only. It builds no 61-slot table, materializes no WCTD payload, allocates no XT memory, generates no SysEx, opens no MIDI port, transmits no MIDI and modifies no instrument state. It commits no private dump, generated SysEx, audio capture, local absolute path or private evidence file.
