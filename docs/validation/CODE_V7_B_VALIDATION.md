# CODE V7-B — XT-native 128→64 projection

## Scope

CODE V7-B consumes the accepted `CodeV6Analysis.reconstructed_wave_set` contract and projects every normalized 128-point cycle into the exact safe Microwave XT User Wave domain:

- 64 independent stored values;
- strict integer range `-127..127`;
- logical reconstruction `second_half[n] = -first_half[63-n]`;
- exhaustive search over all 128 integer phase rotations;
- temporal, spectral, seam, harmonic, and band metrics;
- deterministic JSON and Markdown reports;
- no allocation, WAVD construction, package generation, or MIDI/SysEx transmission.

The `-128` value remains excluded even though V7-A.2.1 found analog output compatible with a positive reconstructed edge. The audio evidence cannot distinguish exact internal `+127` saturation from a wider temporary `+128` representation.

## Projection theorem

For one rotated target pair `t[i]`, `t[127-i]`, the XT constraint is:

```text
x[i]       = q
x[127 - i] = -q
```

The continuous least-squares optimum is:

```text
q = (t[i] - t[127-i]) / 2
```

CODE V7-B then uses deterministic half-away-from-zero nearest-integer quantization of `127*q`. Because each constrained pair is independent, this is the exact quantized L2 optimum for a fixed phase rotation.

## Phase search

For each wave, all rotations `0..127` are evaluated. Candidate ordering is deterministic:

1. combined objective score;
2. temporal NRMSE;
3. spectral RMSE;
4. descending correlation;
5. lowest phase index.

## Default score weights

```text
time-domain NRMSE : 0.45
spectral RMSE     : 0.25
seam error        : 0.10
H1 error          : 0.06
H2 error          : 0.05
H3 error          : 0.04
band-power error  : 0.05
```

Weights are explicit, serialized, and required to sum exactly to `1.0`.

## Input safety

The implementation rejects:

- cycles not exactly 128 points;
- NaN or infinite samples;
- normalized peaks above `1.0`;
- silent cycles;
- malformed or mismatched JSON hashes;
- non-contiguous wave indexes;
- any stored value outside `-127..127`.

No implicit clipping or hidden normalization is performed.

## Outputs per wave

- source samples and SHA-256;
- source candidate linkage;
- 128 phase evaluations;
- selected and worst phase;
- 64 stored int8-safe values;
- 128 reconstructed integer values;
- source-aligned reconstructed float values;
- time RMSE and NRMSE;
- maximum error and correlation;
- spectral RMSE and cosine similarity;
- H1/H2/H3 errors;
- low/mid/high band-power errors;
- seam value and slope errors;
- objective score;
- deterministic projection SHA-256.

## Validation evidence

Focused V7-B tests in the delivery harness:

```text
13 passed
```

Combined local V7-A/V7-A.1/V7-A.2.1/V7-B harness:

```text
41 passed
```

Acceptance in the real repository requires:

```text
focused V7-B tests : 13 passed
full private suite : expected 1002 passed, 0 failed, 0 skipped
```

The exact total may increase if unrelated tests are added. The invariant is zero regressions and execution of all four private dump tests.

## Architectural boundary

CODE V7-B does not decide which waves occupy the 61 editable positions. It does not optimize inter-wave trajectory, allocate User Wave addresses, build WCTD/WAVD/SNDD messages, or contact the synthesizer. Those responsibilities belong to later V7-C/V7-D/V7-E stages.
