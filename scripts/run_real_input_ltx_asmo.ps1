# Real-input LTX + ASMO runner.
# Auto-reads real audio from inputs\audio.
# Auto-reads real .txt lyrics from inputs\lyrics.
# Auto-reads real seed images from inputs\seed images.
# Builds LTX-compatible plan, injects ASMO, expands per-scene prompts under 5000 chars, then optionally runs LTX.
# Does not create fake lyrics or fake visual content.

param(
    [Parameter(Mandatory = $true)]
    [string]$RunName,

    [string]$AudioFileName = "",
    [string]$LyricsFileName = "",
    [string]$SeedImageFileName = "",
    [string]$RunnerCommand = "",

    # Default 0 means auto-match scene count to detected seed image count.
    [int]$SceneCount = 0,
    [double]$SceneSeconds = 8.0,
    [double]$StartOffsetSeconds = 0.0,
    [int]$MaxEventsPerScene = 8,
    [string]$Resolution = "1080x1920",
    [int]$PromptMaxChars = 5000,
    [int]$PromptTargetChars = 4850
)

$ErrorActionPreference = "Stop"

$RepoPath = "C:\Users\Tt-rexX\Documents\GitHub\Audio-Analyze"
$VenvActivate = Join-Path $RepoPath ".venv\Scripts\Activate.ps1"
$AudioDir = Join-Path $RepoPath "inputs\audio"
$LyricsDir = Join-Path $RepoPath "inputs\lyrics"
$SeedImagesDir = Join-Path $RepoPath "inputs\seed images"

Set-Location $RepoPath

if (!(Test-Path $VenvActivate)) { throw "Virtual environment not found: $VenvActivate" }
. $VenvActivate

if (!(Test-Path $AudioDir)) { throw "Missing audio input folder. Create it here: inputs\audio" }
if (!(Test-Path $LyricsDir)) { throw "Missing lyrics input folder. Create it here: inputs\lyrics" }
if (!(Test-Path $SeedImagesDir)) { throw "Missing seed image folder. Create it here: inputs\seed images" }

$AllowedAudioExt = @(".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg")
$AllowedImageExt = @(".png", ".jpg", ".jpeg", ".webp")

if ($AudioFileName.Trim().Length -gt 0) {
    $AudioPath = Join-Path $AudioDir $AudioFileName
    if (!(Test-Path $AudioPath)) { throw "Missing audio file. Put it here: inputs\audio\$AudioFileName" }
    $AudioFile = Get-Item $AudioPath
}
else {
    $AudioFiles = Get-ChildItem -Path $AudioDir -File | Where-Object { $AllowedAudioExt -contains $_.Extension.ToLower() } | Sort-Object LastWriteTime -Descending
    if ($AudioFiles.Count -lt 1) { throw "No supported audio files found in inputs\audio. Supported: $($AllowedAudioExt -join ', ')" }
    $AudioFile = $AudioFiles[0]
}

if ($LyricsFileName.Trim().Length -gt 0) {
    $LyricsPath = Join-Path $LyricsDir $LyricsFileName
    if (!(Test-Path $LyricsPath)) { throw "Missing lyrics text file. Put it here: inputs\lyrics\$LyricsFileName" }
    $LyricsFile = Get-Item $LyricsPath
}
else {
    $LyricsFiles = Get-ChildItem -Path $LyricsDir -File -Filter *.txt | Sort-Object LastWriteTime -Descending
    if ($LyricsFiles.Count -lt 1) { throw "No .txt lyric files found in inputs\lyrics. Lyrics must be plain .txt format." }
    $LyricsFile = $LyricsFiles[0]
}

$AudioPath = $AudioFile.FullName
$LyricsPath = $LyricsFile.FullName
if ($LyricsPath -notmatch "\.txt$") { throw "Lyrics file must be .txt format. Current file: $LyricsPath" }

$SeedFiles = Get-ChildItem -Path $SeedImagesDir -File | Where-Object { $AllowedImageExt -contains $_.Extension.ToLower() } | Sort-Object Name
if ($SeedFiles.Count -lt 1) { throw "No seed images found in: inputs\seed images" }

if ($SeedImageFileName.Trim().Length -gt 0) {
    $SingleSeed = Join-Path $SeedImagesDir $SeedImageFileName
    if (!(Test-Path $SingleSeed)) { throw "Missing seed image: inputs\seed images\$SeedImageFileName" }
    $SeedFiles = @(Get-Item $SingleSeed)
}

if ($SceneCount -lt 1) {
    $SceneCount = $SeedFiles.Count
    $SceneCountSource = "auto_seed_image_count"
}
else {
    $SceneCountSource = "manual_override"
}

function Get-SeedForScene {
    param([int]$SceneNumber, [object[]]$AvailableSeeds)
    $labels = @(("scene{0:D2}" -f $SceneNumber), ("scene{0}" -f $SceneNumber), ("seed{0:D2}" -f $SceneNumber), ("seed{0}" -f $SceneNumber), ("clip{0:D2}" -f $SceneNumber), ("clip{0}" -f $SceneNumber))
    foreach ($label in $labels) {
        $match = $AvailableSeeds | Where-Object { $_.BaseName.ToLower().Contains($label.ToLower()) } | Select-Object -First 1
        if ($match) { return $match.FullName }
    }
    if ($AvailableSeeds.Count -ge $SceneNumber) { return $AvailableSeeds[$SceneNumber - 1].FullName }
    return $AvailableSeeds[0].FullName
}

$RunRoot = Join-Path $RepoPath ("outputs\ltx_video_run\runs\" + $RunName)
$PlanPath = Join-Path $RunRoot ($RunName + "_plan.json")
$InjectedPlanPath = Join-Path $RunRoot ($RunName + "_plan_ASMO_INJECTED.json")
$MaximizedPlanPath = Join-Path $RunRoot ($RunName + "_plan_ASMO_INJECTED_MAXIMIZED.json")

New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null

Write-Host "== Real-input ASMO/LTX runner =="
Write-Host "AudioDir:             $AudioDir"
Write-Host "SelectedAudio:        $AudioPath"
Write-Host "LyricsDir:            $LyricsDir"
Write-Host "SelectedLyrics:       $LyricsPath"
Write-Host "SeedImagesDir:        $SeedImagesDir"
Write-Host "Seed count:           $($SeedFiles.Count)"
Write-Host "Scene count:          $SceneCount ($SceneCountSource)"
Write-Host "Scene seconds:        $SceneSeconds"
Write-Host "Start offset seconds: $StartOffsetSeconds"
Write-Host "Resolution:           $Resolution"
Write-Host "Prompt target:        $PromptTargetChars / $PromptMaxChars chars"
Write-Host "RunRoot:              $RunRoot"

$results = @()
for ($i = 1; $i -le $SceneCount; $i++) {
    $start = [math]::Round($StartOffsetSeconds + (($i - 1) * $SceneSeconds), 3)
    $end = [math]::Round($StartOffsetSeconds + ($i * $SceneSeconds), 3)
    $SeedImagePath = Get-SeedForScene -SceneNumber $i -AvailableSeeds $SeedFiles
    $sceneType = "performance phrase"
    if ($i -eq 1) { $sceneType = "intro phrase" }
    if ($i -eq $SceneCount) { $sceneType = "closing phrase" }

    $results += [ordered]@{
        clip_index = $i
        file_stem = $RunName
        scene = [ordered]@{
            scene_index = $i
            start = $start
            end = $end
            duration = $SceneSeconds
            duration_seconds = $SceneSeconds
            start_offset_seconds = $StartOffsetSeconds
            scene_type = $sceneType
        }
        source_audio_path = $AudioPath
        scene_audio_path = $AudioPath
        seed_image_used = $SeedImagePath
        seed_filename_prompt_hint = [System.IO.Path]::GetFileNameWithoutExtension($SeedImagePath)
        resolution = $Resolution
        prompt_text = "Image-to-video continuation using the provided seed image. Maintain performer identity, wardrobe, camera continuity, scene continuity, musical timing, and synchronized motion."
        model = "ltx-2-3-pro"
    }
}

$plan = [ordered]@{
    schema = "ltx_run_plan.v1"
    file_stem = $RunName
    run_name = $RunName
    source_audio_path = $AudioPath
    lyrics_path = $LyricsPath
    seed_images_dir = $SeedImagesDir
    seed_image_count = $SeedFiles.Count
    scene_count = $SceneCount
    scene_count_source = $SceneCountSource
    scene_seconds = $SceneSeconds
    start_offset_seconds = $StartOffsetSeconds
    resolution = $Resolution
    results = $results
}

$plan | ConvertTo-Json -Depth 12 | Set-Content -Path $PlanPath -Encoding UTF8
Write-Host ""
Write-Host "Created real-input plan:"
Write-Host $PlanPath

Write-Host ""
Write-Host "== Injecting ASMO from real .txt lyrics + real audio =="
python -c "from pathlib import Path; from src.audio_analyze.asmo_engine.ltx_run_integrator import inject_asmo_into_ltx_run_plan; inject_asmo_into_ltx_run_plan(Path(r'$PlanPath'), Path(r'$LyricsPath'), Path(r'$InjectedPlanPath'), max_events_per_scene=$MaxEventsPerScene, start_offset_seconds=$StartOffsetSeconds); print(r'$InjectedPlanPath')"
if (!(Test-Path $InjectedPlanPath)) { throw "ASMO injected plan was not created: $InjectedPlanPath" }

python -c "import json; from pathlib import Path; p=Path(r'$InjectedPlanPath'); data=json.loads(p.read_text(encoding='utf-8-sig')); data['source_audio_path']=r'$AudioPath'; data['lyrics_path']=r'$LyricsPath'; data['seed_images_dir']=r'$SeedImagesDir'; data['seed_image_count']=$($SeedFiles.Count); data['scene_count']=$SceneCount; data['scene_count_source']=r'$SceneCountSource'; data['scene_seconds']=$SceneSeconds; data['start_offset_seconds']=$StartOffsetSeconds; data['resolution']=r'$Resolution'; results=data.get('results', []); [item.update({'file_stem': item.get('file_stem') or r'$RunName', 'resolution': item.get('resolution') or r'$Resolution'}) for item in results if isinstance(item, dict)]; [item.setdefault('scene', {}).update({'duration': item.get('scene', {}).get('duration') or item.get('scene', {}).get('duration_seconds') or $SceneSeconds, 'start_offset_seconds': $StartOffsetSeconds}) for item in results if isinstance(item, dict)]; p.write_text(json.dumps(data, indent=2), encoding='utf-8'); print('Patched LTX-compatible metadata into:', p)"

Write-Host ""
Write-Host "== Expanding per-scene LTX scripts under 5000 chars =="
python -m src.audio_analyze.ltx_prompt_maximizer --plan-json "$InjectedPlanPath" --output "$MaximizedPlanPath" --prompt-max-chars $PromptMaxChars --prompt-target-chars $PromptTargetChars
if (!(Test-Path $MaximizedPlanPath)) { throw "Maximized ASMO plan was not created: $MaximizedPlanPath" }

Write-Host ""
Write-Host "ASMO injected + maximized plan ready:"
Write-Host $MaximizedPlanPath

if ($RunnerCommand.Trim().Length -gt 0) {
    $CommandToRun = $RunnerCommand.Replace("{ASMO_PLAN}", $MaximizedPlanPath)
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
    Write-Host "No RunnerCommand provided. Stopped after creating ASMO-injected maximized plan."
}
