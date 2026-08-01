# CODE V7-A.2 Validation — Controlled XT Audio Gate

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V7-A.2
Branch  : code-v7-xt-native-optimization
Version : 0.6.0 (unchanged until CODE V7-F)
```

## Purpose

CODE V7-A.1 established and physically verified the WAVD storage path:

```text
wire coding    : offset binary, most-significant bit flipped
stored samples : 64 signed values
logical cycle  : 128 values
reconstruction : second_half[n] = -first_half[63 - n]
safe range     : -127..+127
```

CODE V7-A.2 adds a controlled analog-output gate before CODE V7-B. It answers two
narrow questions:

1. are phase-folded XT output captures compatible with the documented reverse-negate
   structure for waves that exclude `-128`?
2. which candidate behavior is most compatible with the physical treatment of the
   `-128 -> +128` edge?

This stage is not the full CODE V10 oscillator/interpolation calibration and does not
claim bit-exact internal DSP recovery.

## Preconditions

The builder refuses to run unless both V7-A.1 reports are supplied and contain:

```text
storage report : status=pass, storage_passed=true,
                 v7_b_allowed_under_safe_range=true
restore report : status=pass, verdict=restore_confirmed
```

A fresh `Everything` backup must contain exactly one copy of each overwritten object:

```text
User Waves      1247, 1248, 1249 by default
User Wavetable  128 by default
Sound           B128 by default
```

All five original messages are copied into the restore bundle before any test package
is produced.

## Controlled Sound contract

The test Sound is cloned from the target Sound in the fresh backup. Reserved and
firmware-private bytes are preserved. Only documented measurement parameters are
forced.

Critical raw values include:

```text
Sound format               1
Osc 1 octave/semitone      64 / 64
Osc 1 detune               64
Osc 1 keytrack             48  (documented 100%)
Osc 2 keytrack             48  (documented 100%; oscillator is muted)
Wave 1 fixed phase         1
Wave 1 / Wave 2 level      96 / 0
Ringmod / noise / external 0 / 0 / 0
Aliasing                   0
Time Quantization          0
Clipping                   0  (Saturate)
Accuracy                   1
Filter 1 cutoff/resonance  127 / 0
Effect type / chorus       0 / 0
Glide / arpeggiator        off / off
Allocation / Assignment    Poly / Normal
Assignment detune          64
Amp envelope               attack 0, decay 0, sustain 127, release 0
Modulation matrix          16 rows disabled: source 0, amount raw 64, destination 0
```

The generated manifest records every forced byte under
`sound_control.raw_overrides` and also records every actual difference from the
original target Sound under `sound_control.changes`.

## Generated packages

```text
CODE_V7_A2_XT_AUDIO_GATE.setup.syx
    3 WAVD + 1 WCTD + 1 SNDD

CODE_V7_A2_XT_AUDIO_GATE.select-safe.syx
    1 WCTD + 1 SNDD

CODE_V7_A2_XT_AUDIO_GATE.select-offset-binary.syx
    1 WCTD + 1 SNDD

CODE_V7_A2_XT_AUDIO_GATE.select-negative-full-scale.syx
    1 WCTD + 1 SNDD

CODE_V7_A2_XT_AUDIO_GATE.restore.syx
    original 3 WAVD + original WCTD + original SNDD
```

Each selector repeats one diagnostic User Wave across all 61 editable wavetable
positions. This eliminates interpolation between different wave references while
keeping the three fixed terminal positions intact.

## Capture corpus

The generated MIDI clips use unambiguous MIDI note numbers:

```text
MIDI 36 — scientific C2 / Ableton C1
MIDI 48 — scientific C3 / Ableton C2
MIDI 60 — scientific C4 / Ableton C3
```

Required format:

```text
channels             mono
sample format        PCM 24-bit recommended
sample rate          96 kHz recommended; 48 kHz minimum
processing           none
input gain           unchanged for the complete corpus
minimum duration     1.5 seconds accepted; supplied clips hold 4 seconds
```

Required files:

```text
silence_5s.wav
safe_MIDI36_take01.wav
safe_MIDI48_take01.wav
safe_MIDI60_take01.wav
offset_MIDI36_take01.wav
offset_MIDI48_take01.wav
negfs_MIDI36_take01.wav
negfs_MIDI36_take02.wav
negfs_MIDI36_take03.wav
negfs_MIDI48_take01.wav
negfs_MIDI48_take02.wav
negfs_MIDI48_take03.wav
```

## Analysis method

For each signal capture, the analyzer:

1. validates mono format and sample rate;
2. trims attack and release regions;
3. estimates the fundamental by autocorrelation near the expected MIDI pitch;
4. folds the stable signal into 128 phase bins;
5. band-limits every candidate to the harmonics observable at that note and sample
   rate;
6. searches circular phase and polarity;
7. combines waveform correlation with normalized harmonic-magnitude similarity.

Safe-wave candidates:

```text
documented reverse-negate
repeat first half
mirror first half
negate first half without reversal
zero-filled second half
```

Negative-full-scale candidates:

```text
positive edge compatible (+127 or internal +128 not distinguished)
wrap to -128
zero replacement
repeat first half
```

The `-128` decision aggregates scores across all edge captures. Close results remain
explicitly inconclusive.

## Acceptance logic

CODE V7-B may proceed under the strict generation range `-127..+127` only when the
three safe captures independently select the documented reverse-negate candidate.

```text
safe candidate unique winner on all notes : PASS for V7-B safe range
mixed or close winners                     : INCONCLUSIVE
consistent non-documented winner           : FAIL / architecture conflict
```

The `-128` result is reported separately. An inconclusive edge result does not block
V7-B while `-128` remains prohibited.

## Safety sequence

1. build the kit from a fresh Everything backup and the two PASS V7-A.1 reports;
2. send only the setup package;
3. redump Everything and run `verify-setup`;
4. record the complete capture corpus using the selectors and MIDI clips;
5. run `analyze`;
6. send the restore bundle;
7. redump Everything and run `verify-restore`;
8. require exact restoration before closing V7-A.2.

No command in this stage transmits MIDI automatically.

## Focused automated validation

Local focused harness during delivery construction:

```text
V7-A.2 tests                              : 12 passed
combined V7-A / V7-A.1 / V7-A.2 tests    : 31 passed
compileall                                : passed
```

The focused harness is not a substitute for the complete repository suite. After
application to the real repository, acceptance requires:

```text
public suite expected : 983 passed, 4 skipped
private suite expected: 987 passed
```

The exact total may increase if the repository receives unrelated tests before the
patch is applied; the acceptance invariant is zero new failures and all four private
dump tests executed.

## Evidence boundary

Analog output can support or contradict the documented structural law and can rank
candidate `-128` policies. It cannot directly reveal exact internal DSP sample values,
DAC transfer details, or replace the later exhaustive interpolation/aliasing/time-
quantization calibration.
