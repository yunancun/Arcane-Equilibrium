# Stage0R 8c Denominator Fix + PM Runtime Verification

Date: 2026-06-19
Owner: PM
Scope: `P1-A1A2-STAGE0R-RUNNER-IMPL`

## Result

PM formal runtime verification is now complete for the Stage0R report-wrapper family at the current source checkpoint, with one source fix landed for the standalone 8c wrapper.

The remaining blocker is E4/formal review before these outputs can be treated as trusted promotion packets.

## Source Finding

Initial Linux read-only verification run:

- Run dir: `/tmp/openclaw/stage0r_formal_runtime_verify_20260619T000547Z`
- Linux repo HEAD at run time: `61e1a6d2`
- Environment: `PGOPTIONS="-c default_transaction_read_only=on"`
- `OPENCLAW_DATABASE_URL` and `POSTGRES_PASSWORD` deliberately unset
- Output only under `/tmp/openclaw`

Findings:

- `w_audit_8b_14d_btc_eth.json`
  - sha256: `e140de646b85b1b7f1102d7a070cd5e8ee8f1d5119d18e518d38d3461d75e7b1`
  - `row_count=8034`
  - `eligible_for_demo_canary=false`
  - fail reason: `no primary-horizon signals`
- `alpha_candidate_14d_btc_eth.json`
  - sha256: `bf85cbcc54db7266f4d753a4fc901040166c9c3489f1fd3bb5c8e0969a9d54f6`
  - `verdict=observe_more`
  - `stage0_ready=false`
  - A1: `draft_only`
  - A2: `observe_more`
- Standalone 8c completed but exposed a source gap:
  - sha256: `1c68df33da83c14dc4b0ad47ae1b160052b0fb0b2066165d0c3293f228403da3`
  - `verdict=RED`, `review_ready=true`
  - `primary_cell.both_direction_floor.fail_reason=missing_bucket_count_denominator`

The alpha-candidate A2 adapter already queried and passed `total_bucket_count`; the standalone 8c wrapper did not.

## Source Fix

Changed files:

- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py`
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py`

Fix:

- `_fetch_panel_rows(...)` now returns `(panel_rows, total_bucket_count)`.
- `total_bucket_count` is computed from the raw 5m liquidation bucket denominator.
- `main(...)` passes `total_bucket_count` to both `compute_stage0r(...)` and `compute_stage0r_sweep(...)`.
- `sweep_params` records `total_bucket_count`.
- Smoke CLI now passes denominator through single-cell, sweep, packet-builder, and markdown paths and asserts that `missing_bucket_count_denominator` is absent.

## Verification

Local focused verification:

- `python3 -m py_compile helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py`
- `python3 helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py`
  - `SMOKE PASS: 11/11 tests passed`
- `python3 helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke.py`
  - `PASS W-AUDIT-8c Stage 0R metrics smoke`
- `python3 helper_scripts/reports/alpha_candidate_stage0r/candidate_stage0r_smoke.py`
  - `PASS alpha_candidate_stage0r runner smoke`
- `python3 helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`
  - `PASS W-AUDIT-8b Stage 0R metrics smoke`
- `git diff --check` on changed source/test files
  - PASS

Linux true-PG verification was run from a temporary clone, not the canonical Linux checkout:

- Temp clone: `/tmp/openclaw_stage0r_8c_fix_test`
- Patch file: `/tmp/stage0r_8c_denominator_fix.patch`
- Run dir: `/tmp/openclaw/stage0r_8c_denominator_fix_20260619T001027Z`
- Environment: `PGOPTIONS="-c default_transaction_read_only=on"`
- `OPENCLAW_DATABASE_URL` and `POSTGRES_PASSWORD` deliberately unset
- Output only under `/tmp/openclaw`

Post-fix standalone 8c artifact:

- Path: `/tmp/openclaw/stage0r_8c_denominator_fix_20260619T001027Z/w_audit_8c/2026-06-19--w_audit_8c_stage0r_red.json`
- sha256: `30b1fd4aabe9b7e4840bbb82c5c3b560439bea8f3c6f857ef89bc6bddf7b3670`
- `verdict=RED`
- `review_ready=true`
- `panel_meta.total_rows=291`
- `panel_meta.distinct_symbols=2`
- `panel_meta.span_days=13.771`
- `params.total_bucket_count=2931`
- both-direction floor:
  - `long_count=164`, `long_trigger_rate=0.05595359945411123`, `long_passed=true`
  - `short_count=121`, `short_trigger_rate=0.04128283862163084`, `short_passed=true`
  - `both_passed=true`
  - `fail_reason=null`
- `missing_denominator=false`

## Boundary

- No deploy, rebuild, restart, or runtime config change.
- No production/canonical Linux checkout mutation for the true-PG post-fix run.
- No DB write; verification used PostgreSQL read-only transaction option.
- No Bybit private/signed/trading API call.
- No credential/key/secret/auth/risk/order/trading mutation.
- This does not close E4 review and does not promote A1/A2/8c outputs.
