# Real-input LTX + ASMO runner.
# Reads real audio, real .txt lyrics, and real seed images from fixed input folders.
# Seed image folder is: inputs\seed images
# Does not create fake lyrics or fake visual content.

param(
    [Parameter(Mandatory = $true)]
    [string]$RunName,

    [Parameter(Mandatory = $true)]
    [string]$AudioFileName,

    [Parameter(Mandatory = $true)]
    [string]$LyricsFileName,

    # Optional. If omitted, runner auto-selects seed images from inputs\seed images by label.
    [string]$SeedImageFileName = "",

    [string]$RunnerCommand = "",

    [int]$SceneCount = 8,

    [double]$SceneSeconds = 8.0,

    [int]$MaxEventsPerScene = 8
)

$ErrorActionPreference = "Stop"

$RepoPath = "C:\Users\Tt-rexX\Documents\GitHub\Audio-Analyze"
$VenvActivate = Join-Path $RepoPath ".venv\Scripts\Activate.ps1"
$SeedImagesDir = Join-Path $RepoPath "inputs\seed images"

Set-Location $RepoPath

if (!(Test-Path $VenvActivate)) {
    throw "Virtual environment not found: $VenvActivate"
}

. $VenvActivate

$AudioPath = Join-Path $RepoPath ("inputs\audio\" + $AudioFileName)
$LyricsPath = Join-Path $RepoPath ("inputs\lyrics\" + $LyricsFileName)

if (!(Test-Path $AudioPath)) {
    throw "Missing audio file. Put it here: inputs\audio\$AudioFileName"
}

if (!(Test-Path $LyricsPath)) {
    throw "Missing lyrics text file. Put it here: inputs\lyrics\$LyricsFileName"
}

if ($LyricsPath -notmatch "\.txt$") {
    throw "Lyrics file must be .txt format. Current file: $LyricsPath"
}

if (!(Test-Path $SeedImagesDir)) {
    throw "Missing seed image folder. Create it here: inputs\seed images"
}

$AllowedImageExt = @(".png", ".jpg", ".jpeg", ".webp")
$SeedFiles = Get-ChildItem -Path $SeedImagesDir -File | Where-Object { $AllowedImageExt -contains $_.Extension.ToLower() } | Sort-Object Name

if ($SeedFiles.Count -lt 1) {
    throw "No seed images found in: inputs\seed images"
}

if ($SeedImageFileName.Trim().Length -gt 0) {
    $SingleSeed = Join-Path $SeedImagesDir $SeedImageFileName
    if (!(Test-Path $SingleSeed)) {
        throw "Missing seed image: inputs\seed images\$SeedImageFileName"
    }
    $SeedFiles = @(Get-Item $SingleSeed)
}

function Get-SeedForScene {
    param(
        [int]$SceneNumber,
        [object[]]$AvailableSeeds
    )

    $labels = @(
        ("scene{0:D2}" -f $SceneNumber),
        ("scene{0}" -f $SceneNumber),
        ("seed{0:D2}" -f $SceneNumber),
        ("seed{0}" -f $SceneNumber),
        ("clip{0:D2}" -f $SceneNumber),
        ("clip{0}" -f $SceneNumber)
    )

    foreach ($label in $labels) {
        $match = $AvailableSeeds | Where-Object { $_.BaseName.ToLower().Contains($label.ToLower()) } | Select-Object -First 1
        if ($match) { return $match.FullName }
    }

    if ($AvailableSeeds.Count -ge $SceneNumber) {
        return $AvailableSeeds[$SceneNumber - 1].FullName
    }

    return $AvailableSeeds[0].FullName
}

$RunRoot = Join-Path $RepoPath ("outputs\ltx_video_run\runs\" + $RunName)
$PlanPath = Join-Path $RunRoot ($RunName + "_plan.json")
$InjectedPlanPath = Join-Path $RunRoot ($RunName + "_plan_ASMO_INJECTED.json")

New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null

Write-Host "== Real-input ASMO/LTX runner =="
Write-Host "Audio:         $AudioPath"
Write-Host "Lyrics:        $LyricsPath"
Write-Host "SeedImagesDir: $SeedImagesDir"
Write-Host "Seed count:    $($SeedFiles.Count)"
Write-Host "RunRoot:       $RunRoot"

$results = @()

for ($i = 1; $i -le $SceneCount; $i++) {
    $start = [math]::Round(($i - 1) * $SceneSeconds, 3)
    $end = [math]::Round($i * $SceneSeconds, 3)
    $SeedImagePath = Get-SeedForScene -SceneNumber $i -AvailableSeeds $SeedFiles

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
        seed_filename_prompt_hint = [System.IO.Path]::GetFileNameWithoutExtension($SeedImagePath)
        prompt_text = "Image-to-video continuation using the provided seed image. Maintain performer identity, wardrobe, camera continuity, scene continuity, musical timing, and synchronized motion."
        model = "ltx-2-3-pro"
    }
}

$plan = [ordered]@{
    schema = "ltx_run_plan.v1"
    run_name = $RunName
    source_audio_path = $AudioPath
    lyrics_path = $LyricsPath
    seed_images_dir = $SeedImagesDir
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

python -c "import json; from pathlib import Path; p=Path(r'$InjectedPlanPath'); data=json.loads(p.read_text(encoding='utf-8-sig')); data['source_audio_path']=r'$AudioPath'; data['lyrics_path']=r'$LyricsPath'; data['seed_images_dir']=r'$SeedImagesDir'; p.write_text(json.dumps(data, indent=2), encoding='utf-8'); print('Patched real input metadata into:', p)"

Write-Host ""
Write-Host "ASMO injected plan ready:"
Write-Host $InjectedPlanPath

if ($RunnerCommand.Trim().Length -gt 0) {
    $CommandToRun = $RunnerCommand.Replace("{ASMO_PLAN}", $InjectedPlanPath)
    $CommandToRun = $CommandToRun.Replace("{AUDIO}", $AudioPath)
    $CommandToRun = $CommandToRun.Replace("{LYRICS}", $LyricsPath)
    $CommandToRun = $CommandToRun.Replace("{SEED_IMAGES_DIR}", $SeedImagesDir)

    Write-Host ""
    Write-Host "== Running LTX command =="
    Write-Host $CommandToRun

    Invoke-Expression $CommandToRun
}
else {
    Write-Host ""
    Write-Host "No RunnerCommand provided. Stopped after creating ASMO-injected plan."
}
