# Local Ollama provider MVP

This workflow uses a local Ollama model as an optional provider for the LTX filename-hint expander.

The seed image itself is not uploaded or inspected. The filename scene hint remains the source of truth.

## Requirements

- Windows PowerShell or any shell that can run Python
- Ollama running locally
- Model pulled locally, for example `gemma3:4b`
- Repo dependencies installed from `requirements.txt`

## Pull the model

```powershell
ollama pull gemma3:4b
```

## Single filename smoke test

From the repo root:

```powershell
$env:PYTHONPATH = "src"
python -m audio_analyze.ltx_filename_hint_expander single "scene_01_duck_flies_off_keyhole_to_ocean_clouds.png" --provider ollama --model "gemma3:4b"
```

Expected output includes:

```text
[MOTION_PROMPT]
[NEGATIVE_PROMPT]
```

## Expand a seed-image folder

```powershell
$env:PYTHONPATH = "src"
python -m audio_analyze.ltx_filename_hint_expander expand-dir --provider ollama --model "gemma3:4b" --seed-dir "inputs\ltx_seed_images" --output-dir "inputs\prompts\ltx_filename_hints"
```

This writes matching files:

```text
*_ltx.txt
*_ltx.json
```

## Apply expansions to an existing LTX plan

```powershell
$env:PYTHONPATH = "src"
python -m audio_analyze.ltx_filename_hint_expander apply-plan --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" --provider ollama --model "gemma3:4b"
```

## Windows convenience wrapper

The wrapper now calls the real Python module directly:

```powershell
.\scripts\Run-LtxFilenameHintExpanderOllama.ps1 -Model "gemma3:4b"
```

Optional single file:

```powershell
.\scripts\Run-LtxFilenameHintExpanderOllama.ps1 -Filename "scene_01_duck_flies_off_keyhole_to_ocean_clouds.png" -Model "gemma3:4b"
```

## Environment overrides

```powershell
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "gemma3:4b"
$env:LOCAL_AI_TIMEOUT_SECONDS = "240"
```

## Fallback behavior

If the local model returns malformed JSON, omits the expected prompt key, or is unavailable, the expander keeps deterministic fallback behavior instead of crashing downstream.

The result still records the provider as `ollama` and includes diagnostic motion notes when fallback is used.
