# GTRG: local genuine 51-frame output and initial cloud readiness

## Phase 1 — real local scene-length video

The saved scene contract (from the recorded `AAOFinishScene` error) is
**51 output frames**. The LTX latent temporal length should be **8n+1**:
use **57 real generated frames** and let the existing `AAOFinishScene` trim
to 51. This generates a genuine 51-frame final sequence with **no**
`RepeatImageBatch` node.

The local runner keeps its original **9-frame, 2-step** preview behavior as
default. `--render-frames 57 --expected-finish-frames 51` selects the
full-duration canary. It is still intentionally low resolution (**288x512**),
two sampling intervals, and batch size one.

```powershell
$repo = "$HOME\Documents\Audio-Analyze"
$script = "$repo\scripts\gtrg_tiny_ltx_local.py"
$comfy = "$HOME\Downloads\ComfyUI-Setup\ComfyUI_windows_portable\ComfyUI"
$api = "$HOME\Downloads\GTRG_LTX23_native_api_local_checked.json"
$report = "$repo\outputs\gtrg_local_smoke\gtrg_full_51frame_result.json"
$python = "$repo\.venv\Scripts\python.exe"
if (!(Test-Path $python)) {
    $python = "$HOME\Downloads\ComfyUI-Setup\ComfyUI_windows_portable\python_embeded\python.exe"
}

$options = @(
    "--api", $api,
    "--comfy-root", $comfy,
    "--report", $report,
    "--render-frames", "57",
    "--expected-finish-frames", "51",
    "--max-runtime-seconds", "7200"
)
& $python $script @options
if ($LASTEXITCODE -ne 0) { throw "Preflight failed. No render started." }
& $python $script @options --run
if ($LASTEXITCODE -ne 0) { throw "Full 51-frame canary failed. Read ComfyUI log." }
& $python "$repo\scripts\verify_gtrg_local_output.py" --report $report
if ($LASTEXITCODE -ne 0) { throw "MP4 stream/frame verification failed. Read the verification JSON." }
```

Requires local `ollama`, the corrected exported API workflow, and local
ComfyUI. A different plan might have a different finishing frame count:
**re-confirm before use**. No output or model weights belong in Git.
The verifier writes a separate `gtrg_full_51frame_result.verification.json`
sidecar and checks that the MP4 is probeable, has exactly one 288x512 video
stream with 51 decoded frames, and contains an audio stream. It does not
confirm subjective playback, identify the soundtrack, or measure sync.
`ffprobe` must be on `PATH` or supplied with `--ffprobe`.

## Phase 2 — first paid cloud compute readiness check

This is an isolated one-call GPU probe, **not yet GTRG/ComfyUI cloud video
generation**. It checks whether a Modal A100-80GB container can start and
report its GPU. No local media, prompts, weights or API graphs leave the PC.

1. Review current Modal pricing and set a Workspace budget/spend limit under
   Usage & Billing before running any paid GPU code.
2. Install Modal's CLI and authenticate interactively.
3. Run without the flag first, then explicitly opt in with `--run-cloud`.

```powershell
$repo = "$HOME\Documents\Audio-Analyze"
$python = "$repo\.venv\Scripts\python.exe"
if (!(Test-Path $python)) {
    $python = "$HOME\Downloads\ComfyUI-Setup\ComfyUI_windows_portable\python_embeded\python.exe"
}
& $python -m pip install --upgrade modal
& $python -m modal setup
Push-Location $repo
try {
    & $python -m modal run scripts/gtrg_modal_gpu_canary.py
    # Separate explicit user decision to spend credits:
    # & $python -m modal run scripts/gtrg_modal_gpu_canary.py --run-cloud
} finally {
    Pop-Location
}
```

A100-80GB base GPU is **$0.000694 per second** at Modal's Nov 2026 published
rate, excluding CPU, RAM, network and storage. A 90s GPU invocation would
be about $0.063 GPU-only, not a fixed billing ceiling. The 90s function
timeout does **not** impose a total cloud account cost cap.

After the readiness probe, a separate engineering milestone will package
ComfyUI, custom GTRG nodes, the checkpoint and text encoder, a secure media
transfer path, and the actual remote LTX-2.3 execution and MP4 retrieval.
Do not claim the readiness check is cloud rendering.
