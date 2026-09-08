<#
.SYNOPSIS
Activate the Audio-Analyze Python 3.11 virtual environment from Windows PowerShell.

.USAGE
From the repo root, dot-source this script so activation persists in the current terminal:

    . .\scripts\Activate-AudioAnalyze.ps1

For a fresh PC or a machine migration, run scripts\Setup-New-PC.ps1 first.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "Audio-Analyze repo root: $RepoRoot"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

$VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

function Get-Python311Executable {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidate = (& py -3.11 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            return $candidate.Trim()
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $version = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $version -and $version.Trim() -eq "3.11") {
            $candidate = (& python -c "import sys; print(sys.executable)" | Select-Object -First 1)
            if ($candidate) {
                return $candidate.Trim()
            }
        }
    }

    return $null
}

if (!(Test-Path $VenvActivate)) {
    Write-Host "Creating Python 3.11 virtual environment at .venv ..."
    $Python311 = Get-Python311Executable
    if (-not $Python311) {
        throw "Python 3.11 was not found. Install Python 3.11 or run scripts\Setup-New-PC.ps1 after installing it."
    }
    & $Python311 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create the Python 3.11 virtual environment."
    }
}

$VenvVersion = (& $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" | Select-Object -First 1)
if (-not $VenvVersion -or $VenvVersion.Trim() -ne "3.11") {
    throw "Existing .venv is not Python 3.11. Run .\scripts\Setup-New-PC.ps1 -ForceRecreateVenv."
}

Write-Host "Activating Python 3.11 virtual environment..."
. $VenvActivate

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

$Requirements = Join-Path $RepoRoot "requirements.txt"
if (Test-Path $Requirements) {
    Write-Host "Installing requirements from requirements.txt ..."
    python -m pip install -r $Requirements
}

$env:PYTHONPATH = Join-Path $RepoRoot "src"

Write-Host ""
Write-Host "Audio-Analyze virtual environment is active."
Write-Host "Python: $(python --version)"
Write-Host "PYTHONPATH=$env:PYTHONPATH"
Write-Host "Repo root: $RepoRoot"
Write-Host ""
Write-Host "Run the filename-hint expander test with:"
Write-Host "python -m pytest -q tests\test_ltx_filename_hint_expander.py"
