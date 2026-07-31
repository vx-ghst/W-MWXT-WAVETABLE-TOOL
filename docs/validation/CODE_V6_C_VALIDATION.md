# CODE V6-C Validation — Cycle Discovery and Metrics

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V6-C
Branch  : code-v6-cycle-engine
Version : 0.5.0 (unchanged until CODE V6-F)
```

## Delivered contract

CODE V6-C converts the accepted V6-A working-pitch plan and V6-B usable source
segments into deterministic source-domain cycle candidates. The stage measures
candidate quality but does not choose representative states or reconstruct waves.

Public models and functions:

```text
CycleCandidateStatus
CycleCandidate
CycleDiscoveryAnalysis
discover_cycles
analyze_audio_source_cycles
```

Each candidate records:

```text
source segment identity
source-domain sample bounds
cycle length and period error
periodicity score
seam value and slope errors
seam score
energy consistency
spectral consistency
composite metric score
accepted/rejected status with canonical reasons
candidate SHA-256
```

## Source-domain period mapping

When V6-A requests a temporary repitch, V6-C does not rewrite or resample the
source. It maps the planned working period back to the original sample domain:

```text
source period = working period × repitch ratio
```

This keeps every cycle bound linked to the unchanged imported audio while retaining
the exact V6-A working-pitch intent.

## Deterministic discovery

For each V6-B usable segment, V6-C:

1. derives a bounded integer period search range around the source-domain period;
2. creates deterministic, evenly distributed cycle anchors;
3. searches a bounded start and period neighborhood;
4. selects the best local window by deterministic metric ordering;
5. records every metric and quality-gate result;
6. caps candidate count per segment without random sampling.

Default configuration:

```text
period search radius          : 0.125
boundary search radius        : 4 samples
maximum cycles per segment    : 64
minimum periodicity score     : 0.75
minimum seam score            : 0.45
minimum energy consistency    : 0.50
minimum spectral consistency  : 0.70
```

## Hash chain

```text
WorkingPitchPlan.analysis_sha256
SegmentationAnalysis.analysis_sha256
    └── CycleDiscoveryAnalysis.analysis_sha256
            └── CycleCandidate.candidate_sha256
```

The analysis preserves the source sample hash, segmentation hash, working-pitch
plan hash, usable segment indexes, usable segment hashes, analyzed/skipped segment
partition, candidate hashes, and accepted candidate indexes.

## CLI

```powershell
W-MWXT-WAVETABLE-TOOL discover-cycles `
  "D:\Audio\source.wav" `
  --pitch-policy auto `
  --attack-policy auto `
  --maximum-cycles-per-segment 64 `
  --report "D:\Reports\source.cycles.json"
```

## Safety boundary

CODE V6-C does not:

- rewrite, trim, normalize, resample, or export source audio;
- rank representative states or select top-N cycles;
- force a user cycle override;
- reconstruct spectral, partial, or hybrid waves;
- quantize Microwave XT wave data;
- generate SysEx;
- transmit MIDI;
- execute any irreversible operation.

## Targeted validation

```text
Core cycle discovery tests : 48
CLI tests                  : 5
Public API tests           : 5
Targeted total             : 58
```

## Acceptance gate

CODE V6-C passes when all 58 targeted tests and both complete suites pass, two
real-audio reports are byte-identical, source audio remains unchanged, every hash
link validates, candidates stay inside their linked usable segments, the analyzed
and skipped sets partition the usable segments, metric/status contracts hold, and
no generated report or private audio enters Git.
