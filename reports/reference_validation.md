# W-MWXT-WAVETABLE-TOOL CODE V1 reference validation

Generated: `2026-07-31T02:46:51.589212+00:00`

## Overall result

- Files validated: **4**
- Exact round trips: **True**
- Valid checksums and structures: **True**
- Everything backups identical: **True**

## File details

### `WALDORF_MWXT_ALL_SOUNDS.syx`

- Size: `67840` bytes
- SHA-256: `5a0996e68b183e9ca3afc5e2f0996945bd13493ba987f5d9af2d13673dd17451`
- Messages: `256`
- Device IDs: `[0]`
- Types: `{"SOUND": 256}`
- Message lengths: `{"265": 256}`
- Strict round trip: `True`
- Validation issues: `0`

### `WALDORF_MWXT_ALL_WAVETABLES_AND_WAVES.syx`

- Size: `42730` bytes
- SHA-256: `19e24c0c58a45eeb22e80268e156d4baa594debc2aed3a17bb17150ea6878808`
- Messages: `282`
- Device IDs: `[0]`
- Types: `{"USER_WAVE": 250, "USER_WAVETABLE": 32}`
- Message lengths: `{"137": 250, "265": 32}`
- Strict round trip: `True`
- Validation issues: `0`

### `WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22.syx`

- Size: `144529` bytes
- SHA-256: `4488e5fcb1a1991f429ff76044ea5f3bcba3061c3cc11ba60401f626d3510244`
- Messages: `667`
- Device IDs: `[0]`
- Types: `{"GLOBAL": 1, "MULTI": 128, "SOUND": 256, "USER_WAVE": 250, "USER_WAVETABLE": 32}`
- Message lengths: `{"137": 250, "265": 416, "39": 1}`
- Strict round trip: `True`
- Validation issues: `0`

### `WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22_B.syx`

- Size: `144529` bytes
- SHA-256: `4488e5fcb1a1991f429ff76044ea5f3bcba3061c3cc11ba60401f626d3510244`
- Messages: `667`
- Device IDs: `[0]`
- Types: `{"GLOBAL": 1, "MULTI": 128, "SOUND": 256, "USER_WAVE": 250, "USER_WAVETABLE": 32}`
- Message lengths: `{"137": 250, "265": 416, "39": 1}`
- Strict round trip: `True`
- Validation issues: `0`

## Reference hardware identity

`F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7`

- Waldorf Microwave XT
- 10 voices, non-expandable mainboard (`03 00`)
- OS `2.33`
- Device ID used by the dumps: `00`
