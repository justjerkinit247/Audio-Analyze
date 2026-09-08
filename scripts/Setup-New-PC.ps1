<#
.SYNOPSIS
Set up Audio-Analyze on a fresh Windows PC and optionally migrate local project data
from an older checkout without carrying over machine-specific caches or a virtual env.

.EXAMPLE
.\scripts\Setup-New-PC.ps1

.EXAMPLE
.\scripts\Setup-New-PC.ps1 -OldRepoPath "D:\Users\OldUser\Documents\GitHub\Audio-Analyze"

.EXAMPLE
.\scripts\Setup-New-PC.ps1 -OldRepoPath "D:\Users\OldUser\Documents\GitHub\Audio-Analyze" -CopyLegacyOutputs
#>

[CmdletBinding()]
param(
    [string]$OldRepoPath = "",
    [switch]$CopyLegacyOutputs,
    [switch]$ForceRecreateVenv,
    [switch]$SkipOllamaModel,
    [switch]$SkipValidation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-Python311Executable {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidate = (& py -3.11 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            return $candidate.Trim()
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidateVersion = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $candidateVersion -and $candidateVersion.Trim() -eq "3.11") {
            $candidate = (& python -c "import sys; print(sys.executable)" | Select-Object -First 1)
            if ($candidate) {
                return $candidate.Trim()
            }
        }
    }

    return $null
}

function Get-PythonMajorMinor {
    param([string]$PythonExe)
    $version = (& $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or -not $version) {
        return ""
    }
    return $version.Trim()
}

function Copy-DirectoryPreservingExisting {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string]$Label = "data"
    )

    if (-not (Test-Path $Source -PathType Container)) {
        Write-Host "Skip $Label: source not found -> $Source" -ForegroundColor DarkGray
        return
    }

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & robocopy $Source $Destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XC /XN /XO /NFL /NDL /NJH /NJS /NP | Out-Null
    $robocopyCode = $LASTEXITCODE
    if ($robocopyCode -ge 8) {
        throw "Robocopy failed for $Label with exit code $robocopyCode."
    }
    Write-Host "Migrated $Label -> $Destination" -ForegroundColor Green
}

function Copy-DirectoryArchive {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string]$Label = "archive"
    )

    if (-not (Test-Path $Source -PathType Container)) {
        Write-Host "Skip $Label: source not found -> $Source" -ForegroundColor DarkGray
        return
    }

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & robocopy $Source $Destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    $robocopyCode = $LASTEXITCODE
    if ($robocopyCode -ge 8) {
        throw "Robocopy failed for $Label with exit code $robocopyCode."
    }
    Write-Host "Archived $Label -> $Destination" -ForegroundColor Green
}

Write-Host "Audio-Analyze new-PC setup" -ForegroundColor Green
Write-Host "Repo root: $RepoRoot"

Write-Step "Checking Python 3.11"
$Python311 = Get-Python311Executable
if (-not $Python311) {
    Write-Host "Python 3.11 was not found." -ForegroundColor Yellow
    Write-Host "Install it, then rerun this script. With Windows Package Manager:" -ForegroundColor Yellow
    Write-Host "  winget install --id Python.Python.3.11 -e" -ForegroundColor White
    throw "Python 3.11 is required by this repository."
}
Write-Host "Python 3.11: $Python311" -ForegroundColor Green

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $VenvVersion = Get-PythonMajorMinor -PythonExe $VenvPython
    if ($ForceRecreateVenv -or $VenvVersion -ne "3.11") {
        Write-Step "Removing incompatible or explicitly reset .venv"
        Remove-Item -Recurse -Force (Join-Path $RepoRoot ".venv")
    }
}

if (-not (Test-Path $VenvPython)) {
    Write-Step "Creating Python 3.11 virtual environment"
    & $Python311 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create .venv with Python 3.11."
    }
}

Write-Step "Installing repository Python dependencies"
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed."
}
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

$env:PYTHONPATH = Join-Path $RepoRoot "src"

Write-Step "Creating local runtime directories"
$RuntimeDirectories = @(
    "inputs\audio",
    "inputs\lyrics",
    "inputs\ltx_seed_images",
    "inputs\runway_seed_images",
    "inputs\driving_performance",
    "inputs\character_images",
    "inputs\lip_sync_audio",
    "outputs\ltx_video_run\_state\memory",
    "outputs\ltx_video_run\_state\policy",
    "outputs\ltx_video_run\live_runs"
)
foreach ($relativePath in $RuntimeDirectories) {
    New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot $relativePath) | Out-Null
}

if ($OldRepoPath) {
    Write-Step "Migrating reusable local project data from old checkout"
    $OldRepoResolved = (Resolve-Path $OldRepoPath).Path
    if ($OldRepoResolved -eq $RepoRoot) {
        throw "OldRepoPath points to the current checkout. Supply the old PC/drive checkout instead."
    }

    $ReusableDirectories = @(
        "inputs\audio",
        "inputs\lyrics",
        "inputs\ltx_seed_images",
        "inputs\runway_seed_images",
        "inputs\driving_performance",
        "inputs\character_images",
        "inputs\lip_sync_audio"
    )

    foreach ($relativePath in $ReusableDirectories) {
        Copy-DirectoryPreservingExisting `
            -Source (Join-Path $OldRepoResolved $relativePath) `
            -Destination (Join-Path $RepoRoot $relativePath) `
            -Label $relativePath
    }

    # Preserve learned ASMO state, but do not reactivate stale per-run state that may
    # contain absolute paths from the old machine.
    foreach ($statePart in @("memory", "policy")) {
        $relativePath = "outputs\ltx_video_run\_state\$statePart"
        Copy-DirectoryPreservingExisting `
            -Source (Join-Path $OldRepoResolved $relativePath) `
            -Destination (Join-Path $RepoRoot $relativePath) `
            -Label "ASMO $statePart"
    }

    $MigrationStamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $MigrationArchive = Join-Path $RepoRoot "outputs\migration_archive\$MigrationStamp"

    # Preserve local prompt/config work as history without overwriting the clean checkout.
    Copy-DirectoryArchive `
        -Source (Join-Path $OldRepoResolved "inputs\prompts") `
        -Destination (Join-Path $MigrationArchive "inputs_prompts") `
        -Label "local prompt/config history"

    # Preserve the old active state as evidence/history only. New runs build fresh active state.
    Copy-DirectoryArchive `
        -Source (Join-Path $OldRepoResolved "outputs\ltx_video_run\_state\active") `
        -Destination (Join-Path $MigrationArchive "old_active_state") `
        -Label "old ASMO active-state history"

    if ($CopyLegacyOutputs) {
        Copy-DirectoryArchive `
            -Source (Join-Path $OldRepoResolved "outputs") `
            -Destination (Join-Path $MigrationArchive "legacy_outputs") `
            -Label "legacy generated outputs"

        Copy-DirectoryArchive `
            -Source (Join-Path $OldRepoResolved "archive\runway_generations\local_exports") `
            -Destination (Join-Path $MigrationArchive "runway_local_exports") `
            -Label "Runway local exports"
    }

    Write-Host ""
    Write-Host "Not migrated by design: .venv, .git, .env/secrets, CacheClip, .gallery, __pycache__." -ForegroundColor Yellow
    Write-Host "Those are machine-specific, rebuildable, or secret-bearing files." -ForegroundColor Yellow
}
else {
    Write-Host ""
    Write-Host "No -OldRepoPath supplied. Code/environment setup will continue without local-data migration." -ForegroundColor DarkYellow
}

Write-Step "Checking NVIDIA GPU visibility"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    & nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    if ($LASTEXITCODE -ne 0) {
        Write-Host "nvidia-smi exists but did not return GPU information." -ForegroundColor Yellow
    }
}
else {
    Write-Host "nvidia-smi was not found. Install/update the NVIDIA driver before relying on GPU-backed local AI." -ForegroundColor Yellow
}

Write-Step "Checking Ollama / Gemma local model"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    if (-not $SkipOllamaModel) {
        Write-Host "Ensuring gemma3:4b is installed..."
        & ollama pull gemma3:4b
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Ollama is installed, but gemma3:4b could not be pulled. The Python/test setup can still be validated." -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "Skipping Ollama model pull by request." -ForegroundColor DarkGray
    }
}
else {
    Write-Host "Ollama is not installed or not on PATH." -ForegroundColor Yellow
    Write-Host "Install it before a real LTX/ASMO run. With Windows Package Manager:" -ForegroundColor Yellow
    Write-Host "  winget install --id Ollama.Ollama -e" -ForegroundColor White
}

Write-Step "Checking FFmpeg availability"
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    $FfmpegVersion = (& ffmpeg -version 2>$null | Select-Object -First 1)
    Write-Host $FfmpegVersion -ForegroundColor Green
}
else {
    Write-Host "System FFmpeg is not on PATH. The current multi-scene code can fall back to imageio-ffmpeg when available." -ForegroundColor Yellow
}

if (-not $SkipValidation) {
    Write-Step "Compiling source and tests"
    & $VenvPython -m compileall -q src tests
    if ($LASTEXITCODE -ne 0) {
        throw "Python compile validation failed."
    }

    Write-Step "Running required LTX/ASMO migration smoke tests"
    $TargetedTests = @(
        "tests\test_asmo_engine_smoke.py",
        "tests\test_ltx_auto_audio_orchestrator.py",
        "tests\test_ltx_plan_prompt_expander.py",
        "tests\test_ltx_filename_hint_expander.py",
        "tests\test_ltx_filename_hint_expander_ollama.py",
        "tests\test_local_ai_client.py",
        "tests\test_asmo_negative_prompt_memory.py"
    )
    & $VenvPython -m pytest -q @TargetedTests
    if ($LASTEXITCODE -ne 0) {
        throw "Targeted LTX/ASMO validation failed."
    }
}
else {
    Write-Host "Validation skipped by request." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Audio-Analyze new-PC setup is complete." -ForegroundColor Green
Write-Host "Python:       $(& $VenvPython --version)"
Write-Host "Repo:         $RepoRoot"
Write-Host "PYTHONPATH:   $env:PYTHONPATH"
Write-Host "Live wrapper: .\run-ltx-live.cmd"
Write-Host "Safe test:    .\run-ltx-live.cmd --dry-run"
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "API keys and .env files are intentionally not copied. The live runner will request LTXV_API_KEY when needed." -ForegroundColor Yellow
