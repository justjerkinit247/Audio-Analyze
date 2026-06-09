<#
.SYNOPSIS
Run the LTX filename-hint expander with a local Ollama model from Windows PowerShell.

.USAGE
From the repo root:

    .\scripts\Run-LtxFilenameHintExpanderOllama.ps1

Optional:

    .\scripts\Run-LtxFilenameHintExpanderOllama.ps1 -Filename "scene_02_duck_dives_into_cloud_portal.png" -Model "gemma3:4b"

This uses a local LLM through Ollama at http://127.0.0.1:11434.
No OpenAI key, billing card, or external API quota is required.
The image itself is not uploaded or analyzed; only the filename text is used.
#>

param(
    [string] $Filename = "scene_01_duck_flies_off_keyhole_to_ocean_clouds.png",
    [string] $Model = "gemma3:4b"
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
$env:LTX_FILENAME_HINT_INPUT = $Filename

Write-Host ""
Write-Host "Pulling local Ollama model if needed..."
Invoke-CheckedNativeCommand ollama pull $Model

$TempPy = Join-Path $env:TEMP "ltx_filename_hint_ollama_runner.py"

@'
from __future__ import annotations

import json
import os
import re
import sys

import requests

from audio_analyze.ltx_filename_hint_expander import (
    build_openai_instruction,
    clean_scene_hint,
    normalize_expansion,
)

filename = os.environ.get("LTX_FILENAME_HINT_INPUT", "").strip()
model = os.environ.get("OLLAMA_MODEL", "gemma3:4b").strip() or "gemma3:4b"

scene_hint = clean_scene_hint(filename)
if not scene_hint:
    raise SystemExit(f"No usable scene hint could be extracted from filename: {filename}")

instruction = build_openai_instruction(filename, scene_hint)

payload = {
    "model": model,
    "stream": False,
    "format": "json",
    "options": {
        "temperature": 0.35,
        "num_predict": 700,
    },
    "messages": [
        {
            "role": "system",
            "content": (
                "You convert seed-image filename scene hints into general-purpose LTX "
                "image-to-video motion prompts. Return strict JSON only. Do not describe "
                "the image. Use only the filename scene hint."
            ),
        },
        {"role": "user", "content": instruction},
    ],
}

try:
    response = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=240)
    response.raise_for_status()
except requests.RequestException as exc:
    raise SystemExit(f"Ollama request failed. Confirm Ollama is running locally, then retry. Details: {exc}") from exc

message = response.json().get("message", {})
content = str(message.get("content", "")).strip()
if not content:
    raise SystemExit(f"Ollama returned no message content for model {model}.")

# Some local models wrap JSON in markdown or extra prose. Extract the JSON object safely.
try:
    data = json.loads(content)
except json.JSONDecodeError:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise SystemExit(f"Ollama did not return parseable JSON:\n{content}")
    data = json.loads(match.group(0))

data.setdefault("model", model)
expansion = normalize_expansion(data, filename=filename, scene_hint=scene_hint, provider="ollama")
print(expansion["combined_ltx_text"])
'@ | Set-Content -Path $TempPy -Encoding UTF8

Write-Host ""
Write-Host "Running local Ollama filename-hint expansion..."
Write-Host "Model: $Model"
Write-Host "Filename: $Filename"
Write-Host ""

Invoke-CheckedNativeCommand python $TempPy

Write-Host ""
Write-Host "Done. Output above should contain [MOTION_PROMPT] and [NEGATIVE_PROMPT]."
