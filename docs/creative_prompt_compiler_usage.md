# Creative Prompt Compiler Usage

This branch now includes a refined compiler layer that produces more creative music and video prompt language from the pipeline manifest.

## Recommended local command

```powershell
python .\src\audio_analyze\creative_prompt_compiler.py --manifest ".\outputs\pipeline_batch_run\manifest.json"
```

## Output files

By default, the refined compiler writes to `outputs\creative_prompt_bundle_run` and creates:

- `creative_music_prompts.txt`
- `creative_video_prompts.txt`
- `creative_prompt_bundle.json`

## Why this exists

The baseline prompt compiler proves the workflow. This refined compiler improves the handoff quality by translating analysis labels into more useful creative language for music and video workflow development.
