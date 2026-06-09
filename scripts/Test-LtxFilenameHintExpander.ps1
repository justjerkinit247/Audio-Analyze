<#
.SYNOPSIS
Run the LTX filename-hint expander tests and a PowerShell smoke test.

.USAGE
From the repo root:

    .\scripts\Test-LtxFilenameHintExpander.ps1

This script uses repo-relative paths and activates/creates .venv if needed.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

$VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (!(Test-Path $VenvActivate)) {
    Write-Host "Creating virtual environment at .venv ..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -m venv .venv
    }
    else {
        python -m venv .venv
    }
}

. $VenvActivate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$env:PYTHONPATH = "src"

Write-Host ""
Write-Host "Running targeted filename-hint expander tests..."
python -m pytest -q tests\test_ltx_filename_hint_expander.py

Write-Host ""
Write-Host "Running manual smoke test..."
python -m audio_analyze.ltx_filename_hint_expander single "scene_01_duck_flies_off_keyhole_to_ocean_clouds.png"

Write-Host ""
Write-Host "Done. Confirm the smoke output contains [MOTION_PROMPT] and [NEGATIVE_PROMPT]."
