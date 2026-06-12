# Codex workflow: LTX filename-hint motion prompt expander

## Goal
Add and verify a general-purpose LTX filename-hint expansion layer. The seed image file name is the source of truth for the scene hint. The image itself should not be analyzed. The module expands the filename scene hint into an LTX image-to-video motion prompt and writes cleanup/negative prompt terms into the same text file under a separate `[NEGATIVE_PROMPT]` section.

## Branch
Work on:

```text
feature/ltx-filename-hint-expander
```

Target base:

```text
main
```

## Existing implementation to review
Review:

```text
src/audio_analyze/ltx_filename_hint_expander.py
tests/test_ltx_filename_hint_expander.py
```

## Required behavior
The module must support this flow:

```text
seed image filename
  -> clean scene hint from filename
  -> expand scene hint into LTX motion prompt
  -> build negative prompt / cleanup terms
  -> write one combined _ltx.txt file
  -> optionally inject combined prompt sections into an existing LTX plan JSON before preflight/submit
```

The combined text format must stay:

```text
[MOTION_PROMPT]
...

[NEGATIVE_PROMPT]
...
```

## Hard rules
- Do not analyze the actual image.
- Use the filename scene hint as the creative source of truth.
- Keep the module general-purpose and project-neutral.
- Do not remove project-specific words like `gospel`, `holy`, `duck`, `club`, etc. unless they are technical filename junk.
- Do not import assumptions from prior songs, genres, or projects.
- Negative prompt terms belong in the same `_ltx.txt` file, under `[NEGATIVE_PROMPT]`.
- The OpenAI provider must remain optional. The template provider must work without network access or API keys.
- Do not add local media files to Git.

## Testing commands
Run:

```bash
pytest -q tests/test_ltx_filename_hint_expander.py
```

Then run the full available test suite if dependencies are installed:

```bash
pytest -q
```

Manual smoke test:

```bash
PYTHONPATH=src python -m audio_analyze.ltx_filename_hint_expander single scene_01_duck_flies_off_keyhole_to_ocean_clouds.png
```

Expected smoke-test output must include both:

```text
[MOTION_PROMPT]
[NEGATIVE_PROMPT]
```

## Optional integration improvement
If safe, wire this into the main LTX pipeline behind explicit flags only, for example:

```text
--expand-filename-hints
--filename-hint-provider template|openai
--filename-hint-replace-prompt
--filename-hint-output-dir inputs/prompts/ltx_filename_hints
```

The expansion should run after the plan is built and before preflight/submit. It should rewrite the run-specific plan JSON with `filename_hint_expander` metadata and each scene's `filename_hint_expansion` data.

## Acceptance criteria
- Existing behavior is unchanged unless the new expander is explicitly invoked.
- The standalone module works from CLI.
- The module can write per-seed `_ltx.txt` and `_ltx.json` files.
- The module can inject the combined prompt sections into a plan JSON.
- Tests pass.
