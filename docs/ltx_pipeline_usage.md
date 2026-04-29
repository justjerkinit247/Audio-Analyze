# LTX Studio Pipeline Usage

This document is the no-credit-first workflow for the LTX Studio video pipeline.

The pipeline is designed to avoid accidental paid generations. By default, submit commands run in dry-run mode. A live API call only happens when `--live` is explicitly provided.

## Local setup

```powershell
cd "C:\Users\Tt-rexX\Documents\GitHub\Audio-Analyze"
git checkout main
git pull origin main
py -m pip install -r requirements.txt
py -m pytest
```

## Required local folders

```text
inputs\audio\
inputs\ltx_seed_images\
outputs\ltx_video_run\
```

Put the source song in:

```text
inputs\audio\
```

Put seed images in:

```text
inputs\ltx_seed_images\
```

Supported seed image extensions:

```text
.jpg
.jpeg
.png
.webp
```

## Step 1: Create an LTX scene plan

```powershell
py -m src.audio_analyze.ltx_holy_cheeks_pipeline plan `
  --audio "inputs\audio\Holy Cheeks.mp3" `
  --seed-dir "inputs\ltx_seed_images" `
  --output "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --resolution "9:16" `
  --max-scenes 6 `
  --scene-seconds 8
```

This creates:

```text
outputs\ltx_video_run\holy_cheeks_ltx_plan.json
```

## Step 2: Run preflight

```powershell
py -m src.audio_analyze.ltx_holy_cheeks_pipeline preflight `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --output "outputs\ltx_video_run\preflight_report.json"
```

Preflight checks:

- source audio exists
- seed images exist
- scene durations are within the allowed short-audio range
- prompts are not empty
- prompts are under 5000 characters
- resolution is normalized

If preflight fails, do not run live generation.

## Step 3: Dry-run one scene without spending credits

```powershell
py -m src.audio_analyze.ltx_holy_cheeks_pipeline submit-one `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --output "outputs\ltx_video_run\scene_01_result.json" `
  --clip-index 1 `
  --model "ltx-2-3-pro" `
  --guidance-scale 9.0
```

No `--live` flag means dry-run mode.

Expected outputs:

```text
outputs\ltx_video_run\scene_01_result.json
outputs\ltx_video_run\scene_audio\*_ltx_scene_01.wav
```

## Step 4: Dry-run all scenes without spending credits

```powershell
py -m src.audio_analyze.ltx_holy_cheeks_pipeline submit-all `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --output-dir "outputs\ltx_video_run" `
  --model "ltx-2-3-pro" `
  --guidance-scale 9.0
```

No `--live` flag means dry-run mode.

Expected output:

```text
outputs\ltx_video_run\ltx_submit_all_summary.json
outputs\ltx_video_run\scene_audio\*.wav
outputs\ltx_video_run\scene_*.json
```

## Step 5: Live generation for one scene only

Only run this after dry-run and preflight pass.

```powershell
$env:LTXV_API_KEY="PASTE_YOUR_LTX_API_KEY_HERE"

py -m src.audio_analyze.ltx_holy_cheeks_pipeline submit-one `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --output "outputs\ltx_video_run\scene_01_result.json" `
  --clip-index 1 `
  --model "ltx-2-3-pro" `
  --guidance-scale 9.0 `
  --live
```

Expected output location:

```text
outputs\ltx_video_run\downloads\
```

## Safety rule

Do not run `submit-all --live` until at least one `submit-one --live` generation has succeeded and the result looks usable.

## Notes

- The pipeline uses short scene-specific WAV files, not the full source song, for LTX audio-to-video submissions.
- The default scene length is 8 seconds.
- The accepted short-audio range is enforced as 2 to 20 seconds.
- The default model is `ltx-2-3-pro`.
- The default guidance scale is `9.0`.
