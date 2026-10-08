# CODE V8-K — Public software-validation record

## Baseline and reviewed candidate

```text
branch                 = code-v8-wavetable-builder
baseline commit        = 7d51e2a2f77afb682e2f3cace09fcca364b5dd17
software semantic tree = ce4e3c3730a3a2bd682f59ccf3a45cc7504add25
software patch SHA-256 = c4b6ed00cef95e1f0ea5f8909bb231aedc04d42d6f80a63f5b7ef8765e7e6c35
changed files          = 18
```

## Validated software scope

- dense WCTD with 61 explicit user-position references;
- repeated references after `61 -> N` consolidation;
- sparse hardware candidate with explicit anchors;
- fixed-tail preservation;
- 128-byte logical / 256-nibble wire / 265-byte complete WCTD forms;
- deterministic `N WAVD + 1 WCTD` package;
- strict WAVD-before-WCTD ordering;
- package reparse and deterministic manifests;
- file-backed 18-step hardware-gate model;
- sparse disabled without real passing evidence;
- public `build_code_v8k` aggregate with no partial output on rejection;
- no MIDI transport or automatic memory write.

## Regression evidence

The reviewed candidate passed targeted V8-K/WCTD tests, V8-J, V8-I, V8-H,
V8-G, V8-F, V8-D, historical V1/V2 contracts, the complete public suite,
compile checks, wheel/import checks, private-dump validation, frozen-module
identity, and private-data leakage scans.

## Current verdict

```text
software materialization = PASS
dense N+1 package        = PASS
sparse candidate         = BUILT_BUT_DISABLED
real hardware campaign   = NOT_STARTED
hardware acceptance      = NOT_CLAIMED
MIDI transport           = NONE
automatic memory write   = NONE
V8-L                      = NOT_STARTED
```

Hardware acceptance requires the public protocol described in
`CODE_V8_K_HARDWARE_PROTOCOL.md` and private file-backed evidence retained
outside Git.
