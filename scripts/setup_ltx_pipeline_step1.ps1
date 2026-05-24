# ==============================
# LTX PIPELINE STEP 1
# Windows PowerShell setup script
# Repository: Audio-Analyze
# ==============================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Location).Path
$InputRoot = Join-Path $RepoRoot "inputs"
$ImageDir = Join-Path $InputRoot "images"
$AudioDir = Join-Path $InputRoot "audio"
$PromptDir = Join-Path $InputRoot "prompts"
$OutputRoot = Join-Path $RepoRoot "outputs\ltx_video_run"
$StateRoot = Join-Path $OutputRoot "_state"

$SeedImagePath = Join-Path $ImageDir "club_confetti_seed.jpg"
$AudioPath = Join-Path $AudioDir "song.mp3"
$PromptPath = Join-Path $PromptDir "club_confetti_ltx_prompt.txt"
$NegativePromptPath = Join-Path $PromptDir "club_confetti_ltx_negative_prompt.txt"
$RunConfigPath = Join-Path $PromptDir "club_confetti_ltx_run_config.json"

$Directories = @(
    $ImageDir,
    $AudioDir,
    $PromptDir,
    $OutputRoot,
    $StateRoot,
    (Join-Path $StateRoot "active\features"),
    (Join-Path $StateRoot "active\feedback"),
    (Join-Path $StateRoot "memory")
)

foreach ($Directory in $Directories) {
    New-Item -ItemType Directory -Force -Path $Directory | Out-Null
}

$PromptText = @"
Cinematic nightlife dance-floor scene inside a packed neon club, based on the reference image. Preserve the same camera angle, crowd layout, pink-purple lighting, falling confetti, smoky atmosphere, and energetic party environment. The performers continue dancing naturally in place with rhythmic hip movement, shoulder bounces, small footwork, and crowd-reactive motion. Confetti keeps raining from above, catching the magenta and blue club lights. The crowd around them cheers, claps, records on phones, and moves subtly to the beat. Camera slowly pushes forward through the dance floor with slight handheld realism, maintaining a wide-angle music-video look. Lighting pulses gently in sync with the bass, with bright pink flare from center background and cool blue highlights from the right. Keep motion realistic, polished, adult club-party energy, high-detail faces and bodies, natural clothing physics, realistic dance timing, no exaggerated distortion, no cartoon movement, no nudity, no explicit sexual content. Professional music video style, immersive crowd energy, slow cinematic forward dolly, 24fps, realistic motion blur, nightclub haze, confetti storm, vibrant neon color grade.

Dance motion should land on clear beat accents: small hip bounce on every kick, shoulder pop on snare hits, confetti and light pulses responding subtly to bass impacts. Keep movement smooth and loopable for a short reel.
"@

$NegativePromptText = @"
Do not change the location. Do not remove the confetti. Do not change the lighting color palette. No nudity. No explicit sexual acts. No warped bodies, extra limbs, melting faces, distorted hands, duplicate people, broken anatomy, floating people, frozen crowd, sudden camera cuts, overexposed faces, unreadable signage focus, low-resolution blur, plastic skin, cartoon style, or glitchy motion.
"@

$PromptText | Set-Content -Path $PromptPath -Encoding UTF8
$NegativePromptText | Set-Content -Path $NegativePromptPath -Encoding UTF8

$Config = [ordered]@{
    project = "club_confetti_ltx"
    seed_image_path = $SeedImagePath
    audio_path = $AudioPath
    prompt_path = $PromptPath
    negative_prompt_path = $NegativePromptPath
    output_root = $OutputRoot
    state_root = $StateRoot
    target_fps = 24
    camera = "slow forward dolly with slight handheld sway"
    sync_rule = "visible dance motion lands on kick/snare accents; lighting/confetti subtly reacts to bass"
}

$Config | ConvertTo-Json -Depth 6 | Set-Content -Path $RunConfigPath -Encoding UTF8

Write-Host ""
Write-Host "LTX Pipeline Step 1 complete." -ForegroundColor Green
Write-Host "Repo root:              $RepoRoot"
Write-Host "Seed image target:      $SeedImagePath"
Write-Host "Audio target:           $AudioPath"
Write-Host "Prompt saved:           $PromptPath"
Write-Host "Negative prompt saved:  $NegativePromptPath"
Write-Host "Run config saved:       $RunConfigPath"
Write-Host ""

$MissingInputs = @()
if (-not (Test-Path $SeedImagePath)) {
    $MissingInputs += $SeedImagePath
}
if (-not (Test-Path $AudioPath)) {
    $MissingInputs += $AudioPath
}

if ($MissingInputs.Count -gt 0) {
    Write-Host "Missing input files:" -ForegroundColor Yellow
    foreach ($Missing in $MissingInputs) {
        Write-Host "  - $Missing" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Copy your seed image and audio into those exact paths before the live LTX submit step." -ForegroundColor Yellow
} else {
    Write-Host "Required seed image and audio files found. Ready for the next LTX pipeline step." -ForegroundColor Green
}
