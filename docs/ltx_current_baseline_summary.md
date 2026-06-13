# LTX Current Baseline Summary

This is the committed baseline for the current LTX image-to-video orchestration path.

## Baseline stack

The standard auto-audio wrapper path now includes:

- Newest supported audio file is auto-selected from `inputs/audio` when `--audio` is omitted.
- Seed images are read from `inputs/ltx_seed_images`.
- Filename scene hints are expanded through Ollama by default using `gemma3:4b`.
- Beat alignment is default-on in the auto-audio wrapper.
- Audio timing is injected into the active prompt through an `[AUDIO_TIMING]` block.
- The active prompt includes `[AUDIO_TIMING]`, `[MOTION_PROMPT]`, and `[NEGATIVE_PROMPT]` sections.
- ASMO negative prompt memory is applied by default unless disabled with `--no-asmo-negative-memory`.
- The top prompt intro is intentionally looser and uses visual-anchor language instead of strict preservation language.

## Prompt policy

The top `Image-to-video continuation...` paragraph should stay clean and flexible.

It should not duplicate timing/BPM text. Scene timing, tempo, beat alignment, and sync rules belong inside `[AUDIO_TIMING]` only.

The intro should give the model enough freedom for creative cinematic interpretation while still anchoring the generation to:

- the seed image,
- the filename scene direction,
- the audio timing block,
- and the negative prompt cleanup terms.

## Current active prompt shape

```text
Image-to-video continuation for <file_stem>.
Use the seed image as the visual anchor for subject identity, pose family, camera angle, framing, lighting, and background.
Seed filename scene direction: <scene hint>.
Allow creative cinematic interpretation and natural motion development as long as it remains coherent with the seed image, filename direction, and audio timing.
Avoid random prior-project assumptions or unrelated characters/settings, but do not over-constrain the shot.

[AUDIO_TIMING]
Scene X audio window...
Tempo target...
Beat alignment...
Sync policy...
Motion timing cue...

[MOTION_PROMPT]
Filename-hint expanded motion prompt...

[NEGATIVE_PROMPT]
Filename-hint cleanup terms plus ASMO learned negative memory...
```

## Baseline test command

Use this dry run to verify the baseline without spending a live LTX call:

```powershell
python -m audio_analyze.ltx_auto_audio_orchestrator `
  --seed-dir "inputs\\ltx_seed_images" `
  --output-plan "outputs\\ltx_video_run\\baseline_commit_test_plan.json" `
  --report-json "outputs\\ltx_video_run\\baseline_commit_test_report.json" `
  --resolution "9:16" `
  --max-scenes 1 `
  --scene-seconds 4 `
  --model "ltx-2-3-pro" `
  --guidance-scale 9.0 `
  --filename-hint-provider "ollama" `
  --filename-hint-model "gemma3:4b" `
  --allow-sorted-seed-fallback
```

## Expected proof markers

A valid baseline run should show:

```text
Beat alignment enabled: True
Preflight status: PASSED
Dry run: True
Status: complete
prompt_build_method: filename_hint_expansion_with_audio_timing
plan beat_alignment_enabled: True
audio_timing beat_alignment_enabled: True
[AUDIO_TIMING]
[MOTION_PROMPT]
[NEGATIVE_PROMPT]
```

The intro should contain:

```text
visual anchor
Allow creative cinematic interpretation
```

The intro should not contain:

```text
Scene 1 covers
Motion should feel rhythm-aware
BPM
exact source of truth
Preserve the seed composition and make only
```

## Next development direction

Do not keep reshaping the core prompt wrapper until enough live outputs have been reviewed.

The next practical improvement is a closed-loop ASMO handoff:

1. Run live generations.
2. Write a next-generation context file after orchestration.
3. Review the output clips.
4. Save structured scene feedback.
5. Update ASMO memory from that feedback.
6. Let the next generation automatically inherit approved negative prompt lessons.
