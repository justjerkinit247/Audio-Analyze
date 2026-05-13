# Run an existing LTX pipeline command after automatically injecting ASMO timing directives.
#
# Example:
#   .\scripts\run_ltx_with_asmo.ps1 `
#     -PlanJson "outputs\ltx_video_run\runs\YOUR_PLAN.json" `
#     -Lyrics "inputs\lyrics\YOUR_LYRICS.txt" `
#     -RunnerCommand "python scripts\YOUR_EXISTING_LTX_RUNNER.py --plan {ASMO_PLAN}"
#
# The token {ASMO_PLAN} is replaced with the generated ASMO-injected plan path.

param(
    [Parameter(Mandatory = $true)]
    [string]$PlanJson,

    [Parameter(Mandatory = $true)]
    [string]$Lyrics,

    [Parameter(Mandatory = $true)]
    [string]$RunnerCommand,

    [int]$MaxEventsPerScene = 8
)

$ErrorActionPreference = "Stop"

$RepoPath = "C:\Users\Tt-rexX\Documents\GitHub\Audio-Analyze"
$VenvActivate = Join-Path $RepoPath ".venv\Scripts\Activate.ps1"

Set-Location $RepoPath

if (Test-Path $VenvActivate) {
    . $VenvActivate
}
else {
    throw "Virtual environment activation script not found: $VenvActivate"
}

$PlanPath = Resolve-Path $PlanJson
$LyricsPath = Resolve-Path $Lyrics
$PlanItem = Get-Item $PlanPath
$OutPath = Join-Path $PlanItem.DirectoryName ($PlanItem.BaseName + "_ASMO_INJECTED" + $PlanItem.Extension)

Write-Host "== ASMO auto-injection =="
Write-Host "Plan:   $PlanPath"
Write-Host "Lyrics: $LyricsPath"
Write-Host "Output: $OutPath"

python -c "from pathlib import Path; from src.audio_analyze.asmo_engine.ltx_run_integrator import inject_asmo_into_ltx_run_plan; inject_asmo_into_ltx_run_plan(Path(r'$PlanPath'), Path(r'$LyricsPath'), Path(r'$OutPath'), max_events_per_scene=$MaxEventsPerScene); print(r'$OutPath')"

if (!(Test-Path $OutPath)) {
    throw "ASMO injected plan was not created: $OutPath"
}

$CommandToRun = $RunnerCommand.Replace("{ASMO_PLAN}", $OutPath)

Write-Host "`n== Running LTX command =="
Write-Host $CommandToRun

Invoke-Expression $CommandToRun
