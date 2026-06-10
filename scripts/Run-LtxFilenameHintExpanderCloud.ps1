<#
.SYNOPSIS
Run the LTX filename-hint expander with an OpenAI-compatible cloud AI endpoint from Windows PowerShell.

.USAGE
From the repo root:

    $env:CLOUD_AI_API_KEY = "your_api_key_here"
    .\scripts\Run-LtxFilenameHintExpanderCloud.ps1

Optional OpenAI-compatible providers:

    $env:CLOUD_AI_BASE_URL = "https://api.openai.com/v1"
    $env:CLOUD_AI_MODEL = "gpt-4.1-mini"

    $env:CLOUD_AI_BASE_URL = "https://api.groq.com/openai/v1"
    $env:CLOUD_AI_MODEL = "llama-3.1-8b-instant"

    $env:CLOUD_AI_BASE_URL = "https://openrouter.ai/api/v1"
    $env:CLOUD_AI_MODEL = "meta-llama/llama-3.1-8b-instruct"

This script does not use local Ollama. It sends filename text only to the selected cloud AI.
It does not upload or analyze the seed images themselves.
#>

param(
    [string] $SeedDir = "inputs\ltx_seed_images",
    [string] $OutputDir = "inputs\prompts\ltx_filename_hints",
    [int] $MaxImages = 6,
    [string] $BaseUrl = $env:CLOUD_AI_BASE_URL,
    [string] $Model = $env:CLOUD_AI_MODEL
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

if ([string]::IsNullOrWhiteSpace($env:CLOUD_AI_API_KEY)) {
    throw "Missing CLOUD_AI_API_KEY. Set it first, for example: `$env:CLOUD_AI_API_KEY = 'your_key_here'"
}

if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    $BaseUrl = "https://api.openai.com/v1"
}

if ([string]::IsNullOrWhiteSpace($Model)) {
    $Model = "gpt-4.1-mini"
}

$env:PYTHONPATH = "src"
$env:CLOUD_AI_BASE_URL = $BaseUrl.TrimEnd("/")
$env:CLOUD_AI_MODEL = $Model
$env:CLOUD_SEED_DIR = $SeedDir
$env:CLOUD_OUTPUT_DIR = $OutputDir
$env:CLOUD_MAX_IMAGES = "$MaxImages"

$TempPy = Join-Path $env:TEMP "ltx_filename_hint_cloud_runner.py"

@'
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

from audio_analyze.ltx_filename_hint_expander import (
    build_openai_instruction,
    clean_scene_hint,
    normalize_expansion,
)

seed_dir = Path(os.environ.get("CLOUD_SEED_DIR", "inputs/ltx_seed_images"))
output_dir = Path(os.environ.get("CLOUD_OUTPUT_DIR", "inputs/prompts/ltx_filename_hints"))
max_images = int(os.environ.get("CLOUD_MAX_IMAGES", "6"))
base_url = os.environ.get("CLOUD_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
model = os.environ.get("CLOUD_AI_MODEL", "gpt-4.1-mini")
api_key = os.environ.get("CLOUD_AI_API_KEY", "").strip()

if not api_key:
    raise SystemExit("Missing CLOUD_AI_API_KEY.")

allowed = {".png", ".jpg", ".jpeg", ".webp"}
if not seed_dir.exists():
    raise SystemExit(f"Seed image folder not found: {seed_dir}")

images = sorted(path for path in seed_dir.iterdir() if path.is_file() and path.suffix.lower() in allowed)[:max_images]
if not images:
    raise SystemExit(f"No seed images found in {seed_dir}")

output_dir.mkdir(parents=True, exist_ok=True)

system_prompt = (
    "You convert seed-image filename scene hints into general-purpose LTX image-to-video motion prompts. "
    "Use only the filename scene hint. Do not analyze or claim to see the image. "
    "Return strict JSON only with filename, scene_hint, ltx_motion_prompt, negative_prompt, and motion_notes."
)

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

# OpenRouter accepts these optional headers; other OpenAI-compatible APIs ignore them.
if os.environ.get("CLOUD_AI_SITE_URL"):
    headers["HTTP-Referer"] = os.environ["CLOUD_AI_SITE_URL"]
if os.environ.get("CLOUD_AI_APP_NAME"):
    headers["X-Title"] = os.environ["CLOUD_AI_APP_NAME"]

print("")
print("Running cloud AI filename-hint expansion...")
print(f"Base URL: {base_url}")
print(f"Model: {model}")
print(f"Seed folder: {seed_dir}")
print(f"Output folder: {output_dir}")
print("")

for index, image_path in enumerate(images, start=1):
    filename = image_path.name
    scene_hint = clean_scene_hint(filename)
    if not scene_hint:
        print(f"SKIP {filename}: no usable filename scene hint")
        continue

    payload = {
        "model": model,
        "temperature": 0.35,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_openai_instruction(filename, scene_hint)},
        ],
        "response_format": {"type": "json_object"},
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=(20, 240),
    )

    if not response.ok:
        raise SystemExit(
            f"Cloud AI request failed for {filename}: HTTP {response.status_code}\n{response.text}"
        )

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except Exception as exc:
        raise SystemExit(f"Unexpected cloud AI response for {filename}:\n{json.dumps(body, indent=2)}") from exc

    content = str(content or "").strip()
    if not content:
        raise SystemExit(f"Cloud AI returned empty content for {filename}")

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise SystemExit(f"Cloud AI did not return parseable JSON for {filename}:\n{content}")
        data = json.loads(match.group(0))

    data.setdefault("model", model)
    expansion = normalize_expansion(data, filename=filename, scene_hint=scene_hint, provider="cloud")

    txt_path = output_dir / f"{image_path.stem}_ltx.txt"
    json_path = output_dir / f"{image_path.stem}_ltx.json"
    txt_path.write_text(expansion["combined_ltx_text"], encoding="utf-8")
    json_path.write_text(json.dumps(expansion, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{index}. {filename}")
    print(f"   Scene hint: {scene_hint}")
    print(f"   TXT:  {txt_path}")
    print(f"   JSON: {json_path}")
    print("")

print("DONE.")
'@ | Set-Content -Path $TempPy -Encoding UTF8

Write-Host ""
Write-Host "Running cloud filename-hint expansion..."
Write-Host "Base URL: $BaseUrl"
Write-Host "Model: $Model"
Write-Host ""

Invoke-CheckedNativeCommand python $TempPy

Write-Host ""
Write-Host "Done. Generated prompt files:"
Get-ChildItem $OutputDir -Filter "*_ltx.txt" | Select-Object Name,Length,LastWriteTime
