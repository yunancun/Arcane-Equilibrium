# W-AUDIT-8b Stage 0R Gap Closure

Date: 2026-05-16
Role: PM local implementation slice
Scope: Funding Skew Stage 0R read-only report tooling only

## Task Summary

Closed the local source/test portion of the W-AUDIT-8b Stage 0R Round 2 prep gap list. This does not run Round 2 full replay, does not select a demo canary cohort, and does not authorize strategy implementation.

## Modified Files

- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py`
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py`
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`

## Changes

- Added explicit panel metadata, source-mode derivation, stale/missing zero-count fields, per-symbol primary breakdown, settlement-window sensitivity, baseline lift versus no-funding/OI confirmation, flat cost model with cost-edge ratio, 60m and 8h bootstrap intervals, PBO metadata with purged walk-forward embargo semantics, and plateau-check output.
- Changed eligibility to use pooled primary bootstrap lower bound for the bootstrap floor and to fail closed when plateau support is absent.
- Added `--k-prior-mode` with `funding-related`, `strict-funding-skew`, and `all` modes; manual `--k-prior` still works and records metadata.
- Extended the smoke fixture to assert the new report contract fields and K-prior mode routing.

## Verification

Passed:

```bash
python3 -m py_compile helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py
python3 helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py
python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py --help
git diff --check
```

Smoke result:

```text
PASS W-AUDIT-8b Stage 0R metrics smoke
eligible_for_demo_canary=False
k_total=555
```

## Boundaries

- No DB write, migration, DDL, config, risk sizing, live/demo auth, restart, or trading runtime mutation.
- No `OPENCLAW_ENABLE_PAPER=1`.
- Existing unrelated Rust/TOML worktree changes were not touched or staged.

## Remaining Blockers

- Round 2 full replay should wait until the panel reaches the TODO target of at least 7 days, unless PM/QC/MIT decide to run an explicitly underpowered diagnostic.
- MIT still needs to sign the final `K_prior` semantic. The tooling now exposes the candidate modes but does not make the governance decision.
- QC/MIT/BB review is still required before any Stage 0R verdict can be used for demo-canary discussion.

PM SIGN-OFF: CONDITIONAL — source/test gap closure complete; Stage 0R verdict remains blocked on data window and review.
