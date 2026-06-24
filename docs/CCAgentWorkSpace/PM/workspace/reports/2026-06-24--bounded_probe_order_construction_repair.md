# Bounded Probe Order Construction Repair

## Session Loop State

- `active_blocker_id`: `P0-BOUNDED-PROBE-CAP-AND-ORDER-CONSTRUCTION-REPAIR-DEMO-ONLY-SOURCE-PROPOSAL`
- `blocker_goal`: Convert the BTC no-order placement failure into a reconstructable order-construction repair packet, and screen lower-price false-negative candidates that can fit the existing bounded Demo cap without lowering the global Cost Gate.
- `profit_relevance`: A bounded Demo probe cannot become live-applicable profit evidence unless the order can be constructed under exchange filters, fresh BBO, candidate attribution, fee/slippage, audit, and reconstructability gates.
- `source_head`: local start `7511198d5405528e7b5a9ddf14ff325fea83c887`; runtime `trade-core` source `bdc1e1568431797cd1001e4484bf2da7ae6df7c4`.
- `runtime_timestamp`: `2026-06-24T16:58:40Z` initial runtime snapshot; latest source-only artifact refresh at `2026-06-24T17:18Z`.
- `pg_snapshot_timestamp`: `2026-06-24 19:01:31.121+02`.
- `previous_report_paths`:
  - `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_adapter_enablement_no_order_btc_review.md`
  - `docs/CCAgentWorkSpace/Operator/2026-06-24--runtime_adapter_enablement_no_order_btc_review.md`
- `operator_action_required`: false for this source-only repair packet. Operator has granted Demo/testnet API operational authority, but live/mainnet, global Cost Gate lowering, Guardian/risk/Decision Lease/Rust-authority bypass, PG writes, service/crontab/runtime mutation, and Rust writer enablement remain excluded.
- `new_evidence_delta_required`: Fresh no-order placement construction evidence or source-only order-construction repair progress. Do not rerun a broad audit.
- `new_evidence_delta_found`:
  - BTC no-order placement preview shows stale BBO plus `qty_step`/cap infeasibility.
  - Read-only PG instrument/ticker screen found 9 false-negative candidates fitting the current 10 USDT cap; top fit is `grid_trading|AVAXUSDT|Sell`.
- `acceptance_criteria`: no Cost Gate lowering, no live/mainnet, no proof from unattributed/flash_dip_buy fills, no Bybit order/cancel/modify, no PG write, no ledger append, no canonical plan mutation, no service/env/crontab mutation, no writer enablement, and every repair packet must be auditable and reconstructable.
- `next_blocker_id`: `P0-BOUNDED-PROBE-LOWER-PRICE-CANDIDATE-REROUTE-REVIEW-DEMO-ONLY`

## Anti-Repeat Decision

`PROCEED_SOURCE_ONLY`.

The prior checkpoint proved admission could reach `ADMIT_DEMO_LEARNING_PROBE` only in a no-order dry run, then failed closed at placement construction. That is a new evidence delta, not a reason to repeat the same runtime-adapter review.

## Runtime Evidence

- BTC no-order placement preview: `/tmp/openclaw/cost_gate_learning_lane/no_order_placement_construction_preview_btc_sell_20260624T164719Z.json`
  - schema `bounded_probe_no_order_placement_construction_preview_v1`
  - status `SKIP_FAIL_CLOSED_NO_ORDER`
  - blocking reasons: `stale_bbo_snapshot`, `max_demo_notional_below_min_positive_qty_step`, `rounded_notional_below_min_notional`, `min_positive_qty_notional_exceeds_demo_cap`
  - BBO age `1652ms` vs max `1000ms`
  - BTCUSDT `qty_step=0.001`, post-round limit `60040.2`, min positive qty notional `60.0402 USDT`, cap `10 USDT/order`

- Candidate universe screen: `/tmp/openclaw/cost_gate_learning_lane/candidate_universe_instrument_screen_false_negative_latest.json`
  - schema `bounded_probe_candidate_universe_instrument_screen_input_v1`
  - sha256 `bf7a8a630522fd5415e4deb09392a13b4c6e3bb9d381ccb4dce0083ed0e4f946`
  - 11 false-negative candidates screened against read-only PG instrument filters and latest tickers
  - 9 fit the current 10 USDT cap
  - top fit: `grid_trading|AVAXUSDT|Sell`, false-negative rank 1, avg net `73.5511bps`, net-positive `100.0%`, outcomes `48`, minimum executable notional `5.0 USDT`

- Order construction repair packet: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_order_construction_repair_latest.json`
  - schema `bounded_demo_probe_order_construction_repair_v1`
  - sha256 `5a5940cf7b1a54ec80a188527fe36695a26454f0b4b14a7fa8e9027a0fda9040`
  - status `ORDER_CONSTRUCTION_REPAIR_REQUIRED`
  - BTC cap repair remains review-only: minimum required `60.0402 USDT/order`
  - lower-price reroute is available: 9 feasible candidates under current cap, top `grid_trading|AVAXUSDT|Sell`
  - input artifact sha/path recorded in packet for reconstructability

## Source Changes

Added:

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_order_construction_repair.py`
- `helper_scripts/research/tests/test_cost_gate_bounded_probe_order_construction_repair.py`

The helper consumes a fresh `bounded_probe_no_order_placement_construction_preview_v1` and optional fresh `bounded_probe_candidate_universe_instrument_screen_input_v1` artifact. It emits a no-authority repair packet that:

- calculates exchange-filter sizing feasibility from limit/reference price, qty step, min notional, and cap;
- reports stale BBO and cap shortfall separately;
- preserves false-negative rank, friction rank, edge, net-positive rate, sample count, spread, and instrument status for reroute candidates;
- fails closed on forbidden authority/proof/mutation contamination, including truthy strings, numbers, and non-empty proof objects;
- refuses to mark construction feasible when `blocking_reasons` is non-empty;
- validates candidate-universe artifact freshness/schema before using it for reroute;
- treats non-`Trading` instruments as not feasible;
- records CLI input artifact path, size, mtime, and sha256.

## Review Chain

- PM: implemented source-only helper, runtime candidate screen, and repair artifacts.
- PA/E1: PASS. Confirmed scope alignment, no-authority output, and profit-relevant rank/edge preservation.
- E2/E4 initial review: FAIL. Found non-boolean contamination, blocking-reason precedence, reconstructability, and candidate-universe validation gaps.
- PM fixes: added fail-closed contamination semantics, blocking-reason precedence, input sha metadata, candidate artifact validation, non-Trading infeasibility, and bare-array CLI regression.
- E2/E4 final review: PASS. No remaining findings.
- QA/PM: source-only tests and runtime artifact hashes recorded.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_order_construction_repair.py`: `11 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_placement_repair_plan.py helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py helper_scripts/research/tests/test_cost_gate_bounded_probe_order_construction_repair.py`: `42 passed`.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_order_construction_repair.py helper_scripts/research/tests/test_cost_gate_bounded_probe_order_construction_repair.py`: passed.
- `git diff --check`: passed.

## Aggressive Profit Hypotheses

1. `false_negative_avax_reroute_under_existing_cap`
   - `why_it_might_make_money`: AVAX false-negative rank 1 has 48/48 net-positive 60m outcomes, avg net `73.5511bps` after current cost assumptions, and fits the current 10 USDT cap under live-grade instrument filters.
   - `fastest_safe_test`: Generate a candidate-specific no-order construction preview and bounded Demo review packet for `grid_trading|AVAXUSDT|Sell`; do not mutate canonical plan or submit orders until gates pass.
   - `required_data`: fresh BBO, instrument filters, funding/spread, current fee/slippage assumptions, candidate-matched controls, and lineage fields.
   - `failure_condition`: stale BBO, widened spread erases net edge, non-candidate fills, missing candidate attribution, or candidate universe artifact stale/schema-mismatched.
   - `authority_required`: none for screening; Demo order path uses existing Demo/testnet operational authorization only after candidate/order gates pass.
   - `max_safe_next_action`: `P0-BOUNDED-PROBE-LOWER-PRICE-CANDIDATE-REROUTE-REVIEW-DEMO-ONLY`.
   - score: expected_net_pnl_upside 8, evidence_strength 7, execution_realism 7, cost_after_fees 8, time_to_test 8, risk_to_account 2, risk_to_governance 2, autonomy_value 8.

2. `btc_cap_repair_only_if_risk_qc_prefers_high-liquidity_probe`
   - `why_it_might_make_money`: BTC has deep liquidity and lower microstructure noise, but current cap is below minimum executable notional.
   - `fastest_safe_test`: Candidate-scoped cap review for BTC only, no global Cost Gate lowering, no live, and no order until a fresh preview passes.
   - `required_data`: current BTC filters, min executable notional, cap budget, maker/slippage estimate, fill attribution plan.
   - `failure_condition`: cap increase makes account risk or governance risk worse than lower-price reroute, or fresh BBO still fails.
   - `authority_required`: operator/QC bounded Demo cap review if choosing this path.
   - `max_safe_next_action`: keep as secondary option behind AVAX reroute.
   - score: expected_net_pnl_upside 5, evidence_strength 5, execution_realism 6, cost_after_fees 6, time_to_test 5, risk_to_account 5, risk_to_governance 4, autonomy_value 5.

3. `instrument_filter_aware_false_negative_portfolio_queue`
   - `why_it_might_make_money`: Many false-negative candidates are positive after current fees but only a subset can be tested under cap; sizing-aware ranking avoids wasting probe budget on unexecutable BTC/ETH variants.
   - `fastest_safe_test`: Keep generating read-only candidate universe screens and feed only schema-valid, fresh, cap-feasible candidates into bounded Demo proposal review.
   - `required_data`: scorecard, instrument filters, latest tickers, spread/funding, candidate samples, matched controls.
   - `failure_condition`: top candidates become stale, spreads/funding erase edge, or candidate artifacts are not reconstructable.
   - `authority_required`: none for screening; Demo order authority only after candidate-specific gates.
   - `max_safe_next_action`: promote the screen into the next candidate-selection gate.
   - score: expected_net_pnl_upside 7, evidence_strength 6, execution_realism 8, cost_after_fees 7, time_to_test 8, risk_to_account 2, risk_to_governance 2, autonomy_value 9.

## Status

`DONE_WITH_CONCERNS`.

The active source-only blocker is closed: the repair helper, tests, and runtime artifact packet exist and are review-passed. Concern remains that the current BTC candidate is not executable under the 10 USDT cap; the highest-upside safe next step is not to raise cap first, but to review the lower-price false-negative reroute path for `grid_trading|AVAXUSDT|Sell`.

## Why Not Repeating Current Blocker

The repair packet and candidate-universe screen are fresh, hashed, and reviewed. Re-running the same source-only repair without a new placement preview, PG/ticker snapshot, source HEAD change, or authorization/governance change would be `NO-OP_NO_EVIDENCE_DELTA`.
