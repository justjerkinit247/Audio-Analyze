<#
.SYNOPSIS
Run the LTX filename-hint expander through the OpenAI provider from Windows PowerShell.

.USAGE
From a fresh PowerShell window, after switching to this repo folder:

    .\scripts\Test-LtxFilenameHintExpanderOpenAI.ps1

This script creates/activates .venv, installs repo requirements, installs the OpenAI Python SDK,
and runs one smoke test using --provider openai.

It does not save your API key. If OPENAI_API_KEY is not already set, it prompts for it and stores it
only for this PowerShell process.
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
python -m pip install openai

$env:PYTHONPATH = "src"

if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
    $SecureKey = Read-Host "Paste your OpenAI API key" -AsSecureString
    $PlainKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
    )
    $env:OPENAI_API_KEY = $PlainKey
}

$Model = $env:OPENAI_MODEL
if ([string]::IsNullOrWhiteSpace($Model)) {
    $Model = "gpt-4.1-mini"
}

Write-Host ""
Write-Host "Running OpenAI-provider smoke test..."
Write-Host "Model: $Model"
Write-Host ""

python -m audio_analyze.ltx_filename_hint_expander single "scene_01_duck_flies_off_keyhole_to_ocean_clouds.png" --provider openai --model $Model

Write-Host ""
Write-Host "Done. Confirm output contains [MOTION_PROMPT] and [NEGATIVE_PROMPT]."
