# Repo Branch Prune Report

Date: 2026-06-12

Repository: `justjerkinit247/Audio-Analyze`
Base branch inspected: `origin/main` at `3c38b922f5cc7b088ebb0ecf8d60ee9b2edf16af`

## Commands Run

```bash
git fetch --all --prune
git branch -r --merged origin/main
git branch -r --no-merged origin/main
git rev-list --left-right --count origin/main...origin/<branch>
```

The original handoff mentioned `ltx-scene-control-layer`; that remote ref is no longer present in this checkout after `git fetch --all --prune`, so no deletion command is listed for it.

## Branch Classification

| Branch | Merged into `origin/main`? | Ahead | Behind | Status | Notes |
|---|---:|---:|---:|---|---|
| `main` | yes | 0 | 0 | KEEP_ACTIVE | Default branch. |
| `feature/ltx-filename-hint-expander` | no | 11 | 10 | KEEP_ACTIVE | Open draft PR #45. Do not delete. |
| `repo-prune-audit-20260612` | no | 16 | 0 | KEEP_ACTIVE | Open PR #46. Can be closed after this audit PR supersedes its backup-tree deletion, or merged first if preferred. |
| `ai-visual-analysis-v1` | yes | 0 | 26 | SAFE_DELETE_MERGED | Fully merged into `origin/main`. |
| `fix/true-asmo-intelligence-loop` | yes | 0 | 19 | SAFE_DELETE_MERGED | Fully merged into `origin/main`; PR #44 merged. |
| `lyric-audio-motion-sync-v1` | yes | 0 | 42 | SAFE_DELETE_MERGED | Fully merged into `origin/main`; PR #40 merged. Workflow trigger was updated away from this branch in this cleanup. |
| `vocal-profile-prototype-v2` | yes | 0 | 172 | SAFE_DELETE_MERGED | Fully merged into `origin/main`. |
| `wrapper-and-style-modes-v2` | yes | 0 | 146 | SAFE_DELETE_MERGED | Fully merged into `origin/main`. |
| `cleanup/remove-duplicate-generated-files` | no | 2 | 26 | NEEDS_HUMAN_REVIEW | Not merged into `origin/main`; verify owner/use before deletion. |
| `connector-test-20260322` | no | 1 | 174 | NEEDS_HUMAN_REVIEW | Not merged into `origin/main`; likely old, but still has one commit ahead. |
| `hotfix-plan-validation-v1` | no | 2 | 27 | NEEDS_HUMAN_REVIEW | PR #42 is merged, but this branch head is still not merged into current `main`; inspect before deleting. |
| `local-safety-checkpoint-20260523-221714` | no | 1 | 25 | NEEDS_HUMAN_REVIEW | Local checkpoint naming suggests manual review before deletion. |
| `ltx-asmo-integrated-intelligence-v1` | no | 19 | 40 | NEEDS_HUMAN_REVIEW | PR #41 is merged, but this branch head is not merged into current `main`; inspect before deleting. |
| `ltx-asmo-learning-loop-v1` | no | 9 | 40 | NEEDS_HUMAN_REVIEW | Not merged into current `main`; may have been partially superseded by PR #41. |
| `ltx-asmo-memory-bank-v1` | no | 6 | 40 | NEEDS_HUMAN_REVIEW | Not merged into current `main`; may have been partially superseded by PR #41. |
| `ltx-audio-analysis-upgrade-v1` | no | 3 | 40 | NEEDS_HUMAN_REVIEW | Not merged into current `main`; may have been partially superseded by PR #41. |
| `revert-10-main` | no | 1 | 130 | NEEDS_HUMAN_REVIEW | Old revert branch with one commit ahead; inspect before deletion. |

## Manual Deletion Commands

Run these only after confirming no local workstation depends on the branches:

```bash
git push origin --delete ai-visual-analysis-v1
git push origin --delete fix/true-asmo-intelligence-loop
git push origin --delete lyric-audio-motion-sync-v1
git push origin --delete vocal-profile-prototype-v2
git push origin --delete wrapper-and-style-modes-v2
```

After either PR #46 or this audit PR lands, also delete the cleanup branch:

```bash
git push origin --delete repo-prune-audit-20260612
```

Do not delete `feature/ltx-filename-hint-expander` while PR #45 is open.

## Workflow References

Stale workflow branch references found and fixed in this cleanup:

- `.github/workflows/asmo-smoke-test.yml` pushed only on `lyric-audio-motion-sync-v1`; changed to `main`.
- `.github/workflows/ltx-smoke-test.yml` pushed on `ltx-orchestrator-v1`, which is not present in current remote refs; removed that stale branch trigger and kept `main`.
