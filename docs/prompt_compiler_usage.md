# Prompt Compiler Usage

This branch adds a compiler layer that turns pipeline batch analysis outputs into reusable prompt files.

## Recommended local command

```powershell
python .\src\audio_analyze\prompt_compiler.py --manifest ".\outputs\pipeline_batch_run\manifest.json"
```

## Output files

By default, the compiler writes to `outputs\prompt_bundle_run` and creates:

- `music_prompts.txt`
- `video_prompts.txt`
- `prompt_bundle.json`

## Why this exists

This is the handoff layer between analyzed audio metadata and the next stage of music/video workflow development.
It converts structured analysis outputs into prompt-ready text files and a bundled JSON summary.
