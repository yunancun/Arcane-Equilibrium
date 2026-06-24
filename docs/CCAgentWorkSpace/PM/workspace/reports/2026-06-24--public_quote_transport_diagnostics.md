# Public Quote Transport Diagnostics

## Session Loop State

1. `active_blocker_id`: `P0-BOUNDED-PROBE-PUBLIC-QUOTE-TRANSPORT-DIAGNOSTICS-SOURCE-ONLY-DEMO-ONLY`
2. `blocker_goal`: Improve the public BBO quote capture failure artifact so transport failures are sanitized, diagnosable, and reconstructable before any runtime-host route or repeated public quote call.
3. `profit_relevance`: The AVAXUSDT Sell false-negative candidate remains blocked by missing fresh BBO evidence. Diagnosable transport failures help distinguish local route/DNS/TLS/proxy issues from strategy or market-data freshness blockers without weakening Cost Gate or order gates.
4. `constraints_checked`: No global Cost Gate lowering; no live promotion; no private/auth endpoint; no Bybit order/cancel/modify; no Bybit call in this checkpoint; no PG read/write; no canonical plan/ledger mutation; no service/env/crontab/runtime mutation; no Rust writer; no probe/order/live authority; no promotion proof.
5. `previous_evidence_checked`: Previous public quote artifact `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_public_quote_capture_avax_sell_20260624T192038Z.json` failed closed with generic `transport_error:URLError` on all three public GETs and no HTTP status, retCode, raw response hash, or BBO age. Runtime checkout was not available from the desktop context, so local one-shot repeat was rejected by anti-repeat.
6. `new_evidence_delta_required`: Source-only diagnostic delta that preserves fail-closed behavior and redacts sensitive material; or an E3/BB-reviewed runtime-host route before any repeated public quote call.
7. `new_evidence_delta_found`: Source commit `37a0315419454c8bb82e666451423e155760c37e` adds sanitized transport diagnostics for public quote capture failures.
8. `anti_repeat_decision`: `PROCEED_SOURCE_ONLY_DIAGNOSTICS_DELTA`; do not rerun the local one-shot artifact and do not attempt runtime-host source sync or public quote call without E3/BB review.
9. `action_taken_or_noop_reason`: Added source/test diagnostics only. The helper now records `transport_error_class`, `transport_error_reason_type`, `transport_error_reason_sanitized`, `transport_error_errno`, `transport_error_stage`, and `transport_error_sanitized` on the exception path while preserving `error=transport_error:<ExceptionClass>`.

## Source Evidence

Source commit:

- branch `main`
- commit `37a0315419454c8bb82e666451423e155760c37e`
- subject `Add public quote transport diagnostics [skip ci]`

Changed files:

- `helper_scripts/research/cost_gate_learning_lane/bbo_freshness_public_quote_capture.py`
- `helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py`

Diagnostic contract:

- preserves existing `transport_error:<ExceptionClass>` taxonomy
- keeps transport failures fail-closed as `PUBLIC_QUOTE_CAPTURE_SOURCE_FAILURE_NO_ORDER`
- records class, reason type, sanitized reason, errno, stage, and sanitized flag only for transport exceptions
- redacts bearer/auth material, env-style secrets, cookies including comma/semicolon cases, DSNs/URLs, local paths, and tracebacks
- preserves only `https://api.bybit.com` public market-data paths in diagnostics, stripped to scheme+host+path
- does not add endpoints, retries, timeout widening, auth/private headers, PG behavior, order behavior, runtime mutation, or Cost Gate/probe/order/live authority

Verification:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q -p no:cacheprovider helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py`: `15 passed`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q -p no:cacheprovider helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py helper_scripts/research/tests/test_cost_gate_bbo_freshness_colocated_runner.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py`: `45 passed`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bbo_freshness_public_quote_capture.py helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py`: passed
- `git diff --check`: passed

## Review Chain

PA/E1 source-contract review passed before implementation with the requirement that transport diagnostics remain sanitized, no-authority, and source-only.

E2 initially failed the sanitizer because env-style secrets, bare DSNs, multi-cookie values, and broader local paths could leak. PM fixed these gaps, added regressions, then E2 found a remaining comma-cookie and diagnostic demo-host preservation concern. PM fixed those too. Final E2 returned `DONE` / `PASS`.

E4 returned `DONE` / `PASS`, confirming tests are mocked-only, diagnostics are additive, transport failures still fail closed, no-authority answers are covered, and public quote artifacts remain rejected as PG construction-preview proof/input.

E3/BB are still required before any runtime-host invocation, source sync, or repeated Bybit public quote call.

## Aggressive Profit Hypotheses

1. `runtime_host_public_quote_route`
   - `why_it_might_make_money`: Local desktop transport failed, but trade-core may have the correct Bybit public route and fresher network proximity, allowing AVAX BBO freshness proof without weakening Cost Gate.
   - `fastest_safe_test`: PM->E3->BB review for fast-forwarding runtime to the reviewed source and running exactly one public quote helper invocation from trade-core.
   - `required_data`: runtime source head, clean tree, request timing, retCode/retMsg, raw response hashes, bid/ask, instrument filters, sanitized transport diagnostics, no-authority answers.
   - `failure_condition`: runtime route also fails transport, response is stale/malformed, or any runtime mutation beyond approved source sync is required.
   - `authority_required`: PM->E3->BB before runtime source sync or public market-data call.
   - `max_safe_next_action`: `P0-BOUNDED-PROBE-PUBLIC-QUOTE-RUNTIME-ROUTE-E3-BB-REVIEW-DEMO-ONLY`.
   - scoring: `expected_net_pnl_upside=4`, `evidence_strength=3`, `execution_realism=3`, `cost_after_fees=3`, `time_to_test=4`, `risk_to_account=1`, `risk_to_governance=2`, `autonomy_value=4`.

2. `alternate_cap_feasible_fresh_pg_candidate`
   - `why_it_might_make_money`: If AVAX remains blocked by quote route, another false-negative candidate may preserve high net bps while having fresh PG BBO under the same 10 USDT cap.
   - `fastest_safe_test`: Read-only candidate reroute over cap-feasible false-negative rows filtered by latest PG ticker lag and current net-after-fees score; emit one proposal only.
   - `required_data`: false-negative packet, instrument filters, PG ticker lag, net bps, sample counts, touchability/placement state.
   - `failure_condition`: lower edge, stale BBO, weak sample, or no exact candidate-match path.
   - `authority_required`: none for source/read-only proposal; separate review before any order path.
   - `max_safe_next_action`: source/read-only alternate selection packet with no authority grant.
   - scoring: `expected_net_pnl_upside=3`, `evidence_strength=3`, `execution_realism=3`, `cost_after_fees=3`, `time_to_test=3`, `risk_to_account=1`, `risk_to_governance=1`, `autonomy_value=3`.

3. `quote_route_cost_reduction_surface`
   - `why_it_might_make_money`: Better quote freshness can reveal whether maker/passive placement is feasible near touch, improving maker ratio and realized cost after fees/slippage without lowering the global Cost Gate.
   - `fastest_safe_test`: After reviewed runtime quote route, compare effective BBO age and spread against construction-preview placement math; no order admission unless all existing gates pass.
   - `required_data`: fresh public quote artifact, construction preview, instrument filters, fee schedule assumptions, no-authority answers.
   - `failure_condition`: quote age remains stale, spread too thin after fees, or route evidence cannot be reconstructed.
   - `authority_required`: E3/BB for quote route, then normal bounded probe review chain.
   - `max_safe_next_action`: reviewed quote-route artifact only.
   - scoring: `expected_net_pnl_upside=3`, `evidence_strength=2`, `execution_realism=3`, `cost_after_fees=4`, `time_to_test=3`, `risk_to_account=1`, `risk_to_governance=2`, `autonomy_value=4`.

## Status

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-BOUNDED-PROBE-PUBLIC-QUOTE-RUNTIME-ROUTE-E3-BB-REVIEW-DEMO-ONLY`
13. `why_not_repeating_current_blocker`: The prior one-shot artifact already failed locally. This checkpoint adds source-level diagnostic evidence; repeating the same local public quote call before runtime-route review would add no evidence delta and would violate the anti-repeat rule.
14. `branch / commit SHA / push status / short description`: source branch `main`, source commit `37a0315419454c8bb82e666451423e155760c37e`; push status recorded in the final PM handoff after docs commit/push. Short description: sanitized public quote transport diagnostics and mocked regressions.
