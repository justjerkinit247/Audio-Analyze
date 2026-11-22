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
