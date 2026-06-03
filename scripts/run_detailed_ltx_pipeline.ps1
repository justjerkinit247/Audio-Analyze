param(
    [Parameter(Mandatory=$true)]
    [string]$Audio,

    [string]$SeedDir = "inputs\ltx_seed_images",
    [string]$OutputPlan = "outputs\ltx_video_run\detailed_ltx_plan.json",
    [string]$PreflightJson = "outputs\ltx_video_run\detailed_ltx_preflight.json",
    [string]$SubmitDir = "outputs\ltx_video_run\detailed_ltx_submissions",
    [string]$Resolution = "9:16",
    [int]$MaxScenes = 0,
    [double]$SceneSeconds = 8.0,
    [double]$StartOffsetSeconds = 0.0,
    [string]$StyleProfile = "generic_performance",
    [string]$Lyrics = "",
    [string]$TimelineJson = "",
    [string]$TimelineOutput = "outputs\ltx_video_run\detailed_asmo_timeline.json",
    [string]$Model = "ltx-2-3-pro",
    [double]$GuidanceScale = 9.0,
    [switch]$BeatAlign,
    [switch]$Live
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force | Out-Null

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    throw "Missing .venv. Run the Audio-Analyze environment setup before this script."
}

. .\.venv\Scripts\Activate.ps1

if (-not (Test-Path $Audio)) {
    throw "Audio file not found: $Audio"
}

if (-not (Test-Path $SeedDir)) {
    throw "Seed image folder not found: $SeedDir"
}

$planArgs = @(
    ".\src\audio_analyze\ltx_detailed_prompt_plan.py",
    "--audio", $Audio,
    "--seed-dir", $SeedDir,
    "--output", $OutputPlan,
    "--resolution", $Resolution,
    "--scene-seconds", "$SceneSeconds",
    "--start-offset-seconds", "$StartOffsetSeconds",
    "--style-profile", $StyleProfile
)

if ($MaxScenes -gt 0) {
    $planArgs += @("--max-scenes", "$MaxScenes")
}
if ($BeatAlign) {
    $planArgs += "--beat-align"
}
if (-not [string]::IsNullOrWhiteSpace($Lyrics)) {
    if (-not (Test-Path $Lyrics)) { throw "Lyrics file not found: $Lyrics" }
    $planArgs += @("--lyrics", $Lyrics, "--timeline-output", $TimelineOutput)
}
if (-not [string]::IsNullOrWhiteSpace($TimelineJson)) {
    if (-not (Test-Path $TimelineJson)) { throw "Timeline JSON not found: $TimelineJson" }
    $planArgs += @("--timeline-json", $TimelineJson)
}

Write-Host "[1/3] Building detailed audio-synced LTX plan..."
python @planArgs

Write-Host "[2/3] Running preflight..."
python .\src\audio_analyze\ltx_holy_cheeks_pipeline.py preflight `
    --plan-json $OutputPlan `
    --output $PreflightJson

$preflight = Get-Content $PreflightJson -Raw | ConvertFrom-Json
if ($preflight.status -ne "PASSED") {
    Write-Host "Preflight failed. Refusing submit." -ForegroundColor Red
    $preflight.problems | ForEach-Object { Write-Host "PROBLEM: $_" -ForegroundColor Red }
    exit 1
}

if ($Live) {
    if ([string]::IsNullOrWhiteSpace($env:LTXV_API_KEY)) {
        throw "LTXV_API_KEY is not set in this PowerShell window."
    }
    Write-Host "[3/3] Preflight passed. Submitting live to LTX..."
    python .\src\audio_analyze\ltx_holy_cheeks_pipeline.py submit-all `
        --plan-json $OutputPlan `
        --output-dir $SubmitDir `
        --model $Model `
        --guidance-scale $GuidanceScale `
        --live
} else {
    Write-Host "[3/3] Preflight passed. Dry-run submit only. Use -Live to generate videos."
    python .\src\audio_analyze\ltx_holy_cheeks_pipeline.py submit-all `
        --plan-json $OutputPlan `
        --output-dir $SubmitDir `
        --model $Model `
        --guidance-scale $GuidanceScale
}

Write-Host "DONE"
Write-Host "Plan:       $OutputPlan"
Write-Host "Preflight:  $PreflightJson"
Write-Host "Submit dir: $SubmitDir"
