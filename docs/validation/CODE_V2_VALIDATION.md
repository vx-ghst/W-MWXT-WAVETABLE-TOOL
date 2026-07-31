# CODE V2 Validation

## Release

- Version: `0.2.0`
- Scope: safe destinations, deterministic SysEx package construction, hardware preflight, read-back comparison, and restoration validation.
- Hardware: Waldorf Microwave XT
- MIDI transport used for the accepted hardware test: Bome SendSX
- Automatic MIDI transmission: not implemented

## CODE V2-A — Safe destinations and allocation

Implemented:

- Device IDs `0–126`;
- explicit opt-in for broadcast Device ID `127`;
- User Wavetable display/internal conversion;
- Sound destinations `A001–A128` and `B001–B128`;
- semantic Edit Buffer destination without guessing its wire address;
- strict and sanitized fixed-width Sound names;
- consecutive User Wave allocation;
- collision and reserved-target detection.

Validation:

- Targeted: `32 passed`
- Public regression: `44 passed, 4 skipped`
- Private regression: `48 passed`

## CODE V2-B — Deterministic package builder

Implemented:

- `PackageRequest`;
- deterministic planning and construction;
- User Wave relocation;
- User Wavetable reference remapping;
- Sound destination and name insertion;
- ordered messages: `WAVD → WCTD → SNDD`;
- checksum regeneration;
- JSON and Markdown manifests;
- strict package reparse and byte-identical round-trip;
- golden-vector package testing.

Validation:

- Targeted: `29 passed`
- Public regression: `73 passed, 4 skipped`
- Private regression: `77 passed`

## CODE V2-C — Hardware validation

Implemented:

- hardware package inspection;
- overwrite preflight;
- exact restoration bundle construction;
- controlled 61-wave hardware test package;
- read-back extraction;
- message-level comparison;
- missing, relocated, duplicate, address, Device ID, checksum, and payload-difference classification;
- CLI commands for test generation, preflight, and comparison.

Software validation:

- Targeted: `43 passed`
- Public regression: `116 passed, 4 skipped`
- Private regression: `120 passed`

Hardware test destinations:

- User Waves: `1189–1249`
- User Wavetable: display `128`, internal `127`
- Sound: `B128`
- Device ID: `00`

Hardware write result:

- Expected messages: `63`
- Exact read-back matches: `63`
- Unexpected differences: `0`
- Status: `pass_exact`

Hardware restoration result:

- Expected restoration messages: `63`
- Exact read-back matches: `63`
- Missing messages: `0`
- Unexpected differences: `0`
- Status: `pass_exact`

## Safety conclusion

The following operations were validated on real hardware:

1. generation of a deterministic `61 WAVD → 1 WCTD → 1 SNDD` package;
2. manual SysEx transmission;
3. exact hardware read-back;
4. restoration of every overwritten destination;
5. exact restoration read-back.

No private SysEx backup, capture, or generated hardware-test package is committed to the public repository.
