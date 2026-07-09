# Audio Analyze

Audio Analyze is a local-first hobby pipeline for audio analysis, prompt packaging, Runway scene generation support, LTX scene generation support, and short-form music video assembly.

## One-command LTX live run

On Windows, run the complete interactive LTX audio-and-image pipeline from the repository root with:

```powershell
.\run-ltx-live.cmd
```

The launcher handles the operational details inside the repository:

- opens file pickers for the source audio and seed image;
- preserves the exact seed-image filename for the Ollama prompt hint;
- creates a unique fresh-run folder and prevents stale-plan reuse;
- applies subject-count locking, tap sync, ASMO negative memory, and prompt-budget compaction;
- builds and validates the plan before any paid request;
- opens the exact final prompt for review;
- submits one live LTX request only after the user types `LIVE`.

A validation-only run is also available:

```powershell
.\run-ltx-live.cmd --dry-run
```

## What this repo does

- Analyze WAV and MP3 files for tempo, timing, and profile data
- Batch-process folders of audio files
- Generate prompt bundles and video cues
- Build Runway-oriented scene planning artifacts
- Build LTX-oriented seed-image scene planning artifacts
- Assemble short-form reels from generated scene clips
- Export beat-cut music video edits for TikTok/Reels style workflows

## Current pipeline areas

### Audio analysis
Core analysis modules estimate:
- duration
- sample rate
- tempo
- loudness / RMS style metrics
- prompt-ready summary data

### Prompt and workflow packaging
The repo includes tools that turn analysis output into:
- prompt bundles
- style mode bundles
- scene planning data
- Runway handoff artifacts
- LTX filename-hint motion prompt artifacts

### LTX filename-hint expansion
`src/audio_analyze/ltx_filename_hint_expander.py` expands scene hints embedded in seed image filenames into LTX image-to-video motion prompts.

This module is general-purpose. It does not analyze the actual image. The filename hint is treated as the creative source of truth, while the seed image remains the visual anchor for LTX.

Example seed image filename:

```text
scene_01_duck_flies_off_keyhole_to_ocean_clouds.png
```

Extracted scene hint:

```text
duck flies off keyhole to ocean clouds
```

Output text format:

```text
[MOTION_PROMPT]
The expanded LTX motion prompt goes here.

[NEGATIVE_PROMPT]
cleanup terms and negative prompt terms go here
```

Standalone smoke test:

```bash
PYTHONPATH=src python -m audio_analyze.ltx_filename_hint_expander single scene_01_duck_flies_off_keyhole_to_ocean_clouds.png
```

Batch seed-folder expansion:

```bash
PYTHONPATH=src python -m audio_analyze.ltx_filename_hint_expander expand-dir --seed-dir inputs/ltx_seed_images --output-dir inputs/prompts/ltx_filename_hints
```

Apply filename-hint expansions into an existing LTX plan JSON:

```bash
PYTHONPATH=src python -m audio_analyze.ltx_filename_hint_expander apply-plan --plan-json outputs/ltx_video_run/holy_cheeks_ltx_plan.json --output-dir inputs/prompts/ltx_filename_hints
```

Provider modes:
- `template`: offline deterministic fallback; no API key required
- `openai`: optional AI expansion provider; requires the `openai` package and an OpenAI API key

### Runway / video workflow
Current video-side tooling includes:
- stage pipeline generation support
- beat-cut short-form assembly
- mid-song reel building
- local archive/export handling

## Important repo behavior

This repo is set up to keep local media and generated outputs out of Git history.
Large local assets such as:
- source audio
- seed images
- generated video files
- local archive exports
are intentionally ignored through `.gitignore`.

## Main Python modules

Notable modules in `src/audio_analyze/` include:
- `analyzer.py`
- `pipeline_batch.py`
- `prompt_compiler.py`
- `runway_video_compiler.py`
- `runway_workflow_wrapper.py`
- `holy_cheeks_stage_pipeline.py`
- `beat_cut_engine.py`
- `mid_song_reel_builder.py`
- `ltx_filename_hint_expander.py`
- `ltx_live_run.py`

## Project intent

This is a practical creative-engineering repo for experimenting with:
- audio-to-prompt workflows
- AI-assisted music-video pipelines
- short-form edit assembly
- repeatable local generation/testing workflows

## Notes

This is a hobby project and is being evolved iteratively through real tests, local runs, and Git-based checkpoints.
