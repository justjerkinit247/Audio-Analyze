# Module Audit Report

Date: 2026-06-12

Repository: `justjerkinit247/Audio-Analyze`
Base branch inspected: `origin/main` at `3c38b922f5cc7b088ebb0ecf8d60ee9b2edf16af`

## Scope

This audit inspected Python modules under `src/audio_analyze/`, tests under `tests/`, workflow branch triggers, tracked local artifacts, and current test results. Runtime modules were not deleted in this PR; deletion candidates are documented for a follow-up PR after external usage and docs references are checked.

## Validation Results

```bash
.venv\Scripts\python.exe -m compileall src tests
# passed

.venv\Scripts\python.exe -m pytest -q --basetemp .pytest_tmp
# 61 passed, 8 failed, 2 warnings
```

The first pytest attempt without `--basetemp` failed because pytest tried to use `C:\Users\Tt-rexX\AppData\Local\Temp\pytest-of-Tt-rexX`, which was not readable in this session. Rerunning with a workspace temp directory exposed the real test failures below.

### Full Suite Failures

| Test | Failure Summary | Recommendation |
|---|---|---|
| `tests/test_ltx_holy_cheeks_pipeline_smoke.py::test_ltx_plan_preflight_and_dry_run_submit` | Expected absolute Windows path, got repo-relative `.pytest_tmp/...` path. | Align path policy/tests: either assert portable repo-relative paths or preserve absolute runtime fields separately. |
| `tests/test_ltx_seed_mapping_enforcement.py::test_build_plan_prefers_explicit_scene_labels_over_sort_order` | Expected absolute seed path, got repo-relative `.pytest_tmp_ltx/...` path. | Same path policy mismatch as above. |
| `tests/test_ltx_seed_mapping_enforcement.py::test_missing_seed_mapping_fails` | Error text contains repo-relative path instead of absolute path. | Decide whether diagnostics should show resolved absolute paths or portable paths. |
| `tests/test_ltx_seed_mapping_enforcement.py::test_mapped_seed_file_missing_fails` | Missing-seed diagnostic does not contain expected absolute path. | Same path policy mismatch. |
| `tests/test_ltx_seed_mapping_enforcement.py::test_accidental_duplicate_seed_usage_is_detected` | Duplicate seed report uses repo-relative path, test expects absolute path. | Same path policy mismatch. |
| `tests/test_ltx_seed_mapping_enforcement.py::test_sorted_order_fallback_is_rejected_before_live_submit` | Preflight error uses repo-relative path, test expects absolute path. | Same path policy mismatch. |
| `tests/test_ltx_seed_mapping_enforcement.py::test_extra_unmapped_seed_images_are_reported_as_warnings` | Extra seed report uses repo-relative path, test expects absolute path. | Same path policy mismatch. |
| `tests/test_root_pipeline_hard_stop.py::test_complete_with_failures_does_not_allow_root_success` | Test fake orchestrator lacks `build_plan`, but `configure_scene_specific_plan_export()` now requires it. | Update the fake orchestrator or guard `configure_scene_specific_plan_export()` for orchestrators without `build_plan`. |

### Targeted Suites

```bash
.venv\Scripts\python.exe -m pytest -q tests/test_*ltx*.py --basetemp .pytest_tmp_ltx
# PowerShell-expanded equivalent: 43 passed, 7 failed, 2 warnings

.venv\Scripts\python.exe -m pytest -q tests/test_*asmo*.py --basetemp .pytest_tmp_asmo
# 1 passed

.venv\Scripts\python.exe -m pytest -q tests/test_*runway*.py --basetemp .pytest_tmp_runway
# 1 passed

.venv\Scripts\python.exe -m pytest -q tests/test_*prompt*.py --basetemp .pytest_tmp_prompt
# 3 passed

.venv\Scripts\python.exe -m pytest -q tests/test_*batch*.py --basetemp .pytest_tmp_batch
# 2 passed, 2 warnings
```

On Windows PowerShell, the Unix-style globs from the handoff had to be expanded with `Get-ChildItem`; otherwise pytest treated `tests/test_*ltx*.py` as a literal path.

## Cleanup Performed

Deleted tracked backup/generated-output artifacts:

- `.asmo_backups/20260513_065330/` timestamped duplicate ASMO backup tree, 16 tracked files.
- `local_backups/main_LOCAL_BACKUP_20260509_081057.py`.
- `outputs/batch_run/json/*.json`, 2 generated analysis files.
- `outputs/batch_run/plots/**/*.png`, 4 generated plot files.

Kept despite looking stale:

- `inputs/runway_seed_images/*.png`: ignored by policy and likely user/demo media, but left for a separate owner decision because this PR keeps media deletion scope small.
- `inputs/prompts/club_confetti_ltx_*`: ignored by policy but may be reusable sample prompt/config material; left for separate review.
- Runtime modules marked `DELETE_CANDIDATE`: not removed because no deletion was proved safe across CLI/docs/external use.

## Module Inventory

| Module | Imported by runtime | CLI? | Direct test coverage | Output produced | Status | Recommendation |
|---|---|---:|---|---|---|---|
| `__init__` | - | no | `test_ltx_live_submit_validation.py`, `test_ltx_seed_mapping_enforcement.py` | none observed | KEEP_RUNTIME | keep |
| `analyzer` | `batch`, `batch_main`, `main`, `pipeline_batch` | no | `test_smoke.py` | library data/helpers | KEEP_TESTED_UTILITY | keep; covered by tests; UTF-8 BOM present |
| `asmo_engine.__init__` | - | no | `test_ltx_live_submit_validation.py`, `test_ltx_seed_mapping_enforcement.py` | none observed | KEEP_RUNTIME | keep |
| `asmo_engine.asmo_engine` | `asmo_engine.__init__`, `asmo_engine.cli`, `asmo_engine.ltx_run_integrator` | no | `test_asmo_engine_smoke.py`, `test_ltx_learning_loop_smoke.py` | library data/helpers | KEEP_TESTED_UTILITY | keep; covered by tests |
| `asmo_engine.audio_fingerprint_engine` | `asmo_engine.asmo_engine` | no | - | library data/helpers | NEEDS_TEST | add smoke coverage or document as ASMO dependency |
| `asmo_engine.beat_grid_engine` | `asmo_engine.asmo_engine` | no | - | library data/helpers | NEEDS_TEST | add direct smoke coverage |
| `asmo_engine.camera_inertia_engine` | `asmo_engine.asmo_engine` | no | - | library data/helpers | NEEDS_TEST | add direct smoke coverage |
| `asmo_engine.cli` | - | yes | - | runtime/structured output | NEEDS_TEST | add CLI smoke coverage |
| `asmo_engine.feedback_adapter` | - | yes | `test_ltx_learning_loop_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `asmo_engine.ltx_prompt_injector` | `asmo_engine.ltx_run_integrator` | no | - | library data/helpers | NEEDS_TEST | add direct prompt injection smoke coverage |
| `asmo_engine.ltx_run_integrator` | - | no | - | none observed | DELETE_CANDIDATE | review for deletion or wire into true-ASMO issue #43 path |
| `asmo_engine.lyric_loader` | `asmo_engine.asmo_engine` | no | - | library data/helpers | NEEDS_TEST | add parser smoke coverage |
| `asmo_engine.motion_ontology` | `asmo_engine.asmo_engine` | no | - | library data/helpers | NEEDS_TEST | add ontology mapping smoke coverage |
| `asmo_engine.motion_vector_engine` | `asmo_engine.asmo_engine` | no | - | library data/helpers | NEEDS_TEST | add motion vector smoke coverage |
| `asmo_engine.timecode` | `asmo_engine.asmo_engine`, `asmo_engine.lyric_loader` | no | - | library data/helpers | NEEDS_TEST | add unit coverage for parsing/formatting |
| `asmo_engine.timeline_exporter` | - | no | - | none observed | DELETE_CANDIDATE | review for deletion after docs/external usage check |
| `asmo_memory_bank` | `ltx_intelligence_loop` | yes | - | runtime/structured output | NEEDS_TEST | add memory bank CLI/unit smoke coverage |
| `asmo_sync_calibrator` | - | yes | - | runtime/structured output | NEEDS_TEST | add calibrator smoke coverage with synthetic data |
| `audio_analysis_upgrade` | `ltx_intelligence_loop` | yes | - | runtime/structured output | NEEDS_TEST | add synthetic audio smoke coverage |
| `batch` | `batch_main` | no | `test_batch_smoke.py` | library data/helpers | KEEP_TESTED_UTILITY | keep; covered by tests |
| `batch_main` | - | yes | - | runtime/structured output | NEEDS_TEST | add CLI smoke coverage |
| `beat_cut_engine` | - | yes | - | runtime/structured output | NEEDS_TEST | add beat-grid smoke coverage; UTF-8 BOM present |
| `beat_ready_runway_builder` | - | yes | - | runtime/structured output | NEEDS_TEST | add smoke coverage; UTF-8 BOM present |
| `clip_plan_export` | `asmo_sync_calibrator` | no | - | library data/helpers | NEEDS_TEST | add JSON export smoke coverage |
| `creative_prompt_compiler` | `workflow_wrapper` | yes | `test_creative_prompt_compiler_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `full_sync_stitcher` | - | yes | - | runtime/structured output | NEEDS_TEST | add stitcher smoke coverage |
| `holy_cheeks_stage_pipeline` | - | yes | - | runtime/structured output | NEEDS_TEST | add smoke coverage or deprecate if superseded |
| `image_integration` | `multi_clip_generator`, `runway_video_compiler` | no | - | library data/helpers | NEEDS_TEST | add image selection smoke coverage |
| `ltx_assemble_state` | - | yes | - | runtime/structured output | NEEDS_TEST | add state-aware assembler CLI smoke coverage |
| `ltx_beat_align_plan` | - | yes | - | runtime/structured output | NEEDS_TEST | add plan beat alignment smoke coverage |
| `ltx_client` | `ltx_holy_cheeks_pipeline` | no | - | library data/helpers | NEEDS_TEST | add mocked client coverage, no live API calls |
| `ltx_clip_assembler` | `ltx_assemble_state` | yes | `test_ltx_assembler_plan_timing.py`, `test_ltx_assembler_sync_controls.py`, `test_ltx_clip_assembler_options.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_control_prep` | - | yes | `test_ltx_control_prep_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_feature_extractor` | `ltx_feedback_analyzer`, `ltx_intelligence_loop` | yes | - | runtime/structured output | NEEDS_TEST | add feature extraction smoke coverage |
| `ltx_feedback_analyzer` | `ltx_intelligence_loop` | yes | `test_ltx_learning_loop_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_ffmpeg_assembler` | - | yes | `test_ltx_ffmpeg_assembler_hard_stop.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_holy_cheeks_pipeline` | `ltx_control_prep`, `ltx_live_session`, `ltx_orchestrator`, `ltx_submit_resilient`, `music_video_pipeline` | yes | `test_ltx_holy_cheeks_pipeline_smoke.py`, `test_ltx_live_submit_validation.py`, `test_ltx_seed_mapping_enforcement.py`, `test_path_policy.py` | runtime/structured output | KEEP_RUNTIME | keep; current failures are path-policy expectation mismatches |
| `ltx_intelligence_loop` | - | yes | `test_ltx_integrated_intelligence_loop_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_live_session` | - | yes | - | runtime/structured output | NEEDS_TEST | add live-session wrapper smoke coverage with fake submitter |
| `ltx_next_scene_planner` | `ltx_intelligence_loop` | yes | - | runtime/structured output | NEEDS_TEST | add planner smoke coverage |
| `ltx_orchestrator` | - | yes | - | runtime/structured output | NEEDS_TEST | add orchestrator smoke coverage |
| `ltx_policy_store` | `ltx_feedback_analyzer`, `ltx_intelligence_loop` | yes | `test_ltx_learning_loop_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_prompt_maximizer` | `ltx_control_prep` | yes | `test_ltx_prompt_maximizer_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_run_state` | `ltx_assemble_state`, `ltx_live_session` | yes | `test_ltx_integrated_intelligence_loop_smoke.py`, `test_ltx_learning_loop_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_seed_mapper` | `ltx_control_prep`, `ltx_holy_cheeks_pipeline` | yes | `test_ltx_preview_maximized_smoke.py`, `test_ltx_seed_mapper_smoke.py`, `test_ltx_seed_mapping_enforcement.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_strategy_scorer` | `ltx_intelligence_loop` | yes | - | runtime/structured output | NEEDS_TEST | add scorer smoke coverage |
| `ltx_submit_resilient` | - | yes | `test_ltx_submit_resilient_stale_reuse.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `ltx_visual_critic` | `ltx_intelligence_loop` | yes | - | runtime/structured output | NEEDS_TEST | add visual critic smoke coverage with local sample metadata only |
| `main` | - | yes | - | runtime/structured output | NEEDS_TEST | add package CLI smoke coverage |
| `mid_song_reel_builder` | - | yes | - | runtime/structured output | NEEDS_TEST | add smoke coverage; UTF-8 BOM present |
| `multi_clip_generator` | `runway_video_compiler` | no | - | library data/helpers | NEEDS_TEST | add clip generation smoke coverage |
| `music_video_pipeline` | - | yes | - | runtime/structured output | NEEDS_TEST | add wrapper CLI smoke coverage |
| `path_policy` | `asmo_sync_calibrator`, `clip_plan_export`, `ltx_control_prep`, `ltx_holy_cheeks_pipeline`, `ltx_orchestrator`, `ltx_seed_mapper`, `ltx_submit_resilient` | yes | `test_path_policy.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `pipeline_batch` | `workflow_wrapper` | yes | `test_pipeline_batch_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `plotting` | `batch` | no | - | library data/helpers | NEEDS_TEST | add plot-generation smoke coverage or keep as batch helper |
| `prompt_compiler` | `workflow_wrapper` | yes | `test_prompt_compiler_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `runway_live_test` | - | yes | - | runtime/structured output | NEEDS_TEST | add mocked live-test coverage or keep local-only |
| `runway_multi_clip_runner` | - | yes | - | runtime/structured output | NEEDS_TEST | add mocked runner coverage; UTF-8 BOM present |
| `runway_video_compiler` | `runway_workflow_wrapper` | yes | `test_runway_video_compiler_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `runway_workflow_wrapper` | - | yes | - | runtime/structured output | NEEDS_TEST | add wrapper smoke coverage |
| `style_mode_compiler` | `workflow_wrapper` | yes | `test_style_mode_compiler_smoke.py` | runtime/structured output | KEEP_RUNTIME | keep |
| `workflow_wrapper` | `runway_workflow_wrapper` | yes | - | runtime/structured output | NEEDS_TEST | add workflow wrapper smoke coverage |

## Summary Counts

- `KEEP_RUNTIME`: primary CLIs and runtime modules with active use.
- `KEEP_TESTED_UTILITY`: helper modules with direct tests.
- `NEEDS_TEST`: modules with runtime imports or CLI behavior but no direct smoke coverage.
- `DELETE_CANDIDATE`: `asmo_engine.ltx_run_integrator`, `asmo_engine.timeline_exporter`.

No runtime module was deleted in this cleanup PR.
