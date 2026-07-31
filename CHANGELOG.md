# Changelog

All notable changes to **W-MWXT-WAVETABLE-TOOL** are documented here.

## 0.1.0 — CODE V1

- Added strict framing and splitting for concatenated Microwave XT SysEx streams.
- Added validation for Waldorf manufacturer ID, Microwave II/XT equipment ID, Device ID, message lengths, and checksums.
- Added 14-bit MIDI address and nibble codecs.
- Added typed models for Sound, Multi, User Wave, User Wavetable, and Global data.
- Added User Wave stored-sample decoding and explicit 128-point reconstruction policies.
- Added User Wavetable reference decoding.
- Added 16-character Sound name reading and editing.
- Added Universal Device Identity decoding for the reference XT running OS 2.33.
- Added CLI commands: `inspect`, `validate`, `roundtrip`, and `identity`.
- Added synthetic tests and strict round-trip validation against four real hardware dumps.
- Renamed the public project, Python distribution, and CLI to `W-MWXT-WAVETABLE-TOOL`.
