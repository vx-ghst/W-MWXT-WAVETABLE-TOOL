# CODE V8-K — Public addendum: WCTD materialization and N+1 package

## Scope

CODE V8-K consumes the validated V8-I physical-wave consolidation, the V8-J
allocation proposal, the manually selected User Wavetable destination, and the
fixed-tail contract inherited from V7.

Its product output is strictly:

```text
N WAVD + 1 WCTD
```

A complete product package containing `SNDD` remains CODE V9. Private V8-K
hardware fixtures may temporarily contain diagnostic `WAVD + WCTD + SNDD`, but
those fixtures are test-only, restored after measurement, and excluded from Git.

## Deferred LFO / Wave Envelope reconstruction requirement

The active V8-K hardware campaign is intentionally unchanged by the future musical
modulation-reconstruction requirement. V8-K continues to validate the native wave/table
representation, read-back, interpolation, audio behavior, and restoration using its current
controlled protocol.

After a valid V8-K hardware result, and while respecting the V8-L release boundary, CODE V9
and CODE V10 shall implement the mandatory deferred requirement to derive a target
wavetable-position trajectory from an analyzed sample and recommend/validate the most
appropriate XT realization: fixed Wave position, LFO, Wave Envelope, or a justified
LFO + Wave Envelope combination.

This deferred requirement shall not be used to reinterpret or invalidate evidence acquired
by the current V8-K campaign.

## WCTD materialization

The logical WCTD contains 64 unsigned 16-bit references:

- indexes `0..60`: user/interpolated positions displayed as `01..61`;
- indexes `61..63`: the three fixed tail positions;
- logical size: 128 bytes;
- wire payload: 256 nibbles;
- complete WCTD message: 265 bytes.

### Dense mode

- default product representation;
- all 61 user positions are explicit;
- repeated references are allowed after `61 -> N` consolidation;
- every allocated physical User Wave is referenced;
- no implicit interpolation is required.

### Sparse candidate

- built only for controlled hardware comparison;
- first and last user positions remain explicit;
- at least one explicit anchor represents each physical wave;
- other interpolable positions use the versioned sentinel contract;
- disabled until the real hardware campaign passes.

## User-WAVD 64-to-128 model

For User Waves transmitted through WAVD, the software model is:

```text
full[n]      = stored[n]       for n = 0..63
full[64 + k] = -stored[63-k]   for k = 0..63
```

This rule is versioned and hardware-gated. It is not generalized to ROM waves,
algorithmic waves, or every full-cycle capability described by the instrument.

## Safety boundaries

CODE V8-K:

- generates packages offline only;
- opens no MIDI port;
- transmits no byte;
- performs no automatic memory write;
- rejects broadcast Device ID unless an independently authorized future path exists;
- keeps sparse mode disabled without complete real evidence;
- does not start V8-L or release `0.8.0`.
