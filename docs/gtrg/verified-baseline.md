# GTRG: verified operational baseline (2026-11-22)

This file separates **actually verified components** from work that is still experimental. The goal is fully automated music-video/reel creation using the existing Audio-Analyze/ASMO pipeline, with an optional Modal GPU worker for expensive LTX inference.

## Tested and retained on `main`

- The standalone narrative timing validator is stored at `src/audio_analyze/asmo_narrative_timing.py`. Its six built-in regression cases were run successfully. The independent standard-library test file is at `tests/test_asmo_narrative_timing.py`.
- The validator checks supplied, structured observations for temporal event order and specific failure conditions. Missing evidence results in `review_required`; known faults result in `reject`.
- Recorded **human-supplied** C/D observations produced `review_required` for C and `reject` for D. This is not autonomous computer-vision validation of those clips.
- The user separately verified in the live local ComfyUI instance that the newer `AAOASMOMotionLoop` node exposes `narrative_timing_mode`. That installed custom-node patch is **not yet committed to main**, since the uploaded `asmo_loop.py` was an older snapshot.

## Cloud baseline verified from user-provided CLI results

- The user's Modal CLI authentication succeeded in the `justjerkinit247` workspace.
- A headless ComfyUI image was built; an attempted L40S deployment initially required a payment method. A completed LTX GPU render **has not been verified**.
- The last account check displayed **0 active containers**, the `gtrg-ltx-worker` app **stopped** with **0 tasks**, **$0.01 metered usage** fully offset by **$0.01 credit**, and **$0.00 billed cost**. This is a point-in-time observation, not a future billing guarantee.
- No GPU rendering should run until a provider-enforced $0-out-of-pocket spend limit is verified. Code flags or a 5-second scale-down window do not replace an account-level limit.

## Not yet promoted to `main`

- Modal worker deployment and the LTX-2.3/2.5 rendering graph (the real `workflow_api.json` has not yet been fully mapped).
- Model-weight transfers, L40S memory/runtime benchmarks, and real video canary.
- Visual observer judgments, direct observer→ASMO review integration, and targeted autonomous retries. Offline tests alone do not establish production correctness.
- Cloud-side and controller updates from the local packages remain on an experimental development path until live verification.

## Deterministic local checks

From repository root (requires only Python 3):

```bash
python src/audio_analyze/asmo_narrative_timing.py --self-test
python -m unittest discover -s tests -p test_asmo_narrative_timing.py -v
```

These commands **do not** start ComfyUI, invoke Ollama, deploy to Modal, or incur GPU costs. Store secrets, songs, render outputs and model weights outside the Git repository.

## Golden-run preservation and BeatSync compatibility (2026-11-22)

- The original paid-generation route remains `run-ltx-live.cmd` and the existing `ltx_auto_audio_orchestrator.py` / `ltx_multi_scene_live_run.py`. Its checked-in `ltx_holy_cheeks_pipeline.py` sets model `ltx-2-3-pro`, guidance scale `9.0`, and default scene length `8.0` seconds. These are **repository defaults**, not a verified record of which exact run the user preferred.
- Do not replace or retime `BeatGridEngine`, `ltx_beat_align_plan.py`, `tap_accent_sync.py`, `asmo_sync_calibrator.py` or the ASMO timeline injection. Keep their source timestamps and scene boundaries authoritative across any cloud-rendering adapter.
- Cloud LTX-2.5 self-hosted/quantized weights are not guaranteed to produce the same visual quality as the hosted `ltx-2-3-pro` API. Compare with a retained favorite clip before choosing a cloud default.
- A narrow `ltx_live_run.py` choreography profile contract validation was restored through [PR #90](https://github.com/justjerkinit247/Audio-Analyze/pull/90) at commit `d3e20f0f3be299a9eb640b76628ff38aa37b2437`. All six GitHub Actions workflows completed successfully for that merge commit. The beat/tap timing modules were unchanged.
- Next safe action: obtain the actual latest `workflow_api.json` and representative successful run receipts from the Windows workstation; inventory custom nodes, weights, and input mapping offline. No GPU jobs until Modal account spending controls are independently confirmed.

## Historical user-run result inventory (2026-11-22)

The user inspected the local `outputs/ltx_video_run/live_runs/**/live_result.json` files after reinstalling Windows. The historical report showed **`ltx-2-3-pro` with guidance `12.0`** for multiple live attempts, including records marked `downloaded` on 2026-09-10 and 2026-08-11. Older 2026-07-25 records used guidance `9.0`; a 2026-07-09 record used `6.5`.

The report's `VideoExists` field was `False` for all rows because no MP4 existed at the recorded `downloaded_mp4_resolved_path`. This does **not** prove the videos were never generated, nor identify whether they moved following OS reinstall. The original outputs must be located or a representative clip compared before a quality claim is made. Treat **12.0 as observed historical guidance, not an assumed optimum**. The rendering backend migration must preserve the audio/beat/tap timing semantics and not translate the hosted API's numeric guidance directly into another model's non-equivalent control without testing.
