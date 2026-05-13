# Real-input LTX + ASMO runner.
# Reads real audio, real .txt lyrics, and real seed image from fixed input folders.
# Does not create fake lyrics or fake visual content.

param(
    [Parameter(Mandatory = $true)]
    [string]$RunName,

    [Parameter(Mandatory = $true)]
    [string]$AudioFileName,

    [Parameter(Mandatory = $true)]
    [string]$LyricsFileName,

    [Parameter(Mandatory = $true)]
    [string]$SeedImageFileName,

    [string]$RunnerCommand = "",

    [int]$SceneCount = 8,

    [double]$SceneSeconds = 8.0,

    [int]$MaxEventsPerScene = 8
)

$ErrorActionPreference = "Stop"

$RepoPath = "C:\Users\Tt-rexX\Documents\GitHub\Audio-Analyze"
$VenvActivate = Join-Path $RepoPath ".venv\Scripts\Activate.ps1"

Set-Location $RepoPath

if (!(Test-Path $VenvActivate)) {
    throw "Virtual environment not found: $VenvActivate"
}

. $VenvActivate

$AudioPath = Join-Path $RepoPath ("inputs\audio\" + $AudioFileName)
$LyricsPath = Join-Path $RepoPath ("inputs\lyrics\" + $LyricsFileName)
$SeedImagePath = Join-Path $RepoPath ("inputs\seed_images\" + $SeedImageFileName)

if (!(Test-Path $AudioPath)) {
    throw "Missing audio file. Put it here: inputs\audio\$AudioFileName"
}

if (!(Test-Path $LyricsPath)) {
    throw "Missing lyrics text file. Put it here: inputs\lyrics\$LyricsFileName"
}

if ($LyricsPath -notmatch "\.txt$") {
    throw "Lyrics file must be .txt format. Current file: $LyricsPath"
}

if (!(Test-Path $SeedImagePath)) {
    throw "Missing seed image. Put it here: inputs\seed_images\$SeedImageFileName"
}

$RunRoot = Join-Path $RepoPath ("outputs\ltx_video_run\runs\" + $RunName)
$PlanPath = Join-Path $RunRoot ($RunName + "_plan.json")
$InjectedPlanPath = Join-Path $RunRoot ($RunName + "_plan_ASMO_INJECTED.json")

New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null

Write-Host "== Real-input ASMO/LTX runner =="
Write-Host "Audio:     $AudioPath"
Write-Host "Lyrics:    $LyricsPath"
Write-Host "SeedImage: $SeedImagePath"
Write-Host "RunRoot:   $RunRoot"

$results = @()

for ($i = 1; $i -le $SceneCount; $i++) {
    $start = [math]::Round(($i - 1) * $SceneSeconds, 3)
    $end = [math]::Round($i * $SceneSeconds, 3)

    $sceneType = "performance phrase"
    if ($i -eq 1) { $sceneType = "intro phrase" }
    if ($i -eq $SceneCount) { $sceneType = "closing phrase" }

    $results += [ordered]@{
        clip_index = $i
        scene = [ordered]@{
            scene_index = $i
            start = $start
            end = $end
            duration_seconds = $SceneSeconds
            scene_type = $sceneType
        }
        source_audio_path = $AudioPath
        scene_audio_path = $AudioPath
        seed_image_used = $SeedImagePath
        prompt_text = "Image-to-video continuation using the provided seed image. Maintain performer identity, wardrobe, camera continuity, scene continuity, musical timing, and synchronized motion."
        model = "ltx-2-3-pro"
    }
}

$plan = [ordered]@{
    schema = "ltx_run_plan.v1"
    run_name = $RunName
    source_audio_path = $AudioPath
    lyrics_path = $LyricsPath
    seed_image_path = $SeedImagePath
    scene_count = $SceneCount
    scene_seconds = $SceneSeconds
    results = $results
}

$plan | ConvertTo-Json -Depth 12 | Set-Content -Path $PlanPath -Encoding UTF8

Write-Host ""
Write-Host "Created real-input plan:"
Write-Host $PlanPath

Write-Host ""
Write-Host "== Injecting ASMO from real .txt lyrics + real audio =="

python -c "from pathlib import Path; from src.audio_analyze.asmo_engine.ltx_run_integrator import inject_asmo_into_ltx_run_plan; inject_asmo_into_ltx_run_plan(Path(r'$PlanPath'), Path(r'$LyricsPath'), Path(r'$InjectedPlanPath'), max_events_per_scene=$MaxEventsPerScene); print(r'$InjectedPlanPath')"

if (!(Test-Path $InjectedPlanPath)) {
    throw "ASMO injected plan was not created: $InjectedPlanPath"
}

python -c "import json; from pathlib import Path; p=Path(r'$InjectedPlanPath'); data=json.loads(p.read_text(encoding='utf-8-sig')); data['source_audio_path']=r'$AudioPath'; data['lyrics_path']=r'$LyricsPath'; data['seed_image_path']=r'$SeedImagePath'; results=data.get('results', []); [item.update({'source_audio_path': r'$AudioPath', 'scene_audio_path': item.get('scene_audio_path') or r'$AudioPath', 'seed_image_used': r'$SeedImagePath'}) for item in results if isinstance(item, dict)]; p.write_text(json.dumps(data, indent=2), encoding='utf-8'); print('Patched real inputs into:', p)"

Write-Host ""
Write-Host "ASMO injected plan ready:"
Write-Host $InjectedPlanPath

if ($RunnerCommand.Trim().Length -gt 0) {
    $CommandToRun = $RunnerCommand.Replace("{ASMO_PLAN}", $InjectedPlanPath)
    $CommandToRun = $CommandToRun.Replace("{AUDIO}", $AudioPath)
    $CommandToRun = $CommandToRun.Replace("{LYRICS}", $LyricsPath)
    $CommandToRun = $CommandToRun.Replace("{SEED_IMAGE}", $SeedImagePath)

    Write-Host ""
    Write-Host "== Running LTX command =="
    Write-Host $CommandToRun

    Invoke-Expression $CommandToRun
}
else {
    Write-Host ""
    Write-Host "No RunnerCommand provided. Stopped after creating ASMO-injected plan."
}
