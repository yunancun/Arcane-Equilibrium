# Public Quote Market Snapshot Adapter

## Session Loop State

1. `active_blocker_id`: `P0-PUBLIC-QUOTE-MARKET-SNAPSHOT-ADAPTER-SOURCE-ONLY-DEMO-ONLY`
2. `blocker_goal`: Convert a reviewed no-authority public quote capture into a construction-preview market snapshot without admitting raw public quote artifacts or forged snapshots.
3. `profit_relevance`: The AVAXUSDT Sell false-negative candidate needs fresh BBO and current instrument filters before any bounded Demo order-admission review. The adapter removes the stale PG-snapshot dependency while preserving audit/reconstructability and hard authority gates.
4. `constraints_checked`: No global Cost Gate lowering; no live/mainnet promotion; no private/auth endpoint; no Bybit order/cancel/modify; no Bybit call in this source checkpoint; no PG query/write; no canonical plan/ledger mutation; no service/env/crontab/runtime mutation; no Rust writer; no probe/order/live authority; no promotion proof.
5. `previous_evidence_checked`: Runtime public quote capture on `trade-core` reached `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER` with three public requests and no authority flags, but the existing PG construction path remained `CANDIDATE_CONSTRUCTION_BBO_STALE`. The public quote artifact became stale before a construction preview could consume it safely.
6. `new_evidence_delta_required`: A source-only adapter contract that allows only reviewed public quote artifacts to become `bounded_probe_candidate_market_snapshot_v1`, with provenance, no-authority contamination checks, cap/gate preservation, and forged-snapshot fail-closed behavior.
7. `new_evidence_delta_found`: Added `public_quote_market_snapshot_adapter.py`, updated construction preview to accept only exact adapter snapshots with valid provenance, and added regression coverage for contamination, candidate mismatch, stale/gate widening, cap widening, direct CLI execution, and forged adapter snapshots.
8. `anti_repeat_decision`: `PROCEED_SOURCE_ONLY_ADAPTER_DELTA`; do not repeat the stale public quote or PG construction runner. The prior runtime quote is already too old for BBO freshness proof.
9. `action_taken_or_noop_reason`: Implemented the smallest source-only bridge needed for the next fresh runtime quote to flow into construction preview, while preserving all order/risk/authority boundaries.

## Source Evidence

Changed files:

- `helper_scripts/research/cost_gate_learning_lane/public_quote_market_snapshot_adapter.py`
- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_candidate_construction_preview.py`
- `helper_scripts/research/tests/test_public_quote_market_snapshot_adapter.py`
- `helper_scripts/SCRIPT_INDEX.md`

Adapter contract:

- input quote schema/status must be `bounded_probe_bbo_freshness_public_quote_capture_v1` / `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`
- reroute review must be `bounded_demo_probe_lower_price_reroute_review_v1` / `LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW`
- candidate identity must match exactly
- BBO must be fresh at adapter generation and use the quote artifact's own freshness gate
- adapter cap is derived from `selected_candidate.current_cap_usdt`; caller cap widening is rejected
- public quote freshness gate widening is rejected
- quote and reroute payloads must match the supplied artifact paths and hashes
- recursive authority/mutation contamination in both quote and reroute artifacts is rejected
- adapter output answers record no Bybit call, no PG query/write, no order/cancel/modify, no runtime mutation, Cost Gate `NONE`, and no probe/order/live/promotion authority
- construction preview rejects raw public quote artifacts and forged adapter snapshots

Verification:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q -p no:cacheprovider helper_scripts/research/tests/test_public_quote_market_snapshot_adapter.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py`: `39 passed`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q -p no:cacheprovider helper_scripts/research/tests/test_public_quote_market_snapshot_adapter.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py helper_scripts/research/tests/test_cost_gate_bbo_freshness_colocated_runner.py helper_scripts/research/tests/test_cost_gate_bounded_probe_lower_price_reroute_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_order_construction_repair.py`: `74 passed`
- `python3 -m py_compile` on changed source/test files: passed
- `git diff --check`: passed
- direct script help with `PYTHONPATH=helper_scripts/research`: passed

## Review Chain

PA/E1 source-contract review approved the adapter shape only if it acted as a public-quote review gate, not a dumb transformer.

E2 passed the implementation and later re-reviewed the cap/freshness-gate hardening. E2's residual programmatic path/payload concern was closed by requiring supplied payloads to match their artifact paths.

E4 initially failed the implementation because a forged adapter snapshot could widen `cap_usdt` or widen a stricter public quote freshness gate. PM fixed both by deriving cap and freshness gate from reviewed artifacts and adding construction-preview provenance checks. E4 re-review passed.

E3/BB are still required before any runtime source sync, repeated public quote call, or runtime-host invocation.

## Aggressive Profit Hypotheses

1. `fresh_public_quote_to_immediate_adapter_preview`
   - `why_it_might_make_money`: The AVAX false-negative candidate has strong historical net bps but is blocked by stale BBO. A runtime-host fresh public quote followed immediately by adapter + construction preview can test whether current maker placement is feasible without waiting for stale PG snapshots.
   - `fastest_safe_test`: E3/BB-reviewed runtime sync to this commit, exactly one public market-data quote capture, immediate adapter generation, and construction preview.
   - `required_data`: fresh public quote artifact, reroute review artifact, adapter snapshot, construction preview, no-authority answers, path/sha provenance.
   - `failure_condition`: quote stale by the time adapter/preview runs, instrument not Trading, cap/min-notional infeasible, or any authority/mutation contamination.
   - `authority_required`: PM->E3->BB for runtime source sync and public quote call.
   - `max_safe_next_action`: reviewed runtime route packet only; no order/probe authority.
   - scoring: `expected_net_pnl_upside=4`, `evidence_strength=3`, `execution_realism=4`, `cost_after_fees=4`, `time_to_test=4`, `risk_to_account=1`, `risk_to_governance=2`, `autonomy_value=4`.

2. `lower_price_false_negative_symbol_rotation`
   - `why_it_might_make_money`: If AVAX remains freshness-blocked, another low-price false-negative side-cell may preserve positive net bps and pass cap/min-notional/fresh-BBO gates faster.
   - `fastest_safe_test`: Source/read-only candidate rotation packet over false-negative candidates with current cap feasibility, ticker freshness, and clean attribution requirements.
   - `required_data`: false-negative scorecard, instrument filters, ticker freshness, sample count, net bps, touchability/placement artifacts.
   - `failure_condition`: weaker edge, stale BBO, no exact candidate-match path, or insufficient sample strength.
   - `authority_required`: none for source-only proposal; bounded probe review still required before orders.
   - `max_safe_next_action`: proposal packet only.
   - scoring: `expected_net_pnl_upside=3`, `evidence_strength=3`, `execution_realism=3`, `cost_after_fees=3`, `time_to_test=3`, `risk_to_account=1`, `risk_to_governance=1`, `autonomy_value=3`.

3. `maker_ratio_microstructure_probe_design`
   - `why_it_might_make_money`: Near-touch post-only placement with fresh BBO can preserve maker economics and reduce fee/slippage drag for low-notional bounded Demo probes.
   - `fastest_safe_test`: Use adapter-backed construction previews to compare passive distance, spread, min notional, and fill realism before any order path.
   - `required_data`: fresh BBO, bid/ask sizes, spread bps, instrument filters, fee assumptions, matched controls.
   - `failure_condition`: spread too tight after fees, repeated stale quote, or post-only placement would cross.
   - `authority_required`: source-only for design; E3/BB plus bounded order-admission chain before any exchange action.
   - `max_safe_next_action`: construction-preview evidence only.
   - scoring: `expected_net_pnl_upside=3`, `evidence_strength=2`, `execution_realism=4`, `cost_after_fees=4`, `time_to_test=3`, `risk_to_account=1`, `risk_to_governance=2`, `autonomy_value=4`.

## Status

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-PUBLIC-QUOTE-ADAPTER-RUNTIME-SYNC-AND-FRESH-QUOTE-E3-BB-REVIEW-DEMO-ONLY`
13. `why_not_repeating_current_blocker`: The source adapter contract is complete and reviewed. Re-running the already-stale runtime quote or PG construction path would add no new evidence delta; the next evidence must be a fresh E3/BB-reviewed runtime quote routed through the adapter immediately.
14. `branch / commit SHA / push status / short description`: branch `main`; commit and push status are recorded in final PM handoff after this report is committed. Short description: source-only public quote market snapshot adapter with provenance, cap/gate preservation, no-authority contamination checks, and forged-snapshot fail-closed regressions.
