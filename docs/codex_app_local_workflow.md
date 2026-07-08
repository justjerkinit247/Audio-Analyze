# Local Codex app workflow

Use the Codex desktop app with the repository owner's ChatGPT account. This workflow does not require an OpenAI API key or API billing.

## One-time setup

1. Open the Codex app and sign in with the ChatGPT account that includes Codex.
2. Select the local `Audio-Analyze` repository folder as the project.
3. Select **Local** in the composer when working directly in the current checkout.
4. Keep sandbox permissions set to **Default permissions**. Do not use full-access mode for routine repository work.
5. Use PowerShell as the integrated terminal on Windows.
6. Optionally install GitHub CLI and authenticate it:

```powershell
gh auth login
```

Authenticated GitHub CLI access lets the Codex app show pull-request context, changed files, and review comments.

## Repository instructions

Codex automatically reads the root `AGENTS.md` before beginning work. Start a new thread after changing `AGENTS.md` so the instructions are reloaded.

## Standard pipeline status check

Start a Local thread and use:

```text
Read AGENTS.md first. Inspect the current branch and working tree. Do not use --live and do not call paid external generation APIs. Run the required compile check, the targeted LTX/ASMO tests, and the deterministic offline one-scene pipeline validation. Report every command, pass/fail result, changed file, and remaining risk. Do not modify code unless a validation failure requires a narrowly scoped fix.
```

## Review current changes

Use the app's `/review` command, or send:

```text
Review all branch changes against main. Follow the Review guidelines in AGENTS.md. Prioritize paid/live execution risks, false-success states, secret exposure, path portability, prompt-contract regressions, stale output reuse, and committed local cache or media. Do not change files. Return only actionable findings with file locations and the smallest safe fix.
```

The review pane can compare uncommitted changes, the most recent turn, or all branch changes against the base branch.

## Make a change safely

For code changes, start a **Worktree** thread based on `main` so Codex does not disturb the local checkout. Use:

```text
Read AGENTS.md first. Create the smallest safe implementation for this task in the worktree. Do not use --live or paid generation APIs. Run the narrow relevant tests first, then compile src and tests. Run the full suite only if the change affects shared orchestration, path policy, plan schemas, assembly, or root-pipeline status. Show the final diff and do not commit or push until the checks pass.
```

After reviewing the result, create a branch in the worktree, commit, push, and open a pull request.

## Pull-request feedback workflow

On the pull-request branch:

1. Open the review pane.
2. Inspect the pull-request context and comments.
3. Add inline feedback where needed.
4. Tell Codex: `Address the inline comments and keep the scope minimal.`
5. Re-run the required validation.
6. Stage, commit, and push only after review.

## GitHub Actions

`.github/workflows/pipeline-validation.yml` remains the non-AI enforcement layer. It compiles the project, runs targeted tests, creates synthetic media fixtures, performs an offline one-scene orchestration dry run, validates the active prompt contract, and uploads the plan/report evidence.

The local Codex app complements this workflow; it does not replace GitHub Actions.
