# ASMO local smoke-test runner for Windows PowerShell
# Run from anywhere. This script moves into the repo, enters .venv, installs deps, and runs ASMO tests.

$ErrorActionPreference = "Stop"

$RepoPath = "C:\Users\Tt-rexX\Documents\GitHub\Audio-Analyze"
$Branch = "lyric-audio-motion-sync-v1"
$VenvPath = Join-Path $RepoPath ".venv"
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"

Write-Host "== ASMO PowerShell Runner =="
Write-Host "Repo: $RepoPath"
Write-Host "Branch: $Branch"

if (!(Test-Path $RepoPath)) {
    throw "Repo path not found: $RepoPath"
}

Set-Location $RepoPath

Write-Host "`n== Git sync =="
git fetch origin
git switch $Branch
git pull origin $Branch

Write-Host "`n== Virtual environment =="
if (!(Test-Path $VenvPath)) {
    Write-Host "Creating .venv..."
    py -m venv .venv
}

if (!(Test-Path $ActivateScript)) {
    throw "Activation script not found: $ActivateScript"
}

Write-Host "Activating .venv..."
. $ActivateScript

Write-Host "Python:"
python --version

Write-Host "`n== Installing dependencies =="
python -m pip install --upgrade pip
pip install pytest numpy librosa soundfile scipy

Write-Host "`n== Syntax check =="
python -m py_compile install_asmo_pack_v3.py

Write-Host "`n== ASMO smoke test =="
python -m pytest tests\test_asmo_engine_smoke.py -v

Write-Host "`n== Done =="
git status
