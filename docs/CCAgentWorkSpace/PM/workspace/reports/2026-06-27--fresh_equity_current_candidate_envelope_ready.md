# Fresh Equity Current-Candidate Envelope Ready

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0152Z_fresh_equity_current_candidate_envelope.json` |
| `session_loop_state_sha256` | `de7f953109f4b98c2933800fba04dde205bf263503f28c554f018c8ae4d1ad05` |
| `fresh_equity_artifact` | `/tmp/openclaw/gui_risk_cap_fresh_equity_refresh_20260627T0150Z/demo_account_equity_artifact_ready_candidate.json` |
| `fresh_equity_artifact_sha256` | `f66f7777b6d552b4542c3fbb6347ca0506807c4d22e1d14b1bee5545dac0966b` |
| `current_candidate_envelope` | `/tmp/openclaw/current_candidate_no_order_refresh_envelope_20260627T0152Z/current_candidate_no_order_refresh_envelope.json` |
| `current_candidate_envelope_sha256` | `6f853183d8dedc598f8d030e4babf1c48f9b7098f7e6123e2d31486d69ad9b36` |

## Decision

This round produced a fresh accepted Demo fast-balance equity artifact and regenerated the current-candidate no-order refresh envelope. It did not perform public quote capture or current construction refresh because the READY envelope still requires a separate PM -> E3 -> BB exchange-facing review before runtime invocation.

## Fresh Equity Artifact

The first runtime capture attempt used `http://127.0.0.1:8000` and correctly fail-closed:

- artifact: `/tmp/openclaw/gui_risk_cap_fresh_equity_refresh_20260627T0150Z/demo_account_equity_artifact.json`
- sha: `5dbdcb7a7d1607e6a48ea51bc15ce62ef412586703db7aac0fe208e4981d7535`
- status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_SOURCE_FAILURE_NO_AUTHORITY`
- reason: `demo_fast_balance_transport_failure`
- transport: connection refused

Read-only runtime diagnosis showed the Control API process was alive and listening on `100.91.109.86:8000`, not `127.0.0.1:8000`. The successful fixed GET used the approved helper base `http://100.91.109.86:8000` and the runtime 0600 token file.

Accepted artifact:

- generated: `2026-06-27T01:52:15.409890+00:00`
- status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`
- source: fixed Control API `GET /api/v1/strategy/demo/balance?fast=1`
- transport: HTTP `200`, authorization header used from token file
- `read_model=rust_snapshot_fast`
- `pipeline_status=connected`
- equity: `9552.43426257`
- all no-authority answers remain false for Bybit, PG, order, runtime mutation, probe/order/live authority, and proof.

## Current-Candidate Envelope

Inputs copied read-only from runtime:

- false-negative review sha `956cf84665c6b43be9ae95a6aeb0db5cbfa9c8b7acc6c28d8e5bcc346c0529b1`, candidate `grid_trading|AVAXUSDT|Sell`
- false-negative preflight sha `929c5b4ff71f9e5df2ebdc8217a12ffbb34f96c360635ecef085fa2c4e5086cf`, candidate `grid_trading|AVAXUSDT|Sell`
- bounded auth sha `3ecd400d72f45c5ef824fb04728907f7425f2c14fc57aaa7a152f651ee7fe8b5`, status `FALSE_NEGATIVE_PREFLIGHT_NOT_READY`, decision `defer`, candidate `grid_trading|AVAXUSDT|Sell`

Envelope result:

- status: `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY`
- candidate: `grid_trading|AVAXUSDT|Sell`
- accepted equity artifact age at generation: `43.401s`
- GUI P1 risk/trade: `10.0%`
- account equity: `9552.43426257`
- resolved per-order cap: `955.24342626 USDT`
- request count: `3`
- exact future public GET paths: `/v5/market/time`, `/v5/market/tickers?category=linear&symbol=AVAXUSDT`, `/v5/market/instruments-info?category=linear&symbol=AVAXUSDT`
- `network_call_performed=false`
- `public_quote_capture_performed=false`
- `order_admission_ready=false`

This confirms the operator correction in current evidence: GUI `10.0%` is the risk parameter, not a `10 USDT` single-order cap.

## Verification

- Runtime source remained at `665b2eef615cd1d93f0691a757f9ab4c3ade83ed`
- Runtime helper present: `demo_fast_balance_equity_artifact.py`
- Runtime API/watchdog processes were observed by `ps`: API parent PID `2218842`, watchdog PID `1538268`
- Runtime listener observed at `100.91.109.86:8000`
- Fresh equity artifact JSON parsed and status verified
- Current-candidate envelope JSON parsed and status verified

## Boundary

Performed only fixed Control API GET fast-balance read, read-only runtime diagnosis/artifact copy, and local no-order envelope generation. No public quote capture, Bybit private/order/cancel/modify call, PG query/write, Control API POST, service restart, cron run, runtime source sync, Cost Gate lowering, risk expansion, adapter/writer enablement, probe/order/live authority, or profit/proof claim.

## Next

Open the exact PM -> E3 -> BB review for no-order public quote/current-construction refresh using the READY envelope above. That review must still forbid private/auth/order paths, keep max BBO age `1000ms`, require adapter path+sha handoff, and produce fresh current candidate control/construction inputs before any bounded auth or execution path.
