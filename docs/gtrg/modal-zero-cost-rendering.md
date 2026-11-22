# GTRG / ASMO cloud rendering — development branch

Status on 2026-11-22: **design and local/offline code tested; no proven live LTX cloud render.** This document is committed on a separate branch to preserve the existing `main` pipeline.

## System boundary

- **Local Windows workstation:** ComfyUI graph editing, Audio-Analyze planning, Gemma/Ollama analysis, ASMO scoring, event chronology, acceptance decisions, retries, final music assembly, and publishing preparation.
- **Modal GPU worker:** Headless ComfyUI on an NVIDIA L40S, running a separately exported render-only `workflow_api.json`. It must have every custom node and model used by the graph. Inputs and outputs are transferred using Modal Volumes with SHA-256 verification.
- **Never submit the full AAO/ASMO local controller graph to Modal.** `AAO*` nodes are host-side orchestration, not just inference nodes. Build a render subgraph adapter.
- **Source of truth:** This repository; do not check in generated videos, licensed model weights, credentials, API tokens, private audio, or workspace state.

## Zero-out-of-pocket requirement (non-negotiable)

1. User budget: **$0 billed**. Cloud execution remains blocked until the user verifies a provider-level spend limit of $0 after credits, and a conservative monthly usage budget below the compute allowance. A CLI confirmation flag alone is **not** account-level enforcement.
2. Modal worker: `min_containers=0`, `buffer_containers=0`, `max_containers=1`, short `scaledown_window`, bounded `timeout`, no automatic retries or always-on endpoints.
3. Explicit approval for a GPU run. Never trigger deploy or render from read-only diagnostics, bootstrapping, git hooks, or automated CI.
4. Local check: `modal container list`, `modal app list`, `modal billing summary`. Confirm no active containers and billed cost. A stopped application is not a stop failure.
5. The previously observed report showed zero active containers, the app stopped, $0.01 metered usage offset by $0.01 credits, and $0.00 billed. This was a point-in-time observation, **not** a future cost guarantee.
6. GPU runtime includes cold start, model loading, generation, and scale-down. Provider-controlled billing limits take precedence over application flags.
7. Do not enable Modal Model APIs (separate charges). Keep models self-hosted, credentials out of Git, and GPU snapshots off until benchmarked.

## Deployment progress and blockers

- Modal authentication was verified locally in workspace `justjerkinit247`.
- Headless ComfyUI image build completed in approximately 100 seconds; a subsequent deployment attempt returned a payment-method requirement for L40S access. Later an app appeared in stopped state. There is **no** evidence yet of a successful L40S model render.
- GTRG Modal guard v2 package has 22 passing offline unit tests. Tests exercise API graph validation, hash receipts, paths, and CLI guard flags, **not** production GPU behavior.
- Remote worker's ComfyUI polling timeout was found longer than its Modal function timeout; fix this mismatch before an actual render.
- Emergency-stop script should treat already-stopped apps as success while preserving real API-error checks.
- The exact current GPU `workflow_api.json` and its custom nodes/checkpoints still need an inventory before a full LTX run.

## First honest acceptance milestone

1. Sync the audited local Modal worker source and latest ASMO controller source to a non-main branch; include checksums and tests.
2. Preflight the user's actual API graph locally; separate any `AAO*` nodes from its render subgraph.
3. In Modal dashboard, verify hard zero-dollar out-of-pocket limit and remaining free compute allowance.
4. With explicit authorization, run a **small non-LTX ComfyUI canary**, download and hash-check its output, confirm zero containers after completion, and record the exact billed usage.
5. Download only the required official LTX weights into the remote model Volume using a CPU-only function.
6. Run a small quantized LTX I2V or A2V clip, record actual GPU/VRAM usage and duration, return media to local ASMO review.
7. Expand to music-driven short clips and batch orchestration after one complete measured render/review/retry loop.

## Model-aware design opportunities

- Official LTX-2.5 audio-to-video workflow holds input music/audio fixed and can use an optional first-frame image. Trim song into scene segments; ASMO should preserve sample-accurate original audio in the final edit.
- For character and prop continuity, investigate LTX IC-LoRA ingredient sheets, pose/depth/motion tracks, and anchored storyboards before generating long clips.
- Separate deterministic checks (durations, hashes, loudness, aspect, frame order) from visual-model judgments (gait, object presence, motion). Unknown evidence must not become an automatic pass.
- Preserve seed image, shot prompt, waveform offsets, model versions, LoRA identifiers, render parameters, output hash, and review result for each attempt. Retry only the failed segment.

References: https://docs.ltx.io/open-source-model/usage-guides/audio-to-video/ ; https://github.com/Lightricks/ComfyUI-LTXVideo/blob/master/example_workflows/2.5/README.md ; https://github.com/Comfy-Org/ComfyUI/blob/master/script_examples/websockets_api_example.py
