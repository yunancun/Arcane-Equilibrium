# PM Report: ETH Construction Preview Not Feasible Under Cap

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-ETH-MARKET-SNAPSHOT-CONSTRUCTION-PREVIEW-DEMO-ONLY`

## Decision

Closed the ETH no-order construction checkpoint. The current top false-negative candidate remains high-upside research evidence, but it is not safely constructible under the current bounded Demo cap.

## Actions

- E3 approved the no-authority artifact path and ruled BB not needed because no Bybit call or exchange-facing action occurred.
- Linux runtime source fast-forwarded from `d2971aa5` to `e0c2a0e1`.
- Crontab expected-head pins were updated from `d2971aa5` to `e0c2a0e1` to avoid source/cron drift.
- Generated a no-authority false-negative operator review approval for `grid_trading|ETHUSDT|Buy` rank 1.
- Refreshed false-negative bounded preflight to `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`.
- Generated a read-only PG ETH market snapshot and no-order construction preview.

## Evidence

- Operator review latest: `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`.
- Preflight latest: `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`.
- Market snapshot: `/tmp/openclaw/cost_gate_learning_lane/candidate_market_snapshot_eth_buy_20260625T213334Z.json`
  - sha256 `6d225a98749f04aa98944a9a3e915f5a72c9595673c0683eff7d8464e399300f`
  - source `read_only_pg:market.market_tickers+market.symbol_universe_snapshots`
  - `pg_query_performed=true`, `pg_write_performed=false`, `bybit_call_performed=false`, `order_submission_performed=false`
- Construction preview: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_candidate_construction_preview_eth_buy_20260625T213334Z.json`
  - sha256 `f4e36f149bd98d93f2d187fb8650c38038b46e2f3e024df864714f7dce7de9a8`
  - status `CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP`
  - BBO fresh: `effective_bbo_age_ms=548.816` under `1000`
  - limit price `1571.05`, qty step `0.01`, cap `10.0`, minimum positive qty notional `15.7105`
  - blockers: `rounded_qty_not_positive_under_cap`, `rounded_notional_below_min_notional`, `min_positive_qty_notional_exceeds_cap`

## Verification

- Linux focused construction/BBO/public-quote/plan-inclusion suites: `91 passed`.
- Artifact validation checked candidate tuple alignment, explicit no-authority fields, read-only PG source, no order/probe authority, and Cost Gate `NONE`.
- Crontab after sync: 70 lines, `e0c2a0e1` count 11, old `d2971aa5` count 0, probe outcomes recording remains `0`, adapter/mainnet flags absent.

## Boundary

FF-only runtime source sync plus expected-head crontab pin sync, read-only PG query, `/tmp/openclaw` artifact writes, and docs only. No Bybit call, no order/cancel/modify, no PG write, no service restart, no Cost Gate lowering, no live/mainnet, no Rust writer/adapter enablement, no probe/order authority, and no promotion proof.

## Next Safe Action

Move to cap-feasible candidate selection/reroute. Do not widen the bounded cap or submit an ETH order from this evidence. The ETH edge remains a research lead that would require a separately reviewed risk/cap decision before it can become a bounded Demo probe candidate.
