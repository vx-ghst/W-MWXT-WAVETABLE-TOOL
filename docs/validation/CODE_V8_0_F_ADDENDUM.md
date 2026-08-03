# CODE V8-0F Addendum - pre-V8 aggregate and zero required-debt gate

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0F
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0E / 4db4ac6bc1ba5c7262cddef082fed6eb6294b6ce
Version : 0.7.0 (unchanged until CODE V8-G)
```

## Purpose

CODE V8-0F closes the mandatory pre-builder gate. It does not add another DSP algorithm. It assembles the accepted V3-V7 provenance chain, the additive V8-0B through V8-0E decision/profile/optimization/repair chain, and an executable closure ledger for every active requirement whose corrected destination begins with `V8-0`.

## File-list addendum

The initial CODE V8 execution-plan file list described the DSP, decision, profile, repair, XT, and later wavetable modules but did not name the final pre-V8 aggregate module or its packaged closure ledger. The following files are therefore authorized by this addendum:

```text
CREATE src/w_mwxt_wavetable_tool/compliance/pre_v8.py
CREATE src/w_mwxt_wavetable_tool/compliance/data/pre_v8_closure_v1.json
CREATE tests/v8f_helpers.py
CREATE tests/test_pre_v8_compliance.py
CREATE tests/test_pre_v8_aggregate.py
CREATE tests/test_public_api_v8f.py
CREATE docs/validation/CODE_V8_0_F_ADDENDUM.md
CREATE docs/validation/CODE_V8_0_F_VALIDATION.md
MODIFY src/w_mwxt_wavetable_tool/compliance/__init__.py
MODIFY src/w_mwxt_wavetable_tool/__init__.py
```

The globally authorized development documentation files remain available to this stage.

## Historical registry boundary

The schema-1 V8-0A registry remains an immutable audit of the accepted `v0.7.0` baseline. Its historical `partial` and `planned` support states are not rewritten to make the current branch appear retroactively complete.

V8-0F adds a separate schema-1 closure ledger linked to the exact V8-0A registry SHA-256. The ledger contains every active requirement whose corrected destination begins with `V8-0`, in canonical registry order. It records:

```text
requirement ID
closing CODE stage
supported state
module evidence
test evidence
closure reason
per-record SHA-256
one final closure SHA-256
```

The ledger also incorporates the V8-0C taxonomy correction: `CDC-CLS-001` is closed against the normative 27-class list, not the obsolete non-normative phrase “28-label taxonomy”.

## Exact debt gate

The executable registry contains exactly 62 active obligations whose corrected destination begins with `V8-0`:

```text
CODE V6     : 2 accepted prerequisite obligations
CODE V8-0B  : 12 obligations
CODE V8-0C  : 19 obligations
CODE V8-0D  : 24 obligations
CODE V8-0E  : 4 obligations
CODE V8-0F  : 1 Windows core-CI obligation
TOTAL       : 62/62 supported
```

Excluded and post-prototype requirements are never counted as pre-V8 debt. Active requirements assigned to V8, V9, V10, V11, V12, V13, V14, or V15 remain deferred to their recorded destination and are not falsely claimed by this stage.

## V3-V7 provenance chain

`PreV8SourceChain` validates:

```text
V3 imported audio state and canonical sample identity
V4 SignalAnalysis link embedded by CodeV5Analysis
V5 CodeV5Analysis link embedded by CodeV6Analysis
V6 reconstructed-wave-set link
V7 XtProjectionSet link to the exact V6 aggregate and reconstructed set
optional V7 trajectory link
optional V7 QC link
optional V7 hardware-package link
```

Supplying QC without a trajectory, or a hardware package without trajectory and QC, is rejected. Every supplied optional artifact must link to the exact preceding artifact.

## V8-0 decision and treatment chain

`PreV8DecisionPlan` validates the complete additive chain:

```text
SignalExtensionAnalysis
BehaviorClassification
RegionInterestAnalysis
FormantAnalysis
SpectralEvolutionAnalysis
PerceptualFeatureVector
MusicalClassification
ModeDecision
ProfileSelection
XtWaveSetOptimization
AutoRepairSequenceResult
```

All sample identities and component hashes must agree. The selected optimization profile must equal the profile-selection definition. Optimized and repaired wave counts must match. A rejected conversion-mode decision remains an explicit rejected preflight; no hidden fallback is introduced.

## Final aggregate

`CodeV8PreflightAnalysis` combines:

```text
PreV8SourceChain
PreV8DecisionPlan
PreV8ComplianceClosure
ready or rejected source status
explicit blockers
canonical JSON
one aggregate SHA-256
```

A source can be rejected while the implementation debt gate remains closed. This distinction prevents capability completion from being confused with source suitability.

## Safety boundary

CODE V8-0F builds no wavetable, allocates no XT memory, generates no SysEx, opens no MIDI port, and transmits no MIDI. It commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
