# LTX auto-audio orchestrator

Use this wrapper when you want the LTX pipeline to grab the current audio file automatically instead of typing the audio filename into every run command.

## Behavior

When `--audio` is omitted, the wrapper scans:

```text
inputs/audio
```

It picks the newest supported audio file by modified time. Supported extensions are inherited from the existing LTX pipeline.

The wrapper then calls the existing LTX orchestrator. It does not replace the old orchestrator logic; it only removes the manual audio-path step.

## Dry run

```powershell
python -m audio_analyze.ltx_auto_audio_orchestrator `
  --seed-dir "inputs\ltx_seed_images" `
  --output-plan "outputs\ltx_video_run\test_old_orchestrator_plan.json" `
  --report-json "outputs\ltx_video_run\test_old_orchestrator_report.json" `
  --resolution "9:16" `
  --max-scenes 1 `
  --scene-seconds 4 `
  --model "ltx-2-3-pro" `
  --guidance-scale 9.0 `
  --allow-sorted-seed-fallback
```

## Live run

Only add `--live` when `LTXV_API_KEY` is set.

```powershell
python -m audio_analyze.ltx_auto_audio_orchestrator `
  --seed-dir "inputs\ltx_seed_images" `
  --output-plan "outputs\ltx_video_run\test_old_orchestrator_live_plan.json" `
  --report-json "outputs\ltx_video_run\test_old_orchestrator_live_report.json" `
  --resolution "9:16" `
  --max-scenes 1 `
  --scene-seconds 4 `
  --model "ltx-2-3-pro" `
  --guidance-scale 9.0 `
  --allow-sorted-seed-fallback `
  --live
```

## Explicit override

You can still force a specific file:

```powershell
python -m audio_analyze.ltx_auto_audio_orchestrator --audio "inputs\audio\specific_file.mp3"
```

## Verification

```powershell
python -m pytest -q tests/test_ltx_auto_audio_orchestrator.py
```
