param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$DumpDirectory
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$resolvedDumpDirectory = (Resolve-Path -LiteralPath $DumpDirectory).Path

python -m pip install -e .

$files = @(
    "WALDORF_MWXT_ALL_SOUNDS.syx",
    "WALDORF_MWXT_ALL_WAVETABLES_AND_WAVES.syx",
    "WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22.syx",
    "WALDORF_MWXT_BACKUP_EVERYTHING_2026-07-22_B.syx"
) | ForEach-Object {
    $path = Join-Path $resolvedDumpDirectory $_
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required dump: $path"
    }
    $path
}

python -m w_mwxt_wavetable_tool.cli validate @files

foreach ($file in $files) {
    python -m w_mwxt_wavetable_tool.cli roundtrip $file
}
