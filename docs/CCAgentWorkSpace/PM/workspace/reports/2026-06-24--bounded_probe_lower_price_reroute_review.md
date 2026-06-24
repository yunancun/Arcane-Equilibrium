# Bounded Probe Lower-Price Reroute Review

## Session Loop State

- `active_blocker_id`: `P0-BOUNDED-PROBE-LOWER-PRICE-CANDIDATE-REROUTE-REVIEW-DEMO-ONLY`
- `blocker_goal`: Select exactly one lower-price cap-feasible false-negative candidate from the order-construction repair packet and emit a no-authority candidate-specific reroute review packet for bounded Demo design.
- `profit_relevance`: BTC is not executable under the current 10 USDT cap. Rerouting to a cap-feasible high-edge false-negative candidate can create live-applicable bounded Demo evidence without raising cap or lowering the global Cost Gate.
- `completed_blockers`: includes `P0-BOUNDED-PROBE-CAP-AND-ORDER-CONSTRUCTION-REPAIR-DEMO-ONLY-SOURCE-PROPOSAL`.
- `previous_report_paths`:
  - `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--bounded_probe_order_construction_repair.md`
  - `docs/CCAgentWorkSpace/Operator/2026-06-24--bounded_probe_order_construction_repair.md`
- `source_head`: local/origin `535411717f2de87dadd52963a1ba903a6c4b3943`; runtime `trade-core` source `bdc1e1568431797cd1001e4484bf2da7ae6df7c4`.
- `runtime_timestamp`: runtime snapshot `2026-06-24T17:19:47Z`; final artifact refresh `2026-06-24T17:34Z`.
- `operator_action_required`: false for this review packet. The operator's Demo/testnet operational authorization is recorded, but live/mainnet, global Cost Gate lowering, Guardian/risk/Decision Lease/Rust-authority bypass, PG writes, service/crontab/runtime mutation, and Rust writer enablement remain excluded.
- `new_evidence_delta_required`: Fresh lower-price candidate artifacts or source-only reroute review packet; do not repeat BTC repair.
- `new_evidence_delta_found`:
  - repair latest points to `grid_trading|AVAXUSDT|Sell` as top cap-feasible false-negative candidate.
  - runtime artifacts for AVAX preflight, placement, authorization review, touchability, and authority readiness are fresh/aligned.
- `next_blocker_id`: `P0-BOUNDED-PROBE-REROUTE-CANDIDATE-CONSTRUCTION-PREFLIGHT-DEMO-ONLY`

## Anti-Repeat Decision

`PROCEED_SOURCE_ONLY`.

The prior blocker is complete. Repeating BTC order-construction repair would be stale work; this checkpoint advances the next state transition by selecting the AVAX lower-price reroute path.

## Source Changes

Added:

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_lower_price_reroute_review.py`
- `helper_scripts/research/tests/test_cost_gate_bounded_probe_lower_price_reroute_review.py`

The helper emits `bounded_demo_probe_lower_price_reroute_review_v1` and requires:

- a fresh `bounded_demo_probe_order_construction_repair_v1` with available lower-price reroute screen;
- exactly one explicit cap-feasible candidate when multiple feasible rows exist;
- candidate identity completeness: side-cell, strategy, symbol, side, and exact integer horizon;
- `instrument_status == "Trading"`;
- aligned fresh/schema-valid false-negative preflight, false-negative operator review, placement repair plan, operator authorization review packet, authority patch readiness, and touchability preflight;
- recursive no-authority/no-proof/no-mutation preservation;
- CLI input path/sha/mtime/size recording for reconstructability.

E2/E4 initially found fail-open issues: rounded horizon alignment, incomplete identity passing, non-Trading instruments passing when upstream marked `fits_current_cap=true`, and implicit row-order auto-selection. PM fixed all and added regressions.

## Runtime Artifact

- `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_lower_price_reroute_review_latest.json`
- sha256 `fcd7f92563dcb1384f6a35f98b6c38cdc21e612c0920e7e3e618aedb5ac3390b`
- schema `bounded_demo_probe_lower_price_reroute_review_v1`
- status `LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW`
- selected candidate `grid_trading|AVAXUSDT|Sell`
- blocking gates `0`

Selected candidate evidence:

- false-negative rank `1`
- friction rank `1`
- avg net `73.5511bps`
- net-positive `100.0%`
- outcomes `48`
- current cap `10.0 USDT`
- minimum executable notional `5.0 USDT`
- instrument status `Trading`

Aligned inputs:

- order construction repair sha `5a5940cf7b1a54ec80a188527fe36695a26454f0b4b14a7fa8e9027a0fda9040`
- false-negative preflight sha `e25a32286c675f4aab0ab6f4b6f7f3c894707f91b9ef38740e86238f1ca8da83`
- false-negative operator review sha `6cf31051702319bcf00d92720fdbdaaca52c7fe6f1f6864d8a0010d05059721a`
- placement repair plan sha `0101f0b8f43396bb4f80a4973171026b7b5fabdf645450396d2b020afe1683b9`
- operator authorization review sha `b727a700008f26e130099cabf60b59a8f9fedeade2ee4f2df1ecb7e925dd82fb`
- authority patch readiness sha `27f9cd6be6f3485104404d4bc08f7249cb21ec5973e04d19d57804dd6df56247`
- touchability preflight sha `8e9b06d135e3398f0c114eb3205e993af98e4b90e39b2a7ff5c8c9f1eb3e7b0f`

## Review Chain

- PM: implemented helper, runtime artifact generation, and docs.
- PA/E1: PASS. Confirmed exactly-one selection, no-authority/no-runtime mutation, live-applicable context preservation, and clear next action.
- E2/E4 initial review: FAIL. Found horizon, identity, non-Trading, and row-order selection fail-open issues.
- PM fixes: exact integer horizon gate, identity completeness gate, Trading-only feasibility, explicit selection requirement when multiple feasible candidates exist, and focused regressions.
- E2/E4 final review: PASS. No remaining findings.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_lower_price_reroute_review.py`: `11 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_order_construction_repair.py helper_scripts/research/tests/test_cost_gate_bounded_probe_lower_price_reroute_review.py helper_scripts/research/tests/test_cost_gate_false_negative_bounded_probe_preflight.py helper_scripts/research/tests/test_cost_gate_bounded_probe_touchability_preflight.py helper_scripts/research/tests/test_cost_gate_bounded_probe_placement_repair_plan.py helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py`: `70 passed`.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_lower_price_reroute_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_lower_price_reroute_review.py`: passed.
- `git diff --check`: passed.

## Aggressive Profit Hypotheses

1. `avax_candidate_specific_no_order_construction`
   - `why_it_might_make_money`: AVAX is rank-1 false-negative, fits the current cap, and retains `73.5511bps` after-cost historical cushion.
   - `fastest_safe_test`: Generate a candidate-specific no-order construction preview from fresh AVAX BBO/instrument filters; do not submit orders until preview passes.
   - `required_data`: fresh BBO, tick/qty/min-notional, maker/passive placement, fee/slippage assumptions, candidate-matched lineage fields.
   - `failure_condition`: stale BBO, spread/cost erases edge, not-Trading instrument, missing attribution, or unmatched fills.
   - `authority_required`: none for no-order preview; Demo order path uses existing Demo/testnet operational authorization only after construction gates pass.
   - `max_safe_next_action`: `P0-BOUNDED-PROBE-REROUTE-CANDIDATE-CONSTRUCTION-PREFLIGHT-DEMO-ONLY`.
   - score: expected_net_pnl_upside 8, evidence_strength 7, execution_realism 8, cost_after_fees 8, time_to_test 8, risk_to_account 2, risk_to_governance 2, autonomy_value 9.

2. `avax_vs_etc_control_pair`
   - `why_it_might_make_money`: ETC is also cap-feasible but weaker edge; using ETC as a matched control can separate symbol-specific edge from generic grid short behavior.
   - `fastest_safe_test`: Keep ETC as no-order control artifact only while AVAX receives construction preview.
   - `required_data`: same-cycle BBO/spread/funding, false-negative ranks, outcome samples, matched controls.
   - `failure_condition`: ETC becomes higher-quality after refresh or AVAX edge decays.
   - `authority_required`: none for control screen.
   - `max_safe_next_action`: add matched-control requirement to AVAX construction preflight.
   - score: expected_net_pnl_upside 5, evidence_strength 6, execution_realism 7, cost_after_fees 7, time_to_test 7, risk_to_account 1, risk_to_governance 1, autonomy_value 8.

3. `cap_preserving_false_negative_queue`
   - `why_it_might_make_money`: The system can avoid cap increases by routing only to false-negative candidates executable under current risk budget.
   - `fastest_safe_test`: Regenerate the lower-price reroute review whenever candidate universe or instrument filters change.
   - `required_data`: fresh scorecard, instrument filters, tickers, fees, spread/funding, and artifact hashes.
   - `failure_condition`: artifact stale/schema mismatch or top feasible candidates lose after-cost cushion.
   - `authority_required`: none for queue update.
   - `max_safe_next_action`: keep reroute review as the admission source for candidate-specific construction.
   - score: expected_net_pnl_upside 7, evidence_strength 6, execution_realism 8, cost_after_fees 7, time_to_test 8, risk_to_account 2, risk_to_governance 2, autonomy_value 9.

## Status

`DONE`.

The lower-price reroute review selected exactly one candidate, `grid_trading|AVAXUSDT|Sell`, and all review-chain gates are aligned with no authority/order/runtime mutation.

## Why Not Repeating Current Blocker

The lower-price reroute review latest is fresh, hashed, reviewed, and ready. Re-running this blocker without a new candidate universe, source HEAD, runtime artifact, or authorization delta would be `NO-OP_NO_EVIDENCE_DELTA`.
