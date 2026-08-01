# CODE V6-D Validation — Representative Cycle Ranking and Top-N Selection

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V6-D
Branch  : code-v6-cycle-engine
Version : 0.5.0 (unchanged until CODE V6-F)
```

## Delivered contract

CODE V6-D converts the deterministic V6-C cycle-discovery result into an auditable
ranking and a representative top-N cycle set. It does not reconstruct waveforms or
write any hardware data.

Public models and functions:

```text
CycleSelectionPolicy
CycleSelectionDecision
RankedCycleCandidate
SelectedCycleSet
select_representative_cycles
analyze_audio_source_cycle_selection
```

The canonical output object is `SelectedCycleSet`. It links directly to the accepted
`CycleDiscoveryAnalysis`, preserves source identity, records the complete eligible
ranking, and exposes the exact selected candidate and ranking hashes.

## Automatic representative ranking

Automatic selection considers only V6-C candidates whose status is `accepted`.
Ranking is deterministic and combines:

```text
quality score             : 0.70
source-time novelty       : 0.20
segment novelty           : 0.10
```

The default weights sum to one and are serialized into the output. Deterministic
tie-breaking uses candidate quality, seam quality, spectral consistency, period
error, and finally the lowest V6-C candidate index.

The selector applies a minimum temporal separation expressed in source-domain cycle
periods. The default is one source cycle. A candidate may be ranked but not selected
when it is inside the configured separation radius or when the top-N limit is full.

## Top-N and Microwave XT boundary

```text
default top-N : 16
minimum       : 1
maximum       : 61
```

The upper bound matches the 61 editable Microwave XT User Wave positions. CODE V6-D
does not allocate those positions; it only prevents an intermediate representative
set from exceeding the final editable-wave capacity.

## Forced-cycle override

```text
selection policy : auto | force
```

`force` requires one explicit V6-C candidate index. The forced candidate is ranked
and selected first. A rejected V6-C candidate remains blocked unless the caller also
sets the explicit `allow_rejected_forced_candidate` override. The output records both
the forced index and whether rejected-candidate override permission was enabled.

This makes user authority explicit without silently weakening automatic quality
gates.

## Decisions

```text
selected
pitch_unavailable
no_candidates
no_accepted_candidates
```

Every decision includes a non-empty explanation. Non-selected decisions cannot
expose selected cycle identities.

## Hash chain

```text
CycleDiscoveryAnalysis.analysis_sha256
    └── SelectedCycleSet.analysis_sha256
            ├── RankedCycleCandidate.ranking_sha256
            ├── selected_candidate_sha256
            └── selected_ranking_sha256
```

Every ranked entry preserves the V6-C candidate index and candidate SHA-256. The
selected indexes, candidate hashes, and ranking hashes are derived from entries marked
`selected` and are validated as an exact ordered contract.

## CLI

Automatic selection:

```powershell
W-MWXT-WAVETABLE-TOOL select-cycles `
  "D:\Audio\source.wav" `
  --selection-policy auto `
  --top-n 16 `
  --report "D:\Reports\source.selection.json"
```

Explicit override:

```powershell
W-MWXT-WAVETABLE-TOOL select-cycles `
  "D:\Audio\source.wav" `
  --selection-policy force `
  --forced-candidate-index 7 `
  --top-n 16 `
  --report "D:\Reports\source.selection-forced.json"
```

A rejected candidate additionally requires:

```text
--allow-rejected-forced-candidate
```

## Safety boundary

CODE V6-D does not:

- modify, resample, trim, normalize, or export source audio;
- synthesize or reconstruct a waveform;
- select a spectral, partial, or hybrid reconstruction strategy;
- quantize Microwave XT User Wave data;
- allocate User Wave or User Wavetable destinations;
- generate SysEx;
- transmit MIDI;
- execute any irreversible operation.

## Targeted validation

```text
Core ranking and selection tests : 48
CLI tests                        : 5
Public API tests                 : 5
Targeted total                   : 58
```

## Acceptance gate

CODE V6-D passes when:

1. all 58 targeted tests pass;
2. the public and private complete suites pass;
3. two real-audio `select-cycles` reports are byte-identical;
4. source audio remains unchanged;
5. the V6-C analysis hash links exactly to `SelectedCycleSet`;
6. every ranked candidate links to one V6-C candidate hash;
7. selected indexes, candidate hashes, and ranking hashes are ordered and exact;
8. automatic mode never admits rejected candidates;
9. force mode records the authoritative candidate and any rejected-candidate override;
10. top-N and temporal-separation contracts hold;
11. no private audio or generated report enters Git.
