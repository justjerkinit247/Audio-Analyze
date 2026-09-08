# New Windows PC migration

This is the supported migration path for moving Audio-Analyze to another Windows PC without carrying forward a stale Python environment, cache data, old absolute paths, or secret files.

## What moves from GitHub

A normal clone restores the current source code, tests, wrappers, choreography profiles, and tracked project documentation.

Git intentionally does **not** restore local runtime media or generated state that is ignored by `.gitignore`, including source audio, LTX seed images, generated videos, local outputs, `.venv`, `.env`, `CacheClip`, and `.gallery`.

## Required runtime baseline

- Windows PowerShell
- Python 3.11
- repository dependencies from `requirements.txt`
- Ollama with `gemma3:4b` for the current local Gemma path
- NVIDIA driver/GPU support when GPU-backed Ollama execution is desired
- FFmpeg is preferred; the multi-scene stitcher can use its imageio-ffmpeg fallback when available

## Fresh clone

From PowerShell:

```powershell
Set-Location "$HOME\Documents"
New-Item -ItemType Directory -Force -Path "GitHub" | Out-Null
Set-Location "GitHub"
git clone https://github.com/justjerkinit247/Audio-Analyze.git
Set-Location "Audio-Analyze"
```

If the repository is already cloned, update it before setup:

```powershell
git switch main
git pull --ff-only
```

## Set up only the new machine

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\scripts\Setup-New-PC.ps1
```

The script:

1. requires Python 3.11;
2. creates or repairs `.venv`;
3. installs `requirements.txt`;
4. creates runtime input/output directories;
5. reports NVIDIA GPU visibility;
6. pulls `gemma3:4b` when Ollama is installed;
7. checks FFmpeg availability;
8. compiles `src` and `tests`;
9. runs the required targeted LTX/ASMO smoke tests;
10. never performs a live/paid LTX request.

If Python 3.11 is not installed, Windows Package Manager can install it with:

```powershell
winget install --id Python.Python.3.11 -e
```

If Ollama is not installed:

```powershell
winget install --id Ollama.Ollama -e
```

Then rerun the setup script.

## Migrate local project data from the old drive

Mount the old system drive or otherwise make the previous Audio-Analyze checkout accessible, then pass that checkout as `-OldRepoPath`:

```powershell
.\scripts\Setup-New-PC.ps1 -OldRepoPath "D:\path\to\old\Audio-Analyze"
```

The migration copies reusable local inputs while preserving files already present in the new checkout:

- `inputs/audio`
- `inputs/lyrics`
- `inputs/ltx_seed_images`
- `inputs/runway_seed_images`
- `inputs/driving_performance`
- `inputs/character_images`
- `inputs/lip_sync_audio`

It also restores the learned state that should survive a machine move:

- `outputs/ltx_video_run/_state/memory`
- `outputs/ltx_video_run/_state/policy`

Old `inputs/prompts` and `_state/active` data are retained under `outputs/migration_archive/<timestamp>/` rather than reactivated. This preserves history while preventing stale absolute paths and old run state from being treated as current.

### Preserve old generated outputs too

Generated videos and old output trees can be large, so they are optional:

```powershell
.\scripts\Setup-New-PC.ps1 `
    -OldRepoPath "D:\path\to\old\Audio-Analyze" `
    -CopyLegacyOutputs
```

Those files are placed under `outputs/migration_archive/<timestamp>/legacy_outputs` rather than mixed into fresh-run output state.

## What must not be copied

The migration intentionally does not transfer these into the active checkout:

- `.venv`
- `.git`
- `.env` and API-key/secret files
- `CacheClip`
- `.gallery`
- `__pycache__`

`.venv` must be rebuilt for the new machine. Cache/editor/NLE data is rebuildable and can contain machine-specific paths. Secrets must be re-established locally rather than copied or committed.

## Verify the migrated environment

Activate the Python 3.11 environment:

```powershell
. .\scripts\Activate-AudioAnalyze.ps1
```

Check the local model:

```powershell
ollama list
```

Run a safe interactive pipeline validation:

```powershell
.\run-ltx-live.cmd --dry-run
```

The dry run still asks for real audio, lyrics, and seed images and uses the local Ollama/Gemma path, but it does not submit a paid LTX generation.

## Live operation

The current live wrapper is:

```powershell
.\run-ltx-live.cmd
```

The pipeline builds and validates a fresh plan first. Paid submission occurs only after the operator explicitly types `LIVE`. The LTX API key is requested at that point if `LTXV_API_KEY` is not already present in the environment.
