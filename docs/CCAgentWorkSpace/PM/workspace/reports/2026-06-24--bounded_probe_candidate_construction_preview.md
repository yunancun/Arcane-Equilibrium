# Bounded Probe Candidate Construction Preview

## Session Loop State

- `active_blocker_id`: `P0-BOUNDED-PROBE-REROUTE-CANDIDATE-CONSTRUCTION-PREFLIGHT-DEMO-ONLY`
- `blocker_goal`: Build a candidate-specific no-order construction preview for the selected AVAXUSDT Sell reroute candidate before any demo order admission.
- `profit_relevance`: A high-edge false-negative candidate only matters if it can be constructed under real instrument filters, BBO freshness, passive placement, and the current Demo cap. This checkpoint prevents wasting risk budget on unexecutable or stale-market probes.
- `completed_blockers`: includes `P0-BOUNDED-PROBE-LOWER-PRICE-CANDIDATE-REROUTE-REVIEW-DEMO-ONLY`.
- `previous_report_paths`:
  - `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--bounded_probe_lower_price_reroute_review.md`
  - `docs/CCAgentWorkSpace/Operator/2026-06-24--bounded_probe_lower_price_reroute_review.md`
- `source_head`: local/origin `7f30d3597652beb0dac4cd23d2a484af209f27f1`; runtime `trade-core` source `bdc1e1568431797cd1001e4484bf2da7ae6df7c4`.
- `runtime_timestamp`: session loop state `/tmp/openclaw/session_loop_state_20260624T174213Z_avax_construction_preflight.json`; preview refreshed at `2026-06-24T18:04Z`.
- `operator_action_required`: false for source-only/no-order preview. Demo/testnet operational authorization is recorded, but live/mainnet, global Cost Gate lowering, Guardian/risk/Decision Lease/Rust-authority bypass, PG writes, service/crontab/runtime mutation, and Rust writer enablement remain excluded.
- `new_evidence_delta_required`: Fresh AVAX lower-price reroute review plus candidate-specific market/instrument snapshot sufficient for no-order construction preview.
- `new_evidence_delta_found`: reroute latest selects `grid_trading|AVAXUSDT|Sell`; read-only PG market snapshot exists for AVAXUSDT.
- `next_blocker_id`: `P0-BOUNDED-PROBE-REROUTE-FRESH-BBO-CONSTRUCTION-REFRESH-DEMO-ONLY`

## Anti-Repeat Decision

`PROCEED_WITH_NEW_EVIDENCE_DELTA`.

This did not repeat the completed lower-price reroute review. It advanced the next state by constructing a candidate-specific no-order preview from the selected AVAX reroute artifact and a read-only market snapshot.

## Source Changes

Added:

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_candidate_construction_preview.py`
- `helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py`

The helper emits `bounded_demo_probe_candidate_construction_preview_v1` and requires:

- fresh/schema-valid `bounded_demo_probe_lower_price_reroute_review_v1`;
- fresh/schema-valid `bounded_probe_candidate_market_snapshot_v1` from `read_only_pg:market.market_tickers+market.symbol_universe_snapshots`;
- exact candidate identity match across reroute review and market snapshot;
- raw `ticker.symbol` and raw `instrument.symbol` equal to selected candidate symbol;
- raw ticker/instrument fields as construction SSOT, with present `derived.*` fields required to parse and match raw values;
- BBO freshness recomputed from raw `ticker.ts` to preview generation time;
- `instrument.status == Trading`;
- passive near-touch placement and qty/min-notional feasibility under the candidate cap;
- recursive no-authority/no-proof/no-mutation preservation, allowing only read-only `pg_query_performed` on the market snapshot input.

## Runtime Artifacts

- Market snapshot: `/tmp/openclaw/cost_gate_learning_lane/candidate_market_snapshot_avax_sell_latest.json`
- Market snapshot sha256: `a82413e3ccb8fe48c445f7613132b356f0dab4fe3ea0d8840104878aa17b247c`
- Preview: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_candidate_construction_preview_avax_sell_latest.json`
- Preview sha256: `3d652a3a5f28433adf33944e1dcf63d6a7a05ab176f161efaba3569611237600`
- Preview status: `CANDIDATE_CONSTRUCTION_BBO_STALE`
- Blocking gates: `bbo_freshness`

Construction math from the latest preview:

- selected candidate `grid_trading|AVAXUSDT|Sell`
- best bid/ask `6.044 / 6.045`
- passive sell limit `6.045`
- rounded qty `1.6`
- rounded notional `9.672 USDT`
- min positive qty notional `0.6045 USDT`
- cap `10.0 USDT`
- min notional `5.0 USDT`
- reported BBO age from snapshot `4791.161ms`
- effective BBO age at preview generation `1229558.906ms`
- max fresh BBO age `1000ms`

## Review Chain

- PM: implemented helper, tests, read-only market snapshot ingestion, runtime preview artifact, and docs.
- PA/E1 initial review: FAIL. Found under-validated nested market identity, trusted BBO age, incomplete authority danger keys, raw/derived contradiction, and malformed derived numeric gaps.
- E2/E4 initial review: FAIL. Found stale-BBO fail-open, wrong-symbol market data, incomplete authority keys, and stale-BBO status precedence.
- PM fixes: raw ticker/instrument SSOT, expected read-only source gate, ticker/instrument symbol gates, effective BBO age from raw timestamp, expanded danger keys, BBO-stale precedence, raw/derived consistency gate, malformed-derived regressions.
- PA/E1 final review: PASS.
- E2/E4 final review: PASS.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py`: `15 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py helper_scripts/research/tests/test_cost_gate_bounded_probe_lower_price_reroute_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_order_construction_repair.py helper_scripts/research/tests/test_cost_gate_false_negative_bounded_probe_preflight.py helper_scripts/research/tests/test_cost_gate_bounded_probe_touchability_preflight.py helper_scripts/research/tests/test_cost_gate_bounded_probe_placement_repair_plan.py helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py`: `85 passed`.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_candidate_construction_preview.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py`: passed.
- `git diff --check`: passed.

## Aggressive Profit Hypotheses

1. `fresh_avax_near_touch_demo_probe`
   - `why_it_might_make_money`: AVAX remains rank-1 false-negative with `73.5511bps` after-cost historical cushion, and construction math fits the 10 USDT cap.
   - `fastest_safe_test`: Refresh read-only AVAX BBO snapshot and rerun no-order construction preview; only consider demo order admission if BBO age is <= `1000ms`.
   - `required_data`: fresh ticker row, instrument row, raw/derived consistency, fee/slippage controls, candidate-matched attribution fields.
   - `failure_condition`: stale BBO, spread widening, instrument not Trading, symbol mismatch, malformed snapshot, unmatched fills, or net PnL after fees/slippage failing matched controls.
   - `authority_required`: none for refresh/preview; demo order admission remains gated.
   - `max_safe_next_action`: `P0-BOUNDED-PROBE-REROUTE-FRESH-BBO-CONSTRUCTION-REFRESH-DEMO-ONLY`.
   - score: expected_net_pnl_upside 8, evidence_strength 7, execution_realism 7, cost_after_fees 8, time_to_test 7, risk_to_account 2, risk_to_governance 2, autonomy_value 9.

2. `freshness_latency_reduction_path`
   - `why_it_might_make_money`: The candidate is cap-feasible but stale snapshots block admission; reducing snapshot-to-preview latency can unlock bounded tests without changing risk limits.
   - `fastest_safe_test`: Generate market snapshot and construction preview in one read-only runtime command, still no order submission.
   - `required_data`: ticker timestamp, preview timestamp, BBO age distribution, command timing, raw/derived consistency.
   - `failure_condition`: effective BBO age remains > `1000ms` or requires service/runtime mutation.
   - `authority_required`: none for read-only artifact generation.
   - `max_safe_next_action`: source/read-only combined snapshot-preview packet.
   - score: expected_net_pnl_upside 6, evidence_strength 6, execution_realism 8, cost_after_fees 8, time_to_test 8, risk_to_account 1, risk_to_governance 1, autonomy_value 8.

3. `cap_preserving_alt_symbol_queue`
   - `why_it_might_make_money`: If AVAX freshness repeatedly fails, another cap-feasible false-negative candidate could provide similar upside without raising cap or lowering the global Cost Gate.
   - `fastest_safe_test`: Keep reroute review as the source of truth and refresh the false-negative queue only after a real evidence delta.
   - `required_data`: false-negative scorecard, instrument filters, fresh BBO, fees, spread, funding, matched controls.
   - `failure_condition`: lower-ranked candidates lose after-cost cushion or fail construction gates.
   - `authority_required`: none for queue refresh; later demo admission gated.
   - `max_safe_next_action`: do not reroute until AVAX fresh-BBO refresh is attempted or evidence changes.
   - score: expected_net_pnl_upside 6, evidence_strength 6, execution_realism 7, cost_after_fees 7, time_to_test 6, risk_to_account 2, risk_to_governance 2, autonomy_value 8.

## Status

`DONE_WITH_CONCERNS`.

AVAX construction is cap-feasible and review-chain aligned, but demo order admission is still blocked because the latest BBO evidence is stale.

## Why Not Repeating Current Blocker

The construction preview helper, tests, reviews, and latest runtime artifact are complete. Repeating this blocker without a fresh AVAX market snapshot would only regenerate another `CANDIDATE_CONSTRUCTION_BBO_STALE` packet. The next state transition is a fresh-BBO read-only refresh and preview rerun, not a new reroute review or order attempt.
