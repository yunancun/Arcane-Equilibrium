# Operator Note: Current Candidate Standing Demo Loss-Control Envelope

State transition: `DONE_WITH_CONCERNS`.

Current AVAX standing loss-control envelope preview is ready, but it was not materialized to runtime.

Artifact:

- `/tmp/openclaw/current_candidate_standing_demo_loss_control_envelope_review_20260627T025157Z/current_candidate_standing_demo_loss_control_envelope_review.json`
- sha `c6970005efab04a9da02ce54b08c60e563e465fbf9c736e9767a3feabc978c03`
- status `CURRENT_CANDIDATE_STANDING_DEMO_LOSS_CONTROL_ENVELOPE_READY_NO_RUNTIME_MUTATION`
- candidate `grid_trading|AVAXUSDT|Sell`

Proposed standing envelope preview:

- `standing_demo_operator_authorization_v1`
- demo only
- candidate scoped to `grid_trading|AVAXUSDT|Sell`
- max authorized probe orders per candidate: `2`
- TTL: `12h`
- shared validator result: valid

Risk source remains GUI/Rust:

- GUI `P1 Risk/Trade = 10.0%` -> `per_trade_risk_pct=0.1`
- accepted Demo equity: `9552.43426257`
- resolved cap: `955.24342626 USDT`
- constructed notional: `954.6264 USDT`
- local/bounded `10 USDT` is not runtime cap authority

No runtime file write, env/crontab mutation, bounded auth object, Decision Lease, Guardian/Rust authority, order, PG write, Cost Gate change, live authority, or profit proof occurred.

Next safe step is reviewed runtime materialization of this standing envelope preview, then no-order refresh of false-negative preflight and bounded auth review.
