<#
.SYNOPSIS
Activate the Audio-Analyze Python virtual environment from Windows PowerShell.

.USAGE
From the repo root, dot-source this script so activation persists in the current terminal:

    . .\scripts\Activate-AudioAnalyze.ps1

This script uses repo-relative paths and does not require you to hard-code your local
C:\ path. It resolves the repo root from this script's location.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "Audio-Analyze repo root: $RepoRoot"

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

Write-Host "Activating virtual environment..."
. $VenvActivate

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

$Requirements = Join-Path $RepoRoot "requirements.txt"
if (Test-Path $Requirements) {
    Write-Host "Installing requirements from requirements.txt ..."
    python -m pip install -r $Requirements
}

$env:PYTHONPATH = "src"

Write-Host ""
Write-Host "Audio-Analyze virtual environment is active."
Write-Host "PYTHONPATH=src"
Write-Host "Repo root: $RepoRoot"
Write-Host ""
Write-Host "Run the filename-hint expander test with:"
Write-Host "python -m pytest -q tests\test_ltx_filename_hint_expander.py"
