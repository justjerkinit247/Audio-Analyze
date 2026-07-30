# Next Audit Correctness Fixes

Work remains on `audit/repo-cleanup-2026-07-10` and must stay off `main` until tested and reviewed.

## Next implementation order

1. Replace generic whitespace compression in `ltx_next_scene_planner.py` with marker-aware compaction.
2. Add SHA-256 source-media content identities to `ltx_submit_resilient.py` fingerprints and version the schema.
3. Require matching generation metadata/fingerprints during strict assembly in `ltx_clip_assembler.py`.
4. Correct role-specific pair wording introduced by `ltx_prompt_budget.py` final compaction.
5. Consolidate duplicate audio decoding in `ltx_holy_cheeks_pipeline.py` only after regression coverage exists.

## Required tests

- structured marker preservation through next-plan generation;
- negative section remains a standalone block;
- same path with changed media bytes produces a different fingerprint;
- old fingerprint metadata is treated as unverifiable, not matched;
- strict assembly rejects missing or mismatched metadata;
- pair subject lock remains role-neutral;
- consolidated audio analysis preserves tempo, beat times, duration, and scene boundaries.

## Merge gate

- targeted new tests pass;
- existing targeted LTX/ASMO suites pass;
- full test suite is run and unrelated pre-existing failures are separated from regressions;
- no paid or live generation is invoked by validation.
