$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not $env:W_MWXT_DUMP_DIR) {
    Write-Host "W_MWXT_DUMP_DIR is not set. Synthetic tests will run; private dump tests may be skipped."
}

python -m pip install -e ".[dev]"
python -m pytest -v
