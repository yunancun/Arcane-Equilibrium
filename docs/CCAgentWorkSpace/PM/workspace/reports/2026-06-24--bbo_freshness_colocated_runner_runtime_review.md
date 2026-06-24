# BBO Freshness Co-Located Runner Runtime Review

## Session Loop State

- `active_blocker_id`: `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY`
- `blocker_goal`: PM->E3 runtime review, then bounded trade-core sync/run of the co-located BBO runner in explicit read-only PG mode.
- `profit_relevance`: AVAX remains a cap-feasible high-upside false-negative candidate; if runtime BBO freshness passes without weakening gates, it can move to order-admission review for candidate-matched Demo evidence.
- `anti_repeat_decision`: `PROCEED_WITH_RUNTIME_REVIEW_SOURCE_RUNTIME_DELTA`
- `new_evidence_delta_found`: local/origin source had `8e7bc890` while trade-core remained clean at `bdc1e156`; no runtime pg-readonly runner artifact existed.
- `next_blocker_id`: `P0-BOUNDED-PROBE-BBO-FRESHNESS-PUBLIC-QUOTE-CAPTURE-E3-BB-REVIEW-DEMO-ONLY`

## Runtime Action

E3 returned `DONE_WITH_CONCERNS` / `PASS` and allowed only a PM-owned bounded envelope:

- clean-tree / branch / exact-start checks;
- `git ls-remote` target check;
- fetch and fast-forward-only merge to `8e7bc890`;
- focused runner+preview pytest;
- helper run with `--pg-readonly` and required `--market-snapshot-output`;
- stop after artifact generation, with no order path.

BB was skipped because this path was not exchange-facing. Direct public quote capture remains BB-gated.

## Evidence

Runtime source:

- before: `bdc1e1568431797cd1001e4484bf2da7ae6df7c4`
- after: `8e7bc890ebb8e3a15f3e329dbb177bcfe453bff8`
- runtime worktree: clean after run

Runtime verification:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q -p no:cacheprovider helper_scripts/research/tests/test_cost_gate_bbo_freshness_colocated_runner.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py`: `30 passed`

Artifacts:

- market snapshot: `/tmp/openclaw/cost_gate_learning_lane/candidate_market_snapshot_avax_sell_colocated_pg_20260624T185436Z.json`
  - sha256 `16effdae7ec28a8454f980d59b79cb62bc12310dc969d59a06d14242405e75e4`
- construction preview: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_candidate_construction_preview_avax_sell_colocated_pg_20260624T185436Z.json`
  - sha256 `fe33a6988ec576e433181711d89a718aa676b38db714979eacf9f907ce8d885b`
- runner packet: `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_colocated_runner_avax_sell_pg_readonly_20260624T185436Z.json`
  - sha256 `8a204584715c13f53852a0107de263893e1ba55d804f5c73873fac2889645568`
- runner markdown: `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_colocated_runner_avax_sell_pg_readonly_20260624T185436Z.md`
  - sha256 `c9ff0237a75d77a8eae002a8d0bd6ceff450b97943ac12e7df681b0e761a0b11`

Runner result:

- status `COLOCATED_RUNNER_BBO_STALE_NO_ORDER`
- mode `pg_readonly`
- preview status `CANDIDATE_CONSTRUCTION_BBO_STALE`
- effective BBO age `2476.128ms` vs gate `1000ms`
- ticker timestamp `2026-06-24T18:54:34.196000+00:00`
- PG snapshot timestamp `2026-06-24T18:54:36.585639+00:00`
- construction remains cap-feasible: limit `6.086`, qty `1.6`, notional `9.7376 USDT`

Authority answers:

- `pg_query_performed=true`
- `pg_write_performed=false`
- `bybit_call_performed=false`
- `order_submission_performed=false`
- `runtime_mutation_performed=false`
- `main_cost_gate_adjustment=NONE`
- `probe_authority_granted=false`
- `order_authority_granted=false`
- `live_authority_granted=false`
- `promotion_evidence=false`

## Aggressive Profit Hypotheses

1. `public_quote_capture_before_construction`
   - `why_it_might_make_money`: direct public ticker capture may bypass PG collector lag and bring AVAX under the 1000ms BBO freshness gate.
   - `fastest_safe_test`: PM->E3->BB review of a public-market-data-only quote capture helper; no private/order endpoint.
   - `required_data`: request/response timestamps, ticker bid/ask, instrument filters, source hash, construction preview hash.
   - `failure_condition`: quote timing is not reconstructable, source is exchange-facing without BB approval, or BBO still exceeds 1000ms.
   - `authority_required`: PM->E3->BB before any public Bybit call.
   - `max_safe_next_action`: `P0-BOUNDED-PROBE-BBO-FRESHNESS-PUBLIC-QUOTE-CAPTURE-E3-BB-REVIEW-DEMO-ONLY`.

2. `pg_ticker_pipeline_lag_rca`
   - `why_it_might_make_money`: if PG ticker lag is a collector cadence/backpressure issue, reducing lag preserves the PG SSOT path and improves all future bounded probes.
   - `fastest_safe_test`: read-only collector freshness histogram by symbol and process/cron status snapshots.
   - `required_data`: ticker `ts` lag distribution, collector logs, process age, latest symbol coverage.
   - `failure_condition`: lag is normal exchange/update cadence or requires service restart/config mutation.
   - `authority_required`: none for read-only; PM->E3 for service/config changes.
   - `max_safe_next_action`: source-only/read-only RCA only, no service restart.

3. `larger_tick_low_price_candidate_pool`
   - `why_it_might_make_money`: if AVAX freshness remains noisy, other cap-feasible false-negative symbols may have fresher PG BBO while preserving the same Cost Gate escape thesis.
   - `fastest_safe_test`: read-only reroute over the false-negative candidate list using latest PG lag filter, selecting exactly one alternate only if AVAX remains stale.
   - `required_data`: false-negative packet, instrument min-notional/tick/qty, ticker lag, net bps after fees/slippage.
   - `failure_condition`: alternate has lower edge, worse cost cushion, stale BBO, or weak sample.
   - `authority_required`: none for research/proposal; separate operator/admission review before any order.
   - `max_safe_next_action`: proposal-only alternate selection, no authority.

## Status

`DONE_WITH_CONCERNS`.

The runtime runner is deployed and reconstructable, but the PG-fed BBO is still stale. No order admission follows from this checkpoint.
