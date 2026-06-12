# Quick repo hygiene smoke report

## Scope

This is a fast hygiene pass, not a full module audit.

The goal is to remove obvious repo noise, document quick checks, and avoid wasting time manually testing every module.

## Base state

- PR #46 was merged first.
- The duplicate `.asmo_backups/20260513_065330/` tree was already removed before this pass.
- Active branch `feature/ltx-filename-hint-expander` remains protected because PR #45 is still open/draft/active.

## Compile result

Not executed by this GitHub connector session.

Run locally or in CI:

```bash
python -m compileall src tests
```

## Pytest result

Not executed by this GitHub connector session.

Run locally or in CI:

```bash
python -m pytest -q
```

## Static checks performed

Repository search was used to check obvious stale artifact patterns:

- `.asmo_backups`
- `outputs/batch_run`
- stale local `C:\Users` path references
- `key.txt`

No matching code-search results were returned during this pass after PR #46 merged.

## Workflow findings

### Fixed: ASMO workflow stale branch trigger

`.github/workflows/asmo-smoke-test.yml` previously triggered push runs only for:

```text
lyric-audio-motion-sync-v1
```

That branch name is stale after the ASMO work was merged.

Changed push trigger to:

```text
main
```

### Fixed: LTX workflow stale branch trigger

`.github/workflows/ltx-smoke-test.yml` previously triggered push runs for:

```text
main
ltx-orchestrator-v1
```

The old feature branch trigger was removed. Push now targets:

```text
main
```

Pull requests into `main` still trigger both workflows.

## Suspicious files found

No obvious committed backup/output/local-path pollution was found by the fast static searches performed in this pass.

## Files safe to ignore for now

Runtime source modules were not changed in this pass.

Any module that is merely untested should not be deleted without a separate focused follow-up.

## Recommended deletes

No additional file deletes recommended in this PR.

## Recommended follow-up PRs

1. Native local AI/Ollama provider MVP from Issue #48.
2. Optional follow-up branch pruning after the user confirms no local workstation dependency.
3. Optional full module coverage audit only if recurring failures appear in CI.

## Manual branch deletion candidates to verify

Do not run these until local workstation dependency is confirmed.

```bash
git push origin --delete ltx-scene-control-layer
git push origin --delete fix/true-asmo-intelligence-loop
```

`feature/ltx-filename-hint-expander` must not be deleted while PR #45 remains open.
