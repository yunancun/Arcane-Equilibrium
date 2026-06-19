# Stage0R 8c Denominator Focused Regression

Date: 2026-06-19
Role: E4 focused regression slice
Verdict: PASS for the W-AUDIT-8c denominator source fix scope

## Scope

This verifies the Stage0R 8c standalone wrapper regression that previously let a no-sweep 8c report reach metrics without the raw 5m bucket denominator, producing `missing_bucket_count_denominator`.

This is a focused source/regression check only. It does not authorize a trusted Stage0R promotion packet, live/demo canary promotion, deploy, rebuild, restart, DB write, auth/risk/order/trading mutation, or full QC/MIT/QA sign-off.

## Source Inspection

- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py:241-309` now returns `(panel_rows, total_bucket_count)` from `_fetch_panel_rows`, with `total_bucket_count` computed from raw liquidation 5m buckets.
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py:1111-1114` stores that denominator in `sweep_params`.
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py:1143-1167` passes `total_bucket_count` into both single-cell and sweep kwargs.
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py:1168-1173` routes those kwargs into `compute_stage0r` and `compute_stage0r_sweep`.
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py:474-509` fail-closes `_both_direction_floor_check` when `total_bucket_count is None`.
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py:1073-1292` records omitted `total_bucket_count` as a hard RED reason.
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py:1529-1624` propagates `total_bucket_count` from sweep into each cell.
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py:219-251`, `256-278`, `338-410`, and `418-431` assert the wrapper/packet paths pass the denominator and do not emit `missing_bucket_count_denominator`.
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke.py:931-963` intentionally omits the denominator and verifies the fail-closed RED path still bites.

## Commands Run

All commands were run from `/Users/ncyu/Projects/TradeBot/srv` on Mac/local checkout `071e1b09` with the pre-existing dirty worktree left untouched except for this documentation slice.

1. Syntax gate:
   - `python3 -m py_compile helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke.py helper_scripts/reports/alpha_candidate_stage0r/candidate_stage0r_smoke.py helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`
   - Result: PASS

2. First focused regression pass:
   - `python3 helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py`
   - Result: PASS, 11/11
   - `python3 helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke.py`
   - Result: PASS, `W-AUDIT-8c Stage 0R metrics smoke`, `ALPHA_SOURCE_ID=liquidation_cluster_reaction`
   - `python3 helper_scripts/reports/alpha_candidate_stage0r/candidate_stage0r_smoke.py`
   - Result: PASS, `A2_ALPHA_SOURCE_ID=liquidation_cascade_fade`, `A2_K_NEW_CANDIDATE=4`
   - `python3 helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`
   - Result: PASS, `eligible_for_demo_canary=False`, `k_total=4119`

3. Repeat focused regression pass:
   - `python3 helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py`
   - Result: PASS, 11/11
   - `python3 helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke.py`
   - Result: PASS
   - `python3 helper_scripts/reports/alpha_candidate_stage0r/candidate_stage0r_smoke.py`
   - Result: PASS
   - `python3 helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`
   - Result: PASS

4. Shared helper regression:
   - `python3 -m pytest helper_scripts/lib/tests/test_stats_common.py -q`
   - Result: `33 passed in 0.05s`

## Boundary

Not run in this E4 slice:

- Full CI.
- Full Linux E4 suite / cargo workspace regression.
- New Linux true-PG report rerun beyond the prior PM v217 runtime verification artifact.
- Deploy, rebuild, restart, model call, DB write, credential/key/secret/runtime/auth/risk/order/trading mutation.

## Conclusion

The focused E4 regression for the Stage0R 8c denominator source fix is PASS. The previous missing-denominator failure is covered both positively, by wrapper/packet tests that pass `total_bucket_count`, and negatively, by fail-closed smoke tests that still RED when the denominator is omitted.

This reduces the open E4 denominator-fix review gate. It does not by itself make Stage0R runner outputs trusted for promotion or canary decisions.
