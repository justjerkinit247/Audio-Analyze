# Runway Video Compiler Usage

This branch adds a Runway-targeted handoff layer on top of the working local audio analysis pipeline.

## Added files

- `src/audio_analyze/runway_video_compiler.py`
- `src/audio_analyze/runway_workflow_wrapper.py`
- `tests/test_runway_video_compiler_smoke.py`

## What it produces

The Runway compiler reads `outputs\\pipeline_batch_run\\manifest.json` and creates:

- `outputs\\runway_video_run\\runway_prompts.txt`
- `outputs\\runway_video_run\\runway_payloads.json`

Each payload includes:

- `model`
- `generation_mode`
- `duration`
- `ratio`
- `promptText`
- analysis metadata for later iteration

## Recommended local command

```powershell
python .\src\audio_analyze\runway_workflow_wrapper.py --input-dir "C:\Users\Tt-rexX\Music\TestAudio" --mode performance-video --runway-model gen4.5 --ratio 1280:720
```

## Why this exists

This layer upgrades the repo from generic video-oriented prompt output into model-specific Runway handoff packaging so the next test can target a real video generation API format more directly.
