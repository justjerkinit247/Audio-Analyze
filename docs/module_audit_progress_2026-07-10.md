# Python Module Audit Progress

Date: 2026-07-10

Repository: `justjerkinit247/Audio-Analyze`

Branch: `audit/repo-cleanup-2026-07-10`

This is an incremental, behavior-preserving audit. No changes are being made directly to `main`, and no runtime module is being deleted without complete dependency and external-usage evidence.

## Baseline

The older `codex/repo-hygiene-audit` branch contains `docs/module_audit_report.md`, which provides a useful historical inventory from 2026-06-12. That report predates the current filename-expansion, fresh-run, tap-sync, prompt-budget, choreography-profile, and one-command-live-run layers, so current files are being re-read rather than accepting the old classifications unchanged.

## Current modules inspected

| Module | Current responsibility | Classification | Audit finding |
|---|---|---|---|
| `ltx_choreography_profiles.py` | Loads, validates, selects, and renders structured choreography profiles. | KEEP_SEPARATE_CRITICAL | Clear policy/config boundary. Do not merge into audio analysis or launcher code. |
| `tap_accent_sync.py` | Detects high-frequency tap accents, selects timing targets, applies choreography policy, and inserts tap-sync prompt sections. | KEEP_SEPARATE_CRITICAL | Core audio-evidence layer. Public compatibility helpers should remain. Negative-term normalization is duplicated elsewhere. |
| `ltx_plan_prompt_expander.py` | Expands filename direction, protects visible subject count, builds audio-timing metadata, and composes the structured scene prompt. | KEEP_SEPARATE_CRITICAL | Distinct prompt-composition role. Its negative-term merge helper duplicates logic in other modules. |
| `ltx_live_run.py` | Interactive one-command launcher, Ollama startup/model check, dry-plan validation, preview, confirmation, submission, and result display. | KEEP_ENTRY_POINT | Large controller, but its responsibilities belong at the application boundary. Do not merge with core modules. |
| `ltx_prompt_budget.py` | Reconstructs and compacts the final prompt while preserving markers, timing, choreography, foreground onset, and critical negatives. | KEEP_SEPARATE_CRITICAL | Final mutation/safety layer. Contains a role-specific pair sentence that can conflict with the newer role-neutral subject policy and should be corrected in a narrowly tested change. |
| `asmo_negative_prompt_memory.py` | Learns negative terms from feedback, persists memory/ledger data, ranks terms, and applies them to future plans. | KEEP_SEPARATE_CRITICAL | Stateful learning layer. Its `normalize_term`, `unique_terms`, and comma-list merge behavior overlap with other prompt modules. |
| `ltx_auto_audio_orchestrator.py` | Fresh-run identity, plan isolation, old-orchestrator wrapping, filename expansion, ASMO memory, tap sync, preflight and submission routing. | KEEP_ORCHESTRATOR | Central integration boundary. Dynamic imports and temporary monkey-patching preserve the legacy path, but the patching is process-global and not thread-safe; acceptable for the current single-run CLI, not for concurrent service use. |
| `local_ai_client.py` | Ollama configuration, JSON/text chat calls, response parsing, and health checks. | KEEP_TESTED_CLIENT | Clean provider boundary. JSON extraction uses a greedy brace regex as fallback; improve only with dedicated malformed-output tests. |
| `ltx_filename_hint_expander.py` | Cleans filename hints, builds deterministic/openai/ollama expansions, normalizes model output, and renders motion/negative sections. | KEEP_SEPARATE_CRITICAL | Correct provider/fallback boundary. Contains another independent negative-term deduplication path. |
| `path_policy.py` | Resolves runtime paths, serializes repo-relative paths, describes paths, and validates portable JSON configuration. | KEEP_FOUNDATION | Foundational utility used across runtime modules. Existing historical test failures are policy-expectation mismatches, not evidence this module is obsolete. |

## Confirmed consolidation candidate

### Shared negative-prompt term utility

Equivalent or substantially overlapping whitespace normalization, case-insensitive deduplication, and comma-separated reconstruction currently exists in at least:

- `tap_accent_sync.merge_negative_prompt_terms`
- `ltx_plan_prompt_expander._merge_negative_terms`
- `asmo_negative_prompt_memory.normalize_term` / `unique_terms` / `merge_negative_prompt`
- `ltx_filename_hint_expander.build_negative_prompt`
- `ltx_prompt_budget._negative_terms`

Safe consolidation shape:

1. Add one small dependency-free utility module for term cleanup and stable case-insensitive deduplication.
2. Keep existing public functions as compatibility wrappers.
3. Preserve each caller's formatting contract, including marker placement and trailing newline behavior.
4. Add equivalence tests before changing imports.
5. Do not combine the owning modules; only centralize the repeated primitive.

## High-priority correctness finding

`ltx_plan_prompt_expander.py` now uses role-neutral subject preservation based on the seed layout. However, `ltx_prompt_budget._compact_subject_lock()` still emits:

`Keep the female lead dancer and male dance partner visible together throughout the complete clip.`

That sentence can reintroduce fixed gender/role assumptions during the final compaction stage even when the structured subject policy is intentionally role-neutral. Recommended narrow correction:

`Keep both visible foreground subjects together throughout the complete clip.`

This should be covered by tests proving that pair preservation remains intact and that no fixed female/male wording is introduced by compaction.

## Other findings

- Marker constants such as `[MOTION_PROMPT]` and `[NEGATIVE_PROMPT]` are duplicated across modules. Centralizing them is lower priority because a constants module would add coupling without eliminating meaningful behavior.
- Small tokenization helpers are duplicated, but they are local and readable. Do not create a generic utility merely to remove a few lines.
- JSON read/write helpers differ in path-policy and persistence semantics. Do not consolidate them until their contracts are proven identical.
- `ltx_auto_audio_orchestrator` and `ltx_live_run` must remain separate: one integrates the pipeline; the other provides the interactive user boundary.
- No inspected runtime module is currently safe to delete.

## Next audit batch

- `ltx_holy_cheeks_pipeline.py`
- `ltx_orchestrator.py`
- `ltx_client.py`
- `ltx_clip_assembler.py`
- `ltx_submit_resilient.py`
- `ltx_next_scene_planner.py`
- `ltx_intelligence_loop.py`
- `ltx_run_state.py`
- `ltx_feedback_analyzer.py`
- `ltx_policy_store.py`
- ASMO engine package modules

## Change policy

Low-risk consolidations may be committed to this audit branch without additional approval when they preserve public names, serialized output, prompt text contracts, timing behavior, fresh-run safety, and dry/live submission safeguards. Deletions, architecture changes, output-schema changes, and changes to `main` require separate review.
