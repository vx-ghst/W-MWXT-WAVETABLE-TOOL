# CODE V7-E — deterministic XT hardware package dry-run

## Scope

CODE V7-E converts an accepted CODE V7-C 61-slot trajectory into a complete, deterministic Microwave XT package after requiring a matching CODE V7-D QC report with `status=pass`.

The stage creates files only. It never opens a MIDI port, sends SysEx, writes the synthesizer, or claims hardware acceptance.

## Required inputs

1. CODE V7-C trajectory JSON with exactly 61 slots.
2. Matching CODE V7-D QC JSON with zero flagged jumps and zero flagged curvature points.
3. A strict baseline backup containing every selected destination.
4. Explicit destinations:
   - 61 consecutive User Waves;
   - one User Wavetable in display range 097–128;
   - one stored Sound in A001–B128;
   - one stored template Sound, defaulting to the target Sound.

## Generated messages

The all-in-one package contains exactly 63 messages in this order:

1. 61 `WAVD` User Wave messages;
2. one `WCTD` User Wavetable message;
3. one `SNDD` Sound message.

The User Wavetable references the 61 generated User Waves in positions 1–61. The three tail references are preserved exactly from the selected baseline User Wavetable. Every generated User Wave remains inside the accepted safe range `-127..127`; `-128` is rejected.

The Sound template is converted into the controlled V7-A.2 audition patch already used for oscillator validation: Oscillator 1 only, 100% keytracking, fixed start wave and phase, open filters, neutral modulation, polyphonic normal assignment, and controlled headroom. The target Wavetable and Sound name are then encoded.

## Generated artifacts

- all-in-one package SysEx;
- separate User Wave, User Wavetable, and Sound SysEx files;
- exact baseline restore bundle for the 63 targets;
- canonical JSON and Markdown analysis reports;
- SHA-256 index.

## Status

`pass` means all 63 generated payloads differ from the selected baseline targets and the package is ready to enter CODE V7-F.

`review` means one or more targets already contain the generated payload. This is not a collision or restoration risk, but an exact post-write redump cannot prove that those specific messages were rewritten. CODE V7-F must resolve the review before hardware acceptance.

## Safety boundary

Transmission remains manual. Before any transmission:

1. verify the selected destinations and restore bundle;
2. send the three ordered SysEx files or the identical all-in-one package;
3. redump the written targets;
4. compare the redump during CODE V7-F;
5. test restoration when required.

CODE V7-E does not automate any of these hardware actions.
