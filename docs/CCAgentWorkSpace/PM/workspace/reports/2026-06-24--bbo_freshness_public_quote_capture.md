# BBO Freshness Public Quote Capture

## Session Loop State

1. `active_blocker_id`: `P0-BOUNDED-PROBE-PUBLIC-QUOTE-ONE-SHOT-RUNTIME-REVIEW-DEMO-ONLY`
2. `blocker_goal`: Run exactly one reviewed public-market-data-only Bybit quote capture for the AVAXUSDT Sell bounded Demo candidate, producing a hashable artifact for later review and no order/probe/live authority.
3. `profit_relevance`: AVAX remains a cap-feasible high-upside false-negative candidate. A fresh public bid/ask capture could resolve the stale PG BBO blocker without lowering the Cost Gate.
4. `constraints_checked`: No global Cost Gate lowering; no live promotion; no private/auth endpoint; no Bybit order/cancel/modify; no PG write/query; no canonical plan/ledger mutation; no service/env/crontab/runtime mutation; no Rust writer; no probe/order/live authority; no promotion proof.
5. `previous_evidence_checked`: PG co-located runner artifact `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_colocated_runner_avax_sell_pg_readonly_20260624T185436Z.json` remained stale at `2476.128ms` vs `1000ms`. Latest reroute review `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_lower_price_reroute_review_latest.json` still selected `grid_trading|AVAXUSDT|Sell`.
6. `new_evidence_delta_required`: E3/BB-reviewed public quote capture source or one-shot artifact; not another PG stale run and not order admission.
7. `new_evidence_delta_found`: E3, BB, PA/E1, E2, and E4 all passed the bounded public-market-data-only envelope/source helper. Source commit `b66715bef256d5836f0db61c4183f9a63ffdfdd4` is pushed. One-shot public quote artifact was generated and failed closed at transport layer.
8. `anti_repeat_decision`: `PROCEED_WITH_REVIEWED_ONE_SHOT_PUBLIC_QUOTE_CAPTURE`; prior blocker had new source/review evidence and no previous one-shot public quote artifact.
9. `action_taken_or_noop_reason`: Added and reviewed `bbo_freshness_public_quote_capture.py`, committed/pushed it, then ran exactly one public-market-data capture attempt. No retry followed because the checkpoint was one-shot.

## Review Chain

E3 returned `DONE_WITH_CONCERNS` / `PASS` for the reviewed envelope only, not order admission. BB returned `DONE_WITH_CONCERNS` / `PASS`, saying ticker `bid1Price/ask1Price` is sufficient for this stale-BBO blocker, while orderbook would be needed only for stronger matching-engine timestamp evidence.

PA/E1 returned `DONE_WITH_CONCERNS` / `PASS` for a distinct public quote artifact contract, explicitly requiring the PG construction preview to stay strict. E2 and E4 both returned `DONE` / `PASS` after source implementation. E2 confirmed allowlists, fail-closed parse/freshness behavior, exact AVAX scope, authority preservation, and test coverage. E4 confirmed no safety blocker.

## Source Evidence

Source commit:

- branch `main`
- commit `b66715bef256d5836f0db61c4183f9a63ffdfdd4`
- pushed `origin/main`
- subject `Add public BBO quote capture helper [skip ci]`

Files:

- `helper_scripts/research/cost_gate_learning_lane/bbo_freshness_public_quote_capture.py`
- `helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py`
- `helper_scripts/SCRIPT_INDEX.md`

Helper contract:

- emits `bounded_probe_bbo_freshness_public_quote_capture_v1`
- allows only public market-data `GET /v5/market/time`, `GET /v5/market/tickers?category=linear&symbol=AVAXUSDT`, and optional `GET /v5/market/instruments-info?category=linear&symbol=AVAXUSDT`
- rejects wrong host/path/query/method, auth/cookie/X-BAPI headers, redirects, HTTP errors, malformed JSON, nonzero `retCode`, bad ticker rows, crossed/nonpositive BBO, stale/future timestamp, non-Trading/malformed instrument, and authority contamination
- records request envelope/timing/hash/provenance fields, parsed bid/ask/size, instrument filters, conservative freshness, artifact self-hash, and no-authority answers
- does not feed public quote artifacts into PG construction preview

Verification:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q -p no:cacheprovider helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py`: `11 passed`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q -p no:cacheprovider helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py helper_scripts/research/tests/test_cost_gate_bbo_freshness_colocated_runner.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py`: `41 passed`
- `python3 -m py_compile ...`: passed
- `git diff --check`: passed

## One-Shot Artifact

Artifact:

- JSON: `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_public_quote_capture_avax_sell_20260624T192038Z.json`
  - sha256 `6857deffd44a1e0fbaa4b370b5c8f4222c76886584a4c691750d52653cb2ce65`
  - artifact self-hash `5c52ee6e8f982d7ce38ee6eb62c804e2306dd521d682b73d8f1a01ec01a94559`
- Markdown: `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_public_quote_capture_avax_sell_20260624T192038Z.md`
  - sha256 `4a0d21334d273d11579c6ca32ad7bd45194d05ed01bc073cd67e409343439fcc`

Result:

- status `PUBLIC_QUOTE_CAPTURE_SOURCE_FAILURE_NO_ORDER`
- reason `public_quote_capture_failed_closed`
- blocking gates: `server_time_request_ok`, `ticker_request_ok`, `instrument_request_ok`, `transport_error:URLError`
- all three public GET attempts failed with `transport_error:URLError`
- no HTTP status, no retCode, no raw response hash, no normalized response hash
- no bid/ask, no spread, no effective BBO age
- next blocker in packet: `P0-BOUNDED-PROBE-PUBLIC-QUOTE-OUTCOME-REVIEW-DEMO-ONLY`, but PM re-routes to transport/runtime-route review because there is no quote outcome to review

Authority answers:

- `bybit_call_performed=true`
- `bybit_public_market_data_call_performed=true`
- `bybit_private_call_performed=false`
- `auth_headers_present=false`
- `private_endpoint_called=false`
- `pg_query_performed=false`
- `pg_write_performed=false`
- `order_submission_performed=false`
- `order_cancel_performed=false`
- `order_modify_performed=false`
- `runtime_mutation_performed=false`
- `main_cost_gate_adjustment=NONE`
- `probe_authority_granted=false`
- `order_authority_granted=false`
- `live_authority_granted=false`
- `promotion_evidence=false`

## Aggressive Profit Hypotheses

1. `runtime_host_public_quote_route`
   - `why_it_might_make_money`: Local desktop transport failed, but trade-core may have the correct network route to Bybit public market data. A fresh runtime-host quote could resolve BBO freshness without weakening the Cost Gate.
   - `fastest_safe_test`: PM->E3->BB review for fast-forwarding runtime to `b66715be` and running exactly one helper invocation from trade-core.
   - `required_data`: runtime source head, clean tree, request timing, raw response hashes, retCode/retMsg, bid/ask, instrument filters, no-authority answers.
   - `failure_condition`: runtime route also fails transport, response is stale/malformed, or any runtime mutation beyond approved source sync is required.
   - `authority_required`: PM->E3->BB before runtime source sync plus exchange-facing public call.
   - `max_safe_next_action`: `P0-BOUNDED-PROBE-PUBLIC-QUOTE-RUNTIME-ROUTE-E3-BB-REVIEW-DEMO-ONLY`.
   - scoring: `expected_net_pnl_upside=4`, `evidence_strength=2`, `execution_realism=3`, `cost_after_fees=3`, `time_to_test=4`, `risk_to_account=1`, `risk_to_governance=2`, `autonomy_value=4`.

2. `public_quote_transport_diagnostics_hardening`
   - `why_it_might_make_money`: If transport failure is local TLS/proxy/DNS rather than Bybit unavailability, better diagnostics prevents wasting future one-shot windows and makes the live-applicable capture route auditable.
   - `fastest_safe_test`: Source-only patch to record sanitized `URLError.reason` and response/socket class without secrets, with mocked tests only.
   - `required_data`: sanitized exception reason, no-auth/no-cookie proof, endpoint envelope, current failed artifact.
   - `failure_condition`: diagnostic details could leak secrets, require extra live calls, or still cannot distinguish DNS/TLS/proxy.
   - `authority_required`: source review only; no exchange call.
   - `max_safe_next_action`: source-only diagnostic patch if runtime-route review is not immediately available.
   - scoring: `expected_net_pnl_upside=2`, `evidence_strength=3`, `execution_realism=4`, `cost_after_fees=4`, `time_to_test=5`, `risk_to_account=1`, `risk_to_governance=1`, `autonomy_value=4`.

3. `alternate_cap_feasible_fresh_pg_candidate`
   - `why_it_might_make_money`: If public quote capture remains blocked, another false-negative candidate may have fresher PG BBO while preserving the same profit thesis and existing 10 USDT cap.
   - `fastest_safe_test`: Read-only reroute over cap-feasible false-negative candidates filtered by latest PG ticker lag and net after fees/slippage; produce one proposal only.
   - `required_data`: false-negative packet, instrument filters, PG ticker lag, net bps, sample counts, touchability/placement state.
   - `failure_condition`: lower edge, stale BBO, weak sample, or no exact candidate-match path.
   - `authority_required`: none for proposal; separate review before any order path.
   - `max_safe_next_action`: source/read-only alternate selection packet, no authority grant.
   - scoring: `expected_net_pnl_upside=3`, `evidence_strength=3`, `execution_realism=3`, `cost_after_fees=3`, `time_to_test=3`, `risk_to_account=1`, `risk_to_governance=1`, `autonomy_value=3`.

## Status

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-BOUNDED-PROBE-PUBLIC-QUOTE-RUNTIME-ROUTE-E3-BB-REVIEW-DEMO-ONLY`
13. `why_not_repeating_current_blocker`: The current blocker has new source review evidence and a dated one-shot artifact. Re-running the same local public quote attempt would violate the one-shot envelope and add no evidence delta.
14. `branch / commit SHA / push status / short description`: source branch `main`, source commit `b66715bef256d5836f0db61c4183f9a63ffdfdd4`, pushed to `origin/main`, added reviewed public BBO quote capture helper and tests. This report is docs-only follow-up.

