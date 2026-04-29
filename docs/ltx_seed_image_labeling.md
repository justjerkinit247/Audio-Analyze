# LTX Scene Control and Seed Image Labeling

Use this when you want specific seed images, filename directions, and per-scene overrides assigned to specific LTX scenes.

This control layer does **not** call LTX and does **not** spend credits. It only edits the local plan JSON before generation.

## Folder

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

## Scene-labeled filenames

Scene labels supported in filenames:

```text
scene_01_intro_walk_forward.png
scene_02_over_shoulder_glance.webp
clip_03_twerk_accent_wide_angle.jpg
s04_group_walk_camera_arc.jpeg
```

The scene number controls which scene receives that seed image.

The extra words after the scene number become prompt direction unless you disable filename hints.

Example:

```text
scene_03_twerk_accent_wide_angle.png
```

Becomes:

```text
Scene 03 seed image assignment
Prompt add-on: twerk accent wide angle
```

## Recommended names

```text
scene_01_intro_walk_forward.png
scene_02_over_shoulder_glance.png
scene_03_twerk_accent_wide_angle.png
scene_04_group_walk_camera_arc.png
scene_05_closeup_confident_faces.png
scene_06_final_pose_stage_lights.png
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

## Step 2: Apply scene control mapping

```powershell
python -m src.audio_analyze.ltx_seed_mapper apply `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --seed-dir "inputs\ltx_seed_images" `
  --preview-md "outputs\ltx_video_run\scene_control_preview.md"
```

This rewrites the plan in place and updates each scene with:

- matching seed image
- filename prompt hint
- scene add-on
- prompt character count
- preview markdown report

## Strict mode

Use strict mode when every scene must have a labeled seed image:

```powershell
python -m src.audio_analyze.ltx_seed_mapper apply `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --seed-dir "inputs\ltx_seed_images" `
  --strict
```

## Disable filename prompt hints

Use this if you only want the filename to assign scenes, not influence the prompt:

```powershell
python -m src.audio_analyze.ltx_seed_mapper apply `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --seed-dir "inputs\ltx_seed_images" `
  --no-filename-hints
```

## Optional per-scene manifest

Create a template:

```powershell
python -m src.audio_analyze.ltx_seed_mapper template `
  --output "inputs\ltx_seed_images\scene_manifest_template.json"
```

Edit the JSON, then apply it:

```powershell
python -m src.audio_analyze.ltx_seed_mapper apply `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --seed-dir "inputs\ltx_seed_images" `
  --manifest-json "inputs\ltx_seed_images\scene_manifest_template.json" `
  --preview-md "outputs\ltx_video_run\scene_control_preview.md"
```

Manifest fields:

```json
{
  "scenes": [
    {
      "scene": 1,
      "seed_file": "scene_01_intro_walk_forward.png",
      "prompt_addon": "establish the performers walking forward with clean group formation",
      "camera": "smooth backward tracking shot, vertical reel framing",
      "motion": "confident synchronized walk, subtle groove on the beat",
      "negative_prompt": "avoid face warping, extra limbs, random costume changes",
      "notes": "planning note only"
    }
  ]
}
```

## Verify before spending credits

Open the preview:

```powershell
Get-Content "outputs\ltx_video_run\scene_control_preview.md" -Raw
```

Open the plan:

```powershell
Get-Content "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" -Raw
```

Look for:

```json
"seed_assignment": {
  "method": "scene_label",
  "seed_file": "scene_03_twerk_accent_wide_angle.png",
  "scene_label_expected": "scene_03",
  "filename_prompt_hint": "twerk accent wide angle",
  "scene_addon": "Seed filename direction: twerk accent wide angle.",
  "manifest_applied": false,
  "prompt_chars": 891
}
```

## Regenerate only the changed scene

After changing a seed image or direction, regenerate only that scene:

```powershell
python -m src.audio_analyze.ltx_holy_cheeks_pipeline submit-one `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --output "outputs\ltx_video_run\scene_03_result.json" `
  --clip-index 3 `
  --model "ltx-2-3-pro" `
  --guidance-scale 9.0 `
  --live
```

Do not rerun all scenes live unless you intentionally want to spend credits on every scene.
