# CODE V7-C — deterministic XT wavetable trajectory

## Purpose

CODE V7-C consumes the canonical CODE V7-B `XtProjectionSet` report and constructs a complete mathematical trajectory for the Microwave XT's 61 editable wavetable positions.

The stage remains offline and analytical. It does not allocate User Wave numbers, append the three fixed XT waves, generate WAVD/WCTD messages, or transmit SysEx.

## Canonical input

- one validated CODE V7-B JSON report;
- projection schema version 1;
- 128 source samples and 64 stored values per structural wave;
- safe quantization range `-127..127`;
- all 128 phase evaluations retained by CODE V7-B.

Every source and nested projection SHA-256 is verified before trajectory construction.

## Algorithm

1. Preserve every V7-B structural wave and its source order.
2. Recompute every 64-value candidate from the recorded source samples and phase index.
3. Under `global` phase policy, admit only phases whose V7-B objective stays within the explicit maximum increase.
4. Solve the complete phase path with deterministic dynamic programming using:
   - local V7-B fidelity cost;
   - adjacent stored-domain distance;
   - adjacent spectral distance.
5. Keep every structural wave as an anchor.
6. Reserve the configured minimum number of intermediate positions per transition.
7. Distribute all remaining positions by deterministic largest-remainder allocation, weighted by transition difficulty.
8. Interpolate directly in the 64-value XT-safe domain.
9. Quantize with half-away-from-zero rounding and reconstruct every 128-point wave with documented reverse-negate symmetry.

## Default policy

- target editable positions: 61;
- structural order: source order;
- phase path: global;
- interpolation: linear;
- local fidelity / transition weights: 0.35 / 0.65;
- transition time / spectral weights: 0.70 / 0.30;
- maximum local objective increase: 0.02;
- minimum intermediates per transition: 1;
- spacing power: 1.0.

## Output contract

`XtWavetableTrajectory` records:

- source V7-B and V6 hashes;
- all structural anchors;
- original and globally selected phase per anchor;
- objective increase and admissible phase count;
- transition distances and allocated intermediate counts;
- exactly 61 editable slots by default;
- 64 stored values and simulated 128-point reconstruction per slot;
- anchor positions, duplicate-adjacent diagnostics, continuity summary, and deterministic hashes;
- explicit stage boundaries.

## Rejection rules

The stage rejects:

- altered or hash-invalid V7-B reports;
- non-contiguous source wave indexes;
- fewer than two structural waves;
- more structural waves than the target slot count;
- malformed phase evaluations;
- values outside `-127..127`;
- any selected V7-B phase that no longer reproduces its recorded stored values;
- impossible minimum-intermediate policies;
- non-finite configuration values or invalid weight sums.

## Determinism

Identical input bytes and identical options must produce identical JSON and Markdown outputs. Tie-breaking is deterministic and phase-index ordered.

## Boundary

CODE V7-C does not:

- choose physical User Wave addresses;
- write User Wavetable memory;
- append the three fixed XT waves;
- encode WAVD or WCTD;
- create a Sound;
- transmit MIDI or SysEx.
