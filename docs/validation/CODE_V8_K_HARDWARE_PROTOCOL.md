# CODE V8-K — Public controlled hardware protocol

## Safety model

The hardware campaign is operator-controlled. The campaign software may build,
hash, inspect, and compare files offline, but it must not open a MIDI port,
transmit SysEx, or write instrument memory automatically.

Before temporary writes, the protocol requires complete backups, a non-broadcast
Device ID, exact destination authorization, and stored restoration messages.
Every installed test kit requires byte-identical read-back before audio capture.

## Evidence families

The real campaign contains 18 ordered steps and includes eight mandatory audio
analysis families:

1. User-WAVD `64 -> 128` reconstruction probes;
2. interpolation 50/50;
3. interpolation 2/3–1/3;
4. positions 58–64 and fixed-tail boundaries;
5. slow scan;
6. fast scan;
7. repeated forward/reverse scan;
8. dense/sparse comparison with one shared hashed MIDI clip.

Audio evidence is mono PCM 24-bit WAV at 96 kHz preferred or 48 kHz minimum,
with unchanged gain, no processing, no clipping, and a controlled neutral Sound.
Private audio and SysEx evidence remain outside Git.

## Final gate

Acceptance requires all steps to pass, all hashes and read-backs to match, no
invalid-reference transmission, and a final Everything backup byte-identical to
the initial backup. Any missing or contradictory evidence leaves sparse mode
disabled and hardware acceptance unclaimed.
