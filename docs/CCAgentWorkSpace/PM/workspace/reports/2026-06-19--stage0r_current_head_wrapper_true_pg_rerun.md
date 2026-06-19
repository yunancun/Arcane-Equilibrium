# Stage0R Current-Head Wrapper True-PG Rerun

Date: 2026-06-19
Owner: PM
Scope: `P1-A1A2-STAGE0R-RUNNER-IMPL`

## Result

Current-head Linux true-PG read-only rerun completed for the Stage0R report-wrapper family.

This removes the stale "no new true-PG rerun beyond v217 artifact" caveat for this row, but it does not create a trusted promotion packet and does not close E4/QC/MIT/QA authority.

## Run Context

- Linux repo: `/home/ncyu/BybitOpenClaw/srv`
- Linux HEAD: `e69d5fd3c90c8d19799c4f58f1e1ed176fa4d0ef`
- Linux origin/main: `e69d5fd3c90c8d19799c4f58f1e1ed176fa4d0ef`
- Run dir: `/tmp/openclaw/stage0r_current_head_verify_20260619T011508Z`
- Environment:
  - `PGOPTIONS="-c default_transaction_read_only=on"`
  - `OPENCLAW_DATABASE_URL`, `DATABASE_URL`, and `POSTGRES_PASSWORD` deliberately unset
  - `PGHOST=localhost`, `PGPORT=5432`, `PGUSER=trading_admin`, `PGDATABASE=trading_ai`
- Output scope: `/tmp/openclaw` only

PostgreSQL emitted the existing informational collation-version warning during each wrapper run.

## Artifacts

`w_audit_8b_14d_btc_eth.json`

- Path: `/tmp/openclaw/stage0r_current_head_verify_20260619T011508Z/w_audit_8b_14d_btc_eth.json`
- sha256: `1a0bea6ae1c87183ebabf7d8a1f8dc46874dfc4509f7a313faede6646d35c372`
- `row_count=8034`
- `eligible_for_demo_canary=false`
- `eligibility_fail_reasons=["no primary-horizon signals"]`
- `pooled_primary.n=0`
- `pbo_metadata.reason=insufficient_days_or_candidates`
- `k_total=4050`, `k_prior=0`

`alpha_candidate_14d_btc_eth.json`

- Path: `/tmp/openclaw/stage0r_current_head_verify_20260619T011508Z/alpha_candidate_14d_btc_eth.json`
- sha256: `6bcbd8efebe0cc2aa72404ec485975f66e32f60dfb989c56e65ae22c462777c2`
- `verdict=observe_more`
- `stage0_ready=false`
- A1 `funding_short_v2`: `verdict=draft_only`, `selected_signals=0`, `fail_reasons=["no_a1_signals_after_entry_gate"]`
- A2 `liquidation_cascade_fade`: `verdict=observe_more`, `eligible_for_demo_canary=false`, `n_filtered_rows=221`, `n_eff=14`, `avg_net_bps=-1.2963520765433392`, `pbo=0.1125`
- A2 embedded 8c packet carries `both_direction_floor.total_bucket_count=2924` and `fail_reason=null`

`2026-06-19--w_audit_8c_stage0r_red.json`

- Path: `/tmp/openclaw/stage0r_current_head_verify_20260619T011508Z/w_audit_8c/2026-06-19--w_audit_8c_stage0r_red.json`
- sha256: `b027b09adf9bb6f8d421690b36ad26bf08c63a5bb462ade7db754868a682aeb5`
- `verdict=RED`
- `review_ready=true`
- `panel_meta.total_rows=291`
- `panel_meta.distinct_symbols=2`
- `panel_meta.span_days=13.771`
- `params.total_bucket_count=2924`
- `primary_cell.pass=RED`
- `primary_cell.n_per_cell=285`
- `primary_cell.pooled_n_eff=14`
- `primary_cell.avg_net_bps=-7.417304178231849`
- `primary_cell.cost_edge_ratio=2.618546040738531`
- both-direction floor:
  - `long_count=164`, `long_trigger_rate=0.0560875512995896`, `long_passed=true`
  - `short_count=121`, `short_trigger_rate=0.04138166894664843`, `short_passed=true`
  - `both_passed=true`
  - `fail_reason=null`
- Recursive JSON scan found `missing_bucket_count_denominator` occurrences: `0`

## Boundary

- No full CI.
- No cargo, Linux build, deploy, rebuild, restart, or runtime config change.
- No DB write; the run used PostgreSQL read-only transaction option.
- No repo artifact write beyond this report/TODO documentation.
- No Bybit private/signed/trading API call.
- No credential/key/secret/auth/risk/order/trading mutation.
- This does not close trusted promotion packet, E4 full review, QC/MIT/QA sign-off, Stage0R promotion, P0-EDGE, or any operator gate.
