<#
.SYNOPSIS
Run the LTX filename-hint expander with a local Ollama model from Windows PowerShell.

.USAGE
From the repo root, expand every seed image filename into matching _ltx.txt/_ltx.json files:

    .\scripts\Run-LtxFilenameHintExpanderOllama.ps1 -Model "gemma3:4b"

Optional single-file test:

    .\scripts\Run-LtxFilenameHintExpanderOllama.ps1 -Filename "scene_02_duck_dives_into_cloud_portal.png" -Model "gemma3:4b"

This uses a local LLM through Ollama at http://127.0.0.1:11434.
No OpenAI key, billing card, or external API quota is required.
The image itself is not uploaded or analyzed; only the filename text is used.
#>

param(
    [string] $Filename = "",
    [string] $Model = "gemma3:4b",
    [string] $SeedDir = "inputs\ltx_seed_images",
    [string] $OutputDir = "inputs\prompts\ltx_filename_hints"
)

$ErrorActionPreference = "Stop"

function Invoke-CheckedNativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,

        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]] $ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
    }
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (!(Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "Ollama is not installed or not on PATH. Install it from https://ollama.com/download, reopen PowerShell, then run this script again."
}

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

$VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (!(Test-Path $VenvActivate)) {
    Write-Host "Creating virtual environment at .venv ..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        Invoke-CheckedNativeCommand py -m venv .venv
    }
    else {
        Invoke-CheckedNativeCommand python -m venv .venv
    }
}

. $VenvActivate

Invoke-CheckedNativeCommand python -m pip install --upgrade pip
Invoke-CheckedNativeCommand python -m pip install -r requirements.txt

$env:PYTHONPATH = "src"
$env:OLLAMA_MODEL = $Model

Write-Host ""
Write-Host "Checking/pulling local Ollama model if needed..."
Invoke-CheckedNativeCommand ollama pull $Model

Write-Host ""
Write-Host "Running native Python LTX filename-hint expansion with local Ollama..."
Write-Host "Model: $Model"

if ($Filename) {
    Write-Host "Filename: $Filename"
    Write-Host ""
    Invoke-CheckedNativeCommand python -m audio_analyze.ltx_filename_hint_expander single $Filename --provider ollama --model $Model
}
else {
    Write-Host "Seed dir: $SeedDir"
    Write-Host "Output dir: $OutputDir"
    Write-Host ""
    Invoke-CheckedNativeCommand python -m audio_analyze.ltx_filename_hint_expander expand-dir --seed-dir $SeedDir --output-dir $OutputDir --provider ollama --model $Model

    Write-Host ""
    Write-Host "Done. Generated prompt files:"
    Get-ChildItem $OutputDir -Filter "*_ltx.txt" | Select-Object Name,Length,LastWriteTime
}
