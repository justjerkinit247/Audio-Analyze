# Python Module Audit — Batch 2

Date: 2026-07-10

Repository: `justjerkinit247/Audio-Analyze`

Branch: `audit/repo-cleanup-2026-07-10`

This batch continues the connector-based audit. It documents behavior and risks without changing `main` or deleting runtime modules.

## Modules inspected

| Module | Responsibility | Classification | Finding |
|---|---|---|---|
| `ltx_holy_cheeks_pipeline.py` | Legacy/core plan builder, audio analysis, scene construction, seed mapping, preflight, scene-audio export, and submission. | KEEP_CORE_LEGACY_BOUNDARY | Still imported by active orchestration and submission paths. It is broad, but splitting it now would be redesign. |
| `ltx_orchestrator.py` | Legacy orchestration, beat markers, continuity/choreography manifests, preflight and submission coordination. | KEEP_LEGACY_ORCHESTRATOR | Active fresh-run wrapper temporarily replaces its old beat-grid functions with the newer tap-accent implementation. Keep until direct and fallback usage is fully mapped. |
| `ltx_client.py` | LTX upload, URI resolution, generation request, response parsing, and MP4 download. | KEEP_SEPARATE_CLIENT | Clear network boundary. Add mocked tests before changing permissive response parsing or upload behavior. |
| `ltx_submit_resilient.py` | Retry handling, stale-output checks, clip fingerprints, metadata, and safe batch resubmission. | KEEP_SEPARATE_SAFETY_LAYER | Distinct from the HTTP client and plan builder. Its fingerprint currently identifies media by path, not file contents. |
| `ltx_clip_assembler.py` | Selects generated scene clips, normalizes duration, attaches audio, handles transitions, and writes the final assembly/report. | KEEP_SEPARATE_ASSEMBLER | Correct separate responsibility, but selection is based on scene number and modification time rather than validated generation fingerprints. |
| `ltx_next_scene_planner.py` | Applies feedback, strategy scores, memory directives, and learned negative terms to produce a next plan. | KEEP_LEARNING_PLANNER | Generic prompt compression collapses structured marker newlines and can weaken the marker contract used elsewhere. |
| `ltx_intelligence_loop.py` | Coordinates audio analysis, feature extraction, visual criticism, feedback, policy update, strategy scoring, memory update, and next-plan creation. | KEEP_COORDINATOR | Correct coordinator role, but some analysis is repeated by called modules. |
| `ltx_run_state.py` | Rotates active/previous state, stores manifests, ingests scene results, records assembly attempts, and reports state. | KEEP_STATE_FOUNDATION | Clear persistence boundary. Rotation behavior needs tests for an existing active directory that lacks a manifest. |
| `ltx_feedback_analyzer.py` | Converts extracted features and human scores into issues, adjustments, and feedback packets. | KEEP_BUT_CORRECT_EVIDENCE_POLICY | Default scores currently create negative findings when no human score exists. This can manufacture failure evidence. |
| `ltx_policy_store.py` | Persists strategy weights and learned adjustment values and updates them from feedback. | KEEP_POLICY_FOUNDATION | Its math is small and understandable, but it trusts feedback scores as evidence and therefore amplifies any fabricated defaults upstream. |

## High-priority correctness findings

### 1. Unscored scenes are treated as scored failures

`ltx_feedback_analyzer.analyze_feature()` substitutes defaults when human scores are absent:

- beat sync: `0.65`
- motion match: `0.65`
- camera match: `0.65`
- prompt obedience: `0.60`
- visual quality: `0.70`

Those defaults are below multiple failure thresholds. Consequently, a scene with no actual human score can be classified as weak beat sync, motion mismatch, camera mismatch, and low prompt obedience. `ltx_policy_store` can then update strategy weights from this synthetic evidence.

Recommended correction:

1. Preserve missing scores as `None` or mark them explicitly as estimated.
2. Do not issue evidence-based failures from an absent score.
3. Do not update policy weights unless a score has an identified evidence source.
4. Add tests for fully unscored, partially scored, and explicitly scored scenes.

### 2. Next-plan compression damages structured prompt markers

`ltx_next_scene_planner.compress_prompt()` collapses all whitespace before truncating. This turns marker blocks such as `[SUBJECT_LOCK]`, `[AUDIO_TIMING]`, `[TAP_SYNC]`, `[MOTION_PROMPT]`, and `[NEGATIVE_PROMPT]` into inline text. The prompt-budget parser elsewhere expects markers on their own lines.

Recommended correction:

- Use marker-aware compaction rather than generic whitespace collapse.
- Preserve all mandatory marker boundaries.
- Never truncate by blindly cutting through the negative-prompt section.
- Reuse the final prompt-budget contract where practical without merging the planner and budget modules.

### 3. Stale-output fingerprint does not hash media contents

`ltx_submit_resilient` fingerprints `source_audio_path` and `seed_image_used`, but not the bytes or a content digest of those files. Replacing audio or a seed image at the same path can leave the fingerprint unchanged and incorrectly mark an old MP4 reusable.

Recommended correction:

- Add deterministic media content hashes, preferably SHA-256, to the fingerprint payload.
- Store file size and modification metadata only as diagnostics, not as the identity proof.
- Version the fingerprint schema when this changes.
- Preserve backward behavior by treating old metadata as unverifiable rather than matched.

### 4. Assembler can select stale clips independently of fingerprint validation

`ltx_clip_assembler.select_latest_scene_clips()` selects the newest numbered MP4 by modification time. It does not verify that the chosen clip matches the active plan, seed, audio, prompt, model, or guidance settings.

Recommended correction:

- Prefer a validated submission/assembly manifest over directory scanning.
- When directory scanning is used, require matching clip metadata for strict mode.
- Report fingerprint-missing and fingerprint-mismatch clips rather than silently choosing them.

### 5. Legacy pipeline analyzes the same audio more than once

`ltx_holy_cheeks_pipeline.build_plan()` calls both `analyze_audio()` and `detect_beats()`, and both decode/load the source audio. This duplicates expensive work and can produce subtly different derived data if parameters diverge.

Recommended consolidation:

- One internal analysis pass should return audio features, duration, tempo, beat frames, and beat times.
- Keep the existing public helper names as wrappers for compatibility.
- Make this change only with audio-analysis and scene-boundary regression tests.

## Additional findings

- `ltx_holy_cheeks_pipeline.build_prompt()` remains project-specific and contains legacy lower-body choreography and kick/snare wording. The current fresh-run wrapper later replaces or restructures the prompt, but direct callers can still receive the legacy text. Do not delete or globally rewrite it until all direct callers are mapped.
- `ltx_orchestrator` retains the old fixed-limit beat-grid selection as a legacy/fallback path. The standard fresh-run flow replaces it with `tap_accent_sync`; this is intentional compatibility, not automatically dead code.
- `ltx_intelligence_loop` extracts features, then `build_feedback_packet()` extracts and writes them again. This is a safe performance-consolidation candidate after tests confirm both calls use identical state.
- Several modules implement local JSON read/write helpers. Their path handling and return contracts differ, so they are not yet safe to centralize.
- `ltx_clip_assembler` uses direct `Path` resolution rather than the repository path policy, making behavior dependent on the current working directory.
- `ltx_client` should eventually accept an injected HTTP session for deterministic mocked tests, but that is a testability improvement rather than module consolidation.
- No module in this batch is presently proven safe to delete.

## Next batch

- `ltx_feature_extractor.py`
- `ltx_visual_critic.py`
- `ltx_strategy_scorer.py`
- `asmo_memory_bank.py`
- `audio_analysis_upgrade.py`
- `ltx_assemble_state.py`
- `ltx_ffmpeg_assembler.py`
- `ltx_live_session.py`
- `ltx_seed_mapper.py`
- remaining ASMO engine package files
