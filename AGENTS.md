# Audio-Analyze Codex Instructions

## Repository purpose

Audio-Analyze is a local-first Python pipeline for audio analysis, LTX/Runway prompt planning, ASMO motion synchronization, dry-run validation, and short-form video assembly.

## Environment

- Use Python 3.11.
- Install dependencies with `python -m pip install -r requirements.txt`.
- Set `PYTHONPATH=src` when invoking modules or tests from the repository root.
- Treat Windows PowerShell as the primary local operator environment, but keep Python and path handling portable across Windows and Linux CI.

## Required validation

For every Python change, run:

```bash
python -m compileall -q src tests
```

Run the narrowest relevant pytest files first. For changes affecting the current LTX/ASMO path, use:

```bash
python -m pytest -q \
  tests/test_asmo_engine_smoke.py \
  tests/test_ltx_auto_audio_orchestrator.py \
  tests/test_ltx_plan_prompt_expander.py \
  tests/test_ltx_filename_hint_expander.py \
  tests/test_ltx_filename_hint_expander_ollama.py \
  tests/test_local_ai_client.py \
  tests/test_asmo_negative_prompt_memory.py
```

Run the full suite with `python -m pytest -q` when a change is broad, shared, or alters orchestration, path policy, plan schemas, assembly, or root-pipeline status handling.

## Pipeline safety rules

- Never use `--live` in automated tests or default CI.
- Never spend LTX, OpenAI, Runway, or other external API credits during validation.
- Use deterministic template or mocked providers in CI; do not require a local Ollama server.
- Preserve hard-stop behavior before live submission, especially plan validation, seed mapping, media existence, model settings, and path policy checks.
- Do not weaken stale-output detection, partial-render safeguards, or failure propagation.
- Keep secrets in environment variables or GitHub Secrets. Never commit API keys, tokens, `.env` files, or secret-bearing logs.

## Current LTX baseline contract

The standard wrapper is `audio_analyze.ltx_auto_audio_orchestrator`.

Preserve these defaults unless a task explicitly changes the contract:

- newest supported audio is selected from `inputs/audio` when `--audio` is omitted;
- beat alignment is enabled by default;
- filename-hint expansion is integrated into the existing orchestrator build-plan path;
- ASMO negative-prompt memory is enabled by default;
- active scene prompts contain `[AUDIO_TIMING]`, `[MOTION_PROMPT]`, and `[NEGATIVE_PROMPT]` sections;
- dry runs remain the default and live submission requires an explicit `--live` flag.

Do not duplicate the existing orchestrator sequence in a new wrapper when a narrow integration point is available.

## Repository hygiene

- Do not commit generated media, pipeline outputs, cache files, editor/NLE databases, virtual environments, or machine-specific absolute paths.
- Keep `outputs/`, local input media, `.gallery/`, `CacheClip/`, and `*.pfl` artifacts out of source control.
- Avoid unrelated cleanup in feature changes. Separate large hygiene removals from runtime changes.
- Do not delete a runtime module merely because direct test coverage is missing; first check imports, CLI entry points, documentation, and external use.

## Review priorities

Treat these as high-severity findings:

1. A path that can trigger a paid/live API call without explicit operator intent.
2. Secret exposure or untrusted prompt/code receiving unnecessary credentials or network access.
3. A regression that allows an empty/invalid plan, missing seed, stale clip, failed scene, or partial render to be reported as successful.
4. Windows-only absolute paths or serialization changes that break portable execution.
5. Changes that silently remove `[AUDIO_TIMING]`, `[MOTION_PROMPT]`, `[NEGATIVE_PROMPT]`, beat alignment, or ASMO memory from the active plan.
6. Committed local media, cache, generated output, or workstation metadata.

Keep review comments specific: cite the file and behavior, explain the failure mode, and suggest the smallest safe correction.