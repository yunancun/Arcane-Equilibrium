# 2026-05-16 W-AUDIT-8b Stage 0R Adversarial Hardening

## Scope

Operator requested multi-agent adversarial review of `W-AUDIT-8b` before future use. This pass stayed read-only with respect to trading/runtime state: no demo, paper, LiveDemo, live auth, risk config, DB migration, or strategy implementation was changed.

## Review Inputs

- QC review: blocked green demo-canary eligibility until K accounting, sample denominators, PBO retention, bootstrap, baseline, and cost model are fail-closed.
- E2 review: returned to E1 for duplicated grid-expanded sample accounting, under-deflated K on narrowed panels, and unusable 7d PBO embargo.
- MIT review: no critical finding, but required strict funding-skew K_prior default, usable PBO under 7-14d retention, exact forward horizons, and settlement rows excluded from eligibility.
- BB review: blocked full sign-off until settlement post-boundary detection and mixed current/settled funding source handling were fail-closed.

## Source Changes

- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py`
  - Floors `K_new` at 4050 and emits `k_new_actual`, `k_new_min`, and `k_new_floor_applied`.
  - Selects and reports pooled/branch/per-symbol metrics for one fixed parameter family instead of pooling grid-expanded duplicates.
  - Excludes settlement-window rows from eligibility while reporting including/excluding sensitivity.
  - Detects previous funding boundary from inferred funding interval so post-settlement rows are flagged.
  - Marks mixed funding source modes as `mixed` and fail-closed.
  - Replaces 7d embargo walk-forward PBO with day-block CSCV metadata.
  - Requires baseline lift and conservative cost-edge ratio in eligibility.
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py`
  - Defaults `--k-prior-mode` to `strict-funding-skew`.
  - Renders K actual/floor metadata in markdown summaries.
- `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql`
  - Uses exact 15m/30m/60m `close_ts_ms` joins instead of first row `>= target horizon`.
  - Emits horizon close timestamps for auditability.
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`
  - Tests K floor behavior, previous-settlement-window marking, and mixed-source fail-closed behavior.

## Verification

- `python3 -m py_compile helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`
- `python3 helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`
- `python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py --help`
- `git diff --check`

Smoke result: `PASS W-AUDIT-8b Stage 0R metrics smoke`, `eligible_for_demo_canary=False`, `k_total=4119`.

## Remaining Gate

This hardens the tooling only. Round 2 still needs a real panel run after panel age reaches at least 7d, followed by QC/MIT/BB verdict. Strategy implementation, demo spend, paper promotion, and live authority remain blocked until a future Stage 0R packet returns `eligible_for_demo_canary=true` and the normal governance gates clear.
