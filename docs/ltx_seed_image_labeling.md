# LTX Seed Image Labeling

Use this when you want specific seed images assigned to specific LTX scenes.

## Naming format

Put seed images in:

```text
inputs\ltx_seed_images\
```

Supported image extensions:

```text
.jpg
.jpeg
.png
.webp
```

Scene labels supported in filenames:

```text
scene_01.png
scene_02_back_shoulder.webp
clip_03_closeup.jpg
s04_wide_angle.jpeg
```

The scene number controls which scene receives that seed image.

## Recommended naming

```text
scene_01_intro_walk.png
scene_02_over_shoulder.png
scene_03_twerk_accent.png
scene_04_group_walk.png
scene_05_closeup_energy.png
scene_06_final_pose.png
```

## Step 1: Build or rebuild the LTX plan

```powershell
python -m src.audio_analyze.ltx_holy_cheeks_pipeline plan `
  --audio "inputs\audio\Gospel Twerk - Holy Cheeks (1).wav" `
  --seed-dir "inputs\ltx_seed_images" `
  --output "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --resolution "9:16" `
  --max-scenes 6 `
  --scene-seconds 8
```

## Step 2: Apply scene-labeled seed mapping

```powershell
python -m src.audio_analyze.ltx_seed_mapper `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --seed-dir "inputs\ltx_seed_images"
```

This rewrites the plan in place and updates each scene with the matching labeled seed image.

## Strict mode

Use strict mode when you want every scene to require a labeled seed image:

```powershell
python -m src.audio_analyze.ltx_seed_mapper `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --seed-dir "inputs\ltx_seed_images" `
  --strict
```

Strict mode reports missing scene labels instead of silently falling back.

## Verify mapping

Open the plan JSON:

```powershell
Get-Content "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" -Raw
```

Look for:

```json
"seed_assignment": {
  "method": "scene_label",
  "seed_file": "scene_01_intro_walk.png",
  "scene_label_expected": "scene_01"
}
```

## Then regenerate a scene

After changing seed mapping, regenerate only the scene you changed:

```powershell
python -m src.audio_analyze.ltx_holy_cheeks_pipeline submit-one `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --output "outputs\ltx_video_run\scene_02_result.json" `
  --clip-index 2 `
  --model "ltx-2-3-pro" `
  --guidance-scale 9.0 `
  --live
```

Do not rerun all scenes live unless you intentionally want to spend credits on every scene.
