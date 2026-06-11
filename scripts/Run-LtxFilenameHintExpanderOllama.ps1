<#
.SYNOPSIS
Run the LTX filename-hint expander with a local Ollama model from Windows PowerShell.

.USAGE
From the repo root, expand every seed image filename into matching _ltx.txt/_ltx.json files:

    .\scripts\Run-LtxFilenameHintExpanderOllama.ps1 -Model "gemma3:4b" -MaxImages 6

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
    [string] $OutputDir = "inputs\prompts\ltx_filename_hints",
    [int] $MaxImages = 6
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
$env:LTX_FILENAME_HINT_SEED_DIR = $SeedDir
$env:LTX_FILENAME_HINT_OUTPUT_DIR = $OutputDir
$env:LTX_FILENAME_HINT_MAX_IMAGES = "$MaxImages"

Write-Host ""
Write-Host "Checking/pulling local Ollama model if needed..."
Invoke-CheckedNativeCommand ollama pull $Model

$TempPy = Join-Path $env:TEMP "ltx_filename_hint_ollama_runner.py"

@'
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

from audio_analyze.ltx_filename_hint_expander import (
    build_negative_prompt,
    build_openai_instruction,
    clean_scene_hint,
    normalize_expansion,
    write_expansion_files,
)

model = os.environ.get("OLLAMA_MODEL", "gemma3:4b").strip() or "gemma3:4b"
single_filename = os.environ.get("LTX_FILENAME_HINT_INPUT", "").strip()
seed_dir = Path(os.environ.get("LTX_FILENAME_HINT_SEED_DIR", "inputs/ltx_seed_images"))
output_dir = Path(os.environ.get("LTX_FILENAME_HINT_OUTPUT_DIR", "inputs/prompts/ltx_filename_hints"))
max_images = int(os.environ.get("LTX_FILENAME_HINT_MAX_IMAGES", "6"))

allowed = {".png", ".jpg", ".jpeg", ".webp"}

if single_filename:
    image_names = [single_filename]
else:
    if not seed_dir.exists():
        raise SystemExit(f"Seed image folder not found: {seed_dir}")
    image_names = [p.name for p in sorted(seed_dir.iterdir()) if p.is_file() and p.suffix.lower() in allowed][:max_images]
    if not image_names:
        raise SystemExit(f"No seed images found in {seed_dir}")

output_dir.mkdir(parents=True, exist_ok=True)

system_prompt = (
    "You convert seed-image filename scene hints into cinematic LTX image-to-video motion prompts. "
    "Return ONLY one strict JSON object. Do not wrap it in markdown. "
    "Required keys: filename, scene_hint, ltx_motion_prompt, negative_prompt, motion_notes. "
    "Use only the filename scene hint. Do not claim to see or analyze the image. "
    "The ltx_motion_prompt must be a present-tense paragraph describing subject motion, camera motion, environment motion, mood, and shot progression."
)


def coerce_ollama_json(raw: str, filename: str, scene_hint: str) -> dict:
    content = str(raw or "").strip()
    if not content:
        raise SystemExit(f"Ollama returned no message content for {filename}.")

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            # Last-resort fallback: treat the whole model output as the motion prompt.
            data = {"ltx_motion_prompt": content}

    if not isinstance(data, dict):
        data = {"ltx_motion_prompt": str(data)}

    # Different local models may use different names. Normalize common variants.
    if not data.get("ltx_motion_prompt"):
        for key in (
            "motion_prompt",
            "prompt",
            "video_prompt",
            "ltx_prompt",
            "description",
            "scene_motion_prompt",
            "cinematic_prompt",
        ):
            if data.get(key):
                data["ltx_motion_prompt"] = data[key]
                break

    if not data.get("ltx_motion_prompt"):
        # Final deterministic fallback instead of crashing.
        data["ltx_motion_prompt"] = (
            f"The shot begins from the seed image and develops the scene direction: {scene_hint}. "
            "The main subject moves with controlled, readable motion while the camera performs a smooth cinematic push, drift, or follow move that preserves the original framing. "
            "Background elements shift subtly so the scene feels alive without changing the location or adding unrelated characters. "
            "The motion builds from a quiet first frame into a stronger final moment with stable identity, clean continuity, and polished cinematic energy."
        )
        data.setdefault("motion_notes", []).append("fallback motion prompt used because Ollama did not return a recognized prompt key")

    data.setdefault("filename", filename)
    data.setdefault("scene_hint", scene_hint)
    data.setdefault("negative_prompt", build_negative_prompt(scene_hint))
    data.setdefault("motion_notes", [])
    data.setdefault("model", model)
    return data


print("")
print("Running local Ollama filename-hint expansion...")
print(f"Model: {model}")
print(f"Mode: {'single file' if single_filename else 'seed folder batch'}")
print(f"Output folder: {output_dir}")
print("")

for index, filename in enumerate(image_names, start=1):
    scene_hint = clean_scene_hint(filename)
    if not scene_hint:
        print(f"SKIP {filename}: no usable filename scene hint")
        continue

    instruction = build_openai_instruction(filename, scene_hint)
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.25,
            "num_predict": 700,
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instruction},
        ],
    }

    try:
        response = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=240)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SystemExit(f"Ollama request failed. Confirm Ollama is running locally, then retry. Details: {exc}") from exc

    message = response.json().get("message", {})
    raw_content = str(message.get("content", "")).strip()
    data = coerce_ollama_json(raw_content, filename=filename, scene_hint=scene_hint)
    expansion = normalize_expansion(data, filename=filename, scene_hint=scene_hint, provider="ollama")

    paths = write_expansion_files(filename, output_dir, expansion)
    print(f"{index}. {filename}")
    print(f"   Scene hint: {scene_hint}")
    print(f"   TXT:  {paths['txt_path']}")
    print(f"   JSON: {paths['json_path']}")
    print("")

print("DONE.")
'@ | Set-Content -Path $TempPy -Encoding UTF8

Write-Host ""
Write-Host "Running local Ollama filename-hint expansion..."
Write-Host "Model: $Model"
if ($Filename) {
    Write-Host "Filename: $Filename"
}
else {
    Write-Host "Seed dir: $SeedDir"
    Write-Host "Max images: $MaxImages"
}
Write-Host ""

Invoke-CheckedNativeCommand python $TempPy

Write-Host ""
Write-Host "Done. Generated prompt files:"
Get-ChildItem $OutputDir -Filter "*_ltx.txt" | Select-Object Name,Length,LastWriteTime
