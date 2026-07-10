# Audit Correctness Fix Log

Date: 2026-07-10

Branch: `audit/repo-cleanup-2026-07-10`

## Completed: score-evidence safeguard

The first high-priority audit finding has been addressed on the audit branch.

### Problem

`ltx_feedback_analyzer.py` previously substituted missing human scores with numeric defaults that were below multiple failure thresholds. An unreviewed scene could therefore be labeled with weak synchronization, motion mismatch, camera mismatch, and low prompt obedience. `ltx_policy_store.py` then treated those synthetic values as learning evidence.

### Change

- Missing scores now remain `None`.
- Score-derived issues are emitted only when an explicit valid score exists.
- Each metric records `score_evidence` as `human_scorecard` or `missing`.
- Feedback packets record scored and fully unscored scene counts.
- Policy updates accept only scores carrying a trusted evidence source.
- Numeric legacy/unproven scores are ignored and counted in `last_feedback_evidence`.
- Non-score findings such as generation failure, excessive prompt length, conflicts, and directive overload remain active without human scores.

### Tests added

`tests/test_ltx_feedback_score_evidence.py` covers:

- fully unscored scenes do not receive invented score failures;
- partially scored scenes use only the supplied metric;
- policy ignores numeric values without evidence provenance;
- trusted human-score evidence still updates the intended strategies and learned adjustments.

### Validation status

The GitHub connector can write and inspect repository files but cannot execute the local Python test suite in this session. The new tests must be run by GitHub Actions or locally before merge.
