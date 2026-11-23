# GTRG local LTX 2.3 canary: first exported MP4

## Status

**Local end-to-end export reached (operator-reported, November 2026).**
The local runner returned `PLAYABLE_FILE_NOT_YET_VERIFIED` and exit code `0`
after detecting an MP4 written by ComfyUI. This proves the runner found a
rendered file, **not** that playback, decoded quality, or soundtrack alignment
has been independently verified.

Source: operator-supplied PowerShell output from the first successful local
render attempt. The media file and machine-specific report remain local and
are intentionally not committed.

## Validated path and limits

- Local `ollama` planning and AudioAnalyze / ASMO render graph were used.
- Native **LTX 2.3** local diffusion sampled successfully for **two intervals**
  (earlier ComfyUI log reported `2/2` complete).
- Temporary test graph generated **9 latent video frames** at **288 × 512**,
  plus 9 latent audio frames where applicable.
- The production `AAOFinishScene` checks the original scene length:
  **51 frames** in this recorded test. Its original incomplete-render guard
  was **not disabled**.
- To exercise finishing with the cheap preview, the test runner inserted a
  verified `RepeatImageBatch` node **only in the submitted graph copy**:
  9 frames × 6 repetitions = 54 frames supplied, trimmed to 51 by
  `AAOFinishScene`.
- `CreateVideo` and `SaveVideo` completed sufficiently for the runner to
  detect an MP4 under the unique `GTRG_Tiny_9f_*` filename prefix.
- `--run` is still required for submission; a dry-run is the default.
  The runner targets the local ComfyUI API only. No paid GPU or video API was
  involved.
- The original exported workflow and soundtrack wiring were preserved.

This is a **pipeline / export canary**, **not** a full-motion 51-frame render:
most preview frames are repetitions of the original nine.

## Local-only reproduction

With ComfyUI listening on `http://127.0.0.1:8188`, `ollama` available, and
the corrected API-format workflow exported locally:

```powershell
$repo = "$HOME\Documents\Audio-Analyze"
$py = "$repo\.venv\Scripts\python.exe"
$comfy = "$HOME\Downloads\ComfyUI-Setup\ComfyUI_windows_portable\ComfyUI"
$api = "$HOME\Downloads\GTRG_LTX23_native_api_local_checked.json"
$report = "$repo\outputs\gtrg_local_smoke\gtrg_tiny_video_result.json"
$script = "$repo\scripts\gtrg_tiny_ltx_local.py"

$args = @(
    "--api", $api,
    "--comfy-root", $comfy,
    "--report", $report,
    "--expected-finish-frames", "51",
    "--max-runtime-seconds", "3600"
)

& $py $script @args  # preflight: no GPU render
if ($LASTEXITCODE -ne 0) { throw "Preflight failed; do not render." }
& $py $script @args --run  # one explicitly authorized local test
```

The corrected API export and local `ollama` setup are prerequisites.
If the repo virtual environment is absent, use the installed ComfyUI
Python interpreter. Never submit while another ComfyUI queue is active.

## Related source and CI

- `scripts/gtrg_tiny_ltx_local.py`
- `tests/test_gtrg_tiny_ltx_local.py`
- `.github/workflows/pipeline-validation.yml`
- Pull request [#97](https://github.com/justjerkinit247/Audio-Analyze/pull/97)
  added the preview frame adapter; all six PR checks passed before merging.

## Outstanding verification

1. Play the exported MP4 and confirm it decodes correctly.
2. Listen for original soundtrack presence and verify synchronization.
3. Confirm dimensions, duration, and frame rate with a media probe.
4. Later, generate **51 unique frames** for a proper motion-continuity test,
   without using the `RepeatImageBatch` preview adapter.
5. Improve local prompt-length handling without silently truncating key
   audio timing or motion instructions.

Do not add generated MP4s, audio, local reports, caches, paths, or credentials
to Git. Record reproducible configuration and test evidence only.
