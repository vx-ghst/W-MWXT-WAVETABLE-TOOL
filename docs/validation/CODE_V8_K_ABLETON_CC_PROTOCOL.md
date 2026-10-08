# CODE V8-K — Ableton Live MIDI/CC protocol

## Note names

| MIDI note | Ableton Live label | Scientific label |
|---:|---|---|
| 48 | C2 | C3 |
| 60 | C3 | C4 |
| 72 | C4 | C5 |

Tests and reports identify notes by MIDI number.

## Controllers

| CC | Parameter | Campaign interpretation |
|---:|---|---|
| 70 | Wavetable | value `0..127` selects displayed Wavetable `001..128` |
| 71 | Wave 1 Startwave | `0..60` selects displayed positions `01..61`; `61` Triangle; `62` Square; `63` Saw |

The campaign generates Standard MIDI Files and event logs offline. The operator
imports the requested clip into Ableton Live, verifies CC70/CC71 visually,
routes it manually, and records the output. No curve must be redrawn manually.

Dense and sparse comparison uses the exact same MIDI file and SHA-256. The
launcher itself performs no MIDI transport.
