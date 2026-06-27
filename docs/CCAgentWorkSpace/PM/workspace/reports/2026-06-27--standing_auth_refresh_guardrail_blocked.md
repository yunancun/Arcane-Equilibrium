# Standing Auth Refresh Guardrail Blocked

| Field | Value |
|---|---|
| `blocker_id` | `P0-CURRENT-CANDIDATE-STANDING-AUTH-REFRESH-GUARDRAIL` |
| `state_transition` | `BLOCKED_BY_LOSS_CONTROL` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T_standing_auth_refresh_guardrail/session_loop_state.json` |
| `session_loop_state_sha256` | `64825163e7863862af93adbd741e8a8d4e46919fc00c261a92e4dfa9efe595cd` |
| `round_summary` | `/tmp/openclaw/standing_auth_refresh_guardrail_20260627T1545Z/standing_auth_refresh_guardrail_round.json` |
| `round_summary_sha256` | `aa8981827e3e51a6b1538fd61cd4b4815cfa28a46541268c83df5541312fd005` |
| `standing_review` | `/tmp/openclaw/standing_auth_refresh_guardrail_20260627T1545Z/current_candidate_standing_demo_loss_control_envelope_review.json` |
| `standing_review_sha256` | `ac80af1aac23d4b37ccf94510d86436527ea47191b92a38d72c737003c700e81` |

## Decision

This round intentionally did not enter active lease, actual-admission BBO, writer/adapter, or order-capable paths. It checked whether the expired materialized standing Demo authorization could be refreshed from the latest available current-candidate evidence.

The refresh did not pass. The current-candidate standing review returned `CURRENT_CANDIDATE_STANDING_DEMO_LOSS_CONTROL_ENVELOPE_NOT_READY` because the false-negative candidate packet snapshot is stale:

- `false_negative_candidate_packet_artifact_not_fresh`
- `false_negative_candidate_packet_not_fresh`

Runtime `trade-core:/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json` still exists, but it is not valid for consumption:

- sha: `98766dfe06aa8bcbd86378faa7983b92b00ff8305faefba14303e62dd842f2f3`
- mode: `0600`
- candidate: `grid_trading|AVAXUSDT|Sell`
- embedded status: `STANDING_DEMO_AUTHORIZATION_ACTIVE`
- expiry: `2026-06-27T15:31:18.539071+00:00`
- checked after expiry, so `valid_for_consumption=false`

## GUI Risk Lineage

The fail-closed review still preserves the operator correction that GUI/Rust RiskConfig is the risk source of truth:

- GUI P1 risk/trade: `10.0%`
- `per_trade_risk_pct_fraction`: `0.1`
- accepted Demo equity: `9549.38926928`
- resolved per-trade/effective cap: `954.93892693 USDT`
- GUI max-single-position: `25.0%`
- single-position budget: `2387.34731732 USDT`
- proposed no-order shape: `144.0 AVAX / 954.576 USDT`
- local `10 USDT` authority: `false`

## Boundary

No runtime standing JSON write, env/crontab mutation, Decision Lease acquire/release, actual-admission BBO call, Bybit private call, order/cancel/modify, PG query/write, service restart, Cost Gate lowering, risk expansion, writer/adapter enablement, live/mainnet authority, fill, PnL, promotion proof, or profit proof occurred.

## Next

Refresh `false_negative_candidate_packet` in no-order/defer mode first. Then rerun `current_candidate_standing_demo_loss_control_envelope_review.py` with fresh source artifacts. Only if that review is `READY_NO_RUNTIME_MUTATION` may the `envelope_preview` be materialized to the reviewed runtime standing path. Any later order-capable Demo invocation still requires fresh same-window bounded authorization, active Decision Lease, Guardian/Rust authority, actual BBO, GUI cap, book-clean, auditability, and reconstructability gates.
