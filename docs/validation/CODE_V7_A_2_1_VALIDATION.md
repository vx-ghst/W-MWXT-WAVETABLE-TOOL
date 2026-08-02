# CODE V7-A.2.1 — 16-capture XT audio gate

## Purpose

V7-A.2.1 makes the four MIDI 60 edge recordings part of the official analysis:

- `offset_MIDI60_take01.wav`
- `negfs_MIDI60_take01.wav`
- `negfs_MIDI60_take02.wav`
- `negfs_MIDI60_take03.wav`

The canonical corpus is therefore 16 files: one silence file and fifteen sounding captures.

## Backward compatibility

An already generated V7-A.2 manifest containing the original 12-capture plan remains valid. During analysis, V7-A.2.1 deterministically expands that legacy plan to the canonical 16-capture plan. No new setup SysEx, selector SysEx, backup, or audio recording is required when the four exact MIDI 60 filenames already exist.

The original manifest SHA-256 and setup/restore contracts are not rewritten. The analysis report records a warning when a legacy 12-capture manifest was expanded.

## Statistical aggregation

Every capture is analyzed. Edge evidence is aggregated hierarchically:

1. repetitions are averaged within each MIDI note;
2. MIDI 36, 48, and 60 are averaged equally within each edge role;
3. OFFSET and NEGFS roles are averaged equally.

This avoids giving the three NEGFS repetitions three times the influence of the single-take OFFSET role while retaining all twelve edge recordings.

## Expected corpus

- silence: 1
- SAFE: MIDI 36, 48, 60 — one take each
- OFFSET: MIDI 36, 48, 60 — one take each
- NEGFS: MIDI 36, 48, 60 — three takes each

Total: 16 WAV files; 15 sounding takes.

## Validation

Focused harness:

```text
14 passed
```

Combined V7-A/V7-A.1/V7-A.2.1 harness:

```text
28 passed
```

The full repository suite and private-dump suite must be rerun in the real Windows repository after applying this patch.
