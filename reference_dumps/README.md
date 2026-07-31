# Private reference dumps are not included

Personal Microwave XT backups are deliberately excluded from the public repository.

To run the complete hardware-backed test suite on Windows, place the four files in one private directory and set:

```powershell
$env:W_MWXT_DUMP_DIR = "D:\Path\To\MicrowaveXT\Dumps"
python -m pytest -v
```

Expected filenames:

- `WALDORF_MWXT_ALL_SOUNDS.syx`
- `WALDORF_MWXT_ALL_WAVETABLES_AND_WAVES.syx`
- `WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22.syx`
- `WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22_B.syx`

Their expected byte sizes and SHA-256 fingerprints are recorded in `reference_manifest.json`.
