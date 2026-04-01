# Wrapper and Style Modes Usage

This branch adds two workflow-oriented layers:

- `src/audio_analyze/style_mode_compiler.py`
- `src/audio_analyze/workflow_wrapper.py`

## Style mode compiler

Compile a style-targeted prompt file from the pipeline manifest:

```powershell
python .\src\audio_analyze\style_mode_compiler.py --manifest ".\outputs\pipeline_batch_run\manifest.json" --mode cinematic
```

Supported modes:
- `suno`
- `cinematic`
- `performance-video`
- `short-form-social`

## One-command wrapper

Run the full local workflow in one command:

```powershell
python .\src\audio_analyze\workflow_wrapper.py --input-dir "C:\Users\Tt-rexX\Music\TestAudio" --mode performance-video
```

This wrapper runs:
- pipeline batch analysis
- baseline prompt compiler
- refined creative prompt compiler
- style mode compiler

## Why this exists

This branch reduces friction by letting the user run the full local audio-to-prompt workflow with one command, while also supporting mode-specific prompt generation for different downstream use cases.
