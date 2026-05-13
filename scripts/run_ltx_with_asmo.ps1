# Run LTX after automatically injecting ASMO timing directives.
# Requires real input files: audio, lyrics, and seed image.
# No fake starter content is created.

param(
    [Parameter(Mandatory = $true)]
    [string]$Audio,

    [Parameter(Mandatory = $true)]
    [string]$Lyrics,

    [Parameter(Mandatory = $true)]
    [string]$SeedImage,

    [Parameter(Mandatory = $true)]
    [string]$PlanJson,

    [Parameter(Mandatory = $true)]
    [string]$RunnerCommand,

    [int]$MaxEventsPerScene = 8
)

$ErrorActionPreference = "Stop"

$RepoPath = "C:\Users\Tt-rexX\Documents\GitHub\Audio-Analyze"
$VenvActivate = Join-Path $RepoPath ".venv\Scripts\Activate.ps1"

Set-Location $RepoPath

if (!(Test-Path $VenvActivate)) {
    throw "Virtual environment activation script not found: $VenvActivate"
}

. $VenvActivate

$AudioPath = Resolve-Path $Audio
$LyricsPath = Resolve-Path $Lyrics
$SeedImagePath = Resolve-Path $SeedImage
$PlanPath = Resolve-Path $PlanJson

$PlanItem = Get-Item $PlanPath
$OutPath = Join-Path $PlanItem.DirectoryName ($PlanItem.BaseName + "_ASMO_INJECTED" + $PlanItem.Extension)

Write-Host "== ASMO + LTX real-input runner =="
Write-Host "Audio:     $AudioPath"
Write-Host "Lyrics:    $LyricsPath"
Write-Host "SeedImage: $SeedImagePath"
Write-Host "Plan:      $PlanPath"
Write-Host "Output:    $OutPath"

python -c "from pathlib import Path; from src.audio_analyze.asmo_engine.ltx_run_integrator import inject_asmo_into_ltx_run_plan; inject_asmo_into_ltx_run_plan(Path(r'$PlanPath'), Path(r'$LyricsPath'), Path(r'$OutPath'), max_events_per_scene=$MaxEventsPerScene); print(r'$OutPath')"

if (!(Test-Path $OutPath)) {
    throw "ASMO injected plan was not created: $OutPath"
}

# Patch the injected plan with the resolved real seed image and audio path.
python -c "import json; from pathlib import Path; p=Path(r'$OutPath'); data=json.loads(p.read_text(encoding='utf-8-sig')); data['source_audio_path']=r'$AudioPath'; data['seed_image_path']=r'$SeedImagePath'; results=data.get('results', []); [item.update({'source_audio_path': r'$AudioPath', 'scene_audio_path': item.get('scene_audio_path') or r'$AudioPath', 'seed_image_used': r'$SeedImagePath'}) for item in results if isinstance(item, dict)]; p.write_text(json.dumps(data, indent=2), encoding='utf-8'); print('Patched real audio and seed image into injected plan:', p)"

$CommandToRun = $RunnerCommand.Replace("{ASMO_PLAN}", $OutPath)
$CommandToRun = $CommandToRun.Replace("{AUDIO}", $AudioPath)
$CommandToRun = $CommandToRun.Replace("{LYRICS}", $LyricsPath)
$CommandToRun = $CommandToRun.Replace("{SEED_IMAGE}", $SeedImagePath)

Write-Host "`n== Running LTX command =="
Write-Host $CommandToRun

Invoke-Expression $CommandToRun
