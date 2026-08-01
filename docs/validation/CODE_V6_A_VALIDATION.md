# CODE V6-A Validation — Working Pitch and Repitch Policy

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V6-A
Branch  : code-v6-cycle-engine
Version : 0.5.0 (unchanged until CODE V6-F)
```

## Delivered contract

CODE V6-A adds deterministic working-pitch planning without modifying source audio.

Delivered public models and functions:

```text
WorkingPitchCandidateKind
WorkingPitchCandidate
WorkingPitchCandidates
WorkingPitchPolicy
WorkingPitchDecision
WorkingPitchPlan
generate_working_pitch_candidates
plan_working_pitch
analyze_audio_source_working_pitch
```

The canonical automatic candidate set is built from octave-related versions of the
detected source pitch. This preserves pitch class and harmonic ratios while testing
whether a shorter or longer period is more suitable for later cycle extraction.

Default working-period configuration:

```text
preferred period : 128 samples
accepted range   : 64–256 samples
maximum shift    : ±4 octaves
```

These values are explicit configuration, are serialized into the report, and may be
overridden by the caller.

## Policies

```text
auto         evaluate octave-preserving candidates and apply confidence gates
lock         make one explicit target frequency authoritative
no_repitch   preserve the detected source pitch
```

Automatic repitching is withheld when:

- no pitch is available;
- periodicity is below the configured gate;
- pitch stability is below the configured gate;
- the best candidate does not improve the deterministic fitness score enough.

Unpitched material remains eligible for later non-periodic or spectral reconstruction.
The stage does not falsely assign a pitch to noisy or silent material.

## Hash and identity chain

```text
PitchPeriodicityAnalysis.analysis_sha256
    └── WorkingPitchCandidates.analysis_sha256
            └── WorkingPitchPlan.analysis_sha256
```

Every object preserves:

- sample rate;
- sample count;
- canonical sample SHA-256;
- the upstream pitch-analysis SHA-256;
- deterministic candidate and plan SHA-256 values.

## CLI

```powershell
W-MWXT-WAVETABLE-TOOL pitch-plan `
  "D:\Audio\source.wav" `
  --policy auto `
  --report "D:\Reports\source.pitch-plan.json"
```

Explicit lock example:

```powershell
W-MWXT-WAVETABLE-TOOL pitch-plan `
  "D:\Audio\source.wav" `
  --policy lock `
  --locked-frequency 330 `
  --report "D:\Reports\source.pitch-lock.json"
```

## Safety boundary

CODE V6-A does not:

- resample or rewrite audio;
- create a temporary audio file;
- segment source material;
- select or reconstruct cycles;
- quantize XT waves;
- generate SysEx;
- transmit MIDI;
- execute any irreversible action.

The output is an auditable plan only. Temporary sample-domain repitch execution and
cycle material are gated by later CODE V6 stages.

## Targeted validation

```text
Core candidate and policy tests : 48
CLI tests                       : 5
Public API tests                : 5
Targeted total                  : 58
```

## Acceptance gate

CODE V6-A passes when:

1. all 58 targeted tests pass;
2. the public and private full suites pass;
3. two real-audio `pitch-plan` reports are byte-identical;
4. every selected candidate links to the candidate set;
5. source audio remains unchanged;
6. no private audio or generated report enters Git.
