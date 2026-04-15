# Audio Analyze

Audio Analyze is a local-first hobby pipeline for audio analysis, prompt packaging, Runway scene generation support, and short-form music video assembly.

## What this repo does

- Analyze WAV and MP3 files for tempo, timing, and profile data
- Batch-process folders of audio files
- Generate prompt bundles and video cues
- Build Runway-oriented scene planning artifacts
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

## Project intent

This is a practical creative-engineering repo for experimenting with:
- audio-to-prompt workflows
- AI-assisted music-video pipelines
- short-form edit assembly
- repeatable local generation/testing workflows

## Notes

This is a hobby project and is being evolved iteratively through real tests, local runs, and Git-based checkpoints.