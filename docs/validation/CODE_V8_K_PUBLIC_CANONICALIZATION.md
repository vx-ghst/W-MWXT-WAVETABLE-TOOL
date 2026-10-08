# CODE V8-K — Public documentation canonicalization

**Canonical public revision:** `V8K-PRE-HARDWARE-1.0-public`

## Purpose

This record reconciles the public specification, roadmap, published V8-G to
V8-J stages, the local V8-K software candidate, and the active hardware
protocol without publishing private working material.

## Resolved boundaries

1. CODE V8-K product output is `N WAVD + 1 WCTD`.
2. A temporary diagnostic `SNDD` is a private campaign fixture, not a V8 product output.
3. Dense WCTD is the default; sparse remains disabled before hardware PASS.
4. CC71 values `0..60` address displayed positions `01..61`; values `61..63` select the fixed Triangle/Square/Saw tail positions.
5. The reverse-negate `64 -> 128` model is limited to User Waves transmitted through WAVD and remains hardware-gated.
6. V8-K software and V8-K hardware acceptance are separate states.
7. V8-L remains a separate, explicitly authorized aggregate/release stage.

## Public/private boundary

Public Git content may contain contracts, aggregate test results, non-sensitive
hashes, and generic safety procedures. It must not contain SysEx dumps, exact
user-slot contents, read-backs, audio captures, installation screenshots, local
paths, or diagnostic fixture payloads.

## Status

```text
CANONICALIZATION=COMPLETE_PRE_HARDWARE
HARDWARE_CAMPAIGN=NOT_STARTED
SPARSE_ENABLED=false
V8L_STARTED=false
```
