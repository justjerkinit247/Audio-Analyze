# GTRG: use the existing seed + Gemma + ASMO cloud path (LTX API V2)

This is a **transport-layer compatibility fix**, not a rebuilt audio/video pipeline.
Do not change the native ComfyUI graph, `AAOFinishScene`, BeatGrid, ASMO event times,
Gemma prompts, scene boundaries, or the original soundtrack/export logic.

## Two different cloud options

- **LTX hosted API (this change):** the existing `run-ltx-live.cmd` flow
  uploads the selected scene audio and seed image, submits the *exact* synthesized
  motion prompt, and downloads a video. This uses LTX API credits.
- **Modal self-hosted GPU (separate experimental path):** the checked-in Modal
  GPU readiness canary is *not* a working remote LTX renderer and is not
  enabled by this change. A successful hosted LTX request is not evidence of
  Modal GPU rendering.

## Existing inputs and data flow

1. Choose the source track, seed PNG/JPG/WebP, and lyrics TXT/LRC.
2. The existing planner runs Audio Analyze, Gemma visual/prompt stages,
   BeatSync/TapSync and ASMO timing and creates an isolated fresh-run plan.
3. Preflight requires a nonempty exact prompt, seed path, audio path, valid
   scene settings, subject-lock policy and ASMO timeline.
4. The existing `submit_one` extracts the actual scene audio and calls
   `LTXClient.audio_to_video(audio_uri, image_uri, prompt, ...)`.
5. The **same client** now uploads media through `POST /v1/upload`, sends the
   generation request to `POST /v2/audio-to-video`, polls
   `GET /v2/audio-to-video/{id}`, and downloads `result.video_url`.
   It includes the job ID in errors so an uncertain result is not
   automatically resubmitted as another paid job.
6. The downloaded MP4 is returned through the existing fresh-run result path.

## Safe Windows rehearsal

From the **existing** Audio-Analyze checkout, with the existing virtual
environment and Ollama available:

```powershell
cd "$HOME\Documents\Audio-Analyze"
.\run-ltx-live.cmd --dry-run --scene-seconds 6 --model ltx-2-3-pro
```

The file pickers request a **seed image, audio and lyrics**. This exercises
the existing planner and exact-prompt validation; it **does not upload media,
submit a paid job, or launch Modal**.

To submit one paid LTX-hosted clip, omit `--dry-run`; the launcher opens the
exact final prompt and requires the typed confirmation `LIVE`:

```powershell
.\run-ltx-live.cmd --scene-seconds 6 --model ltx-2-3-pro
```

No real paid request should be submitted until the user reviews the prompt,
selected seed/audio, account credits and intended cost.

**Important model distinction:** LTX-2.3 `ltx-2-3-fast` supports
*image-to-video*, but the documented **audio-to-video** endpoint accepts
`ltx-2-3-pro`, not `ltx-2-3-fast`. Keep the current ASMO-driven
audio+image route on Pro; do not silently switch to image-only generation.

## Validation scope

`tests/test_ltx_client_v2.py` uses mocked HTTP responses to check seed,
audio and exact prompt forwarding, pending/processing/completed polling,
failed-job handling, download and dry-run safety. Passing offline tests does
**not** mean a live cloud generation has occurred. Do not add source audio,
seed images, credentials, generated videos or local run reports to Git.

Official documentation:
- https://docs.ltx.io/migrate-v1-to-v2
- https://docs.ltx.io/api-documentation/api-reference/async-video-generation/submit-audio-to-video
- https://docs.ltx.io/async-jobs
