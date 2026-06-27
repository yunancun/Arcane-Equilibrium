# Operator Note: Current Candidate Bounded Demo Admission Review

State transition: `BLOCKED_BY_LOSS_CONTROL`.

The GUI risk correction is now enforced in source and artifact checks:

- GUI `P1 Risk/Trade = 10.0%` means `per_trade_risk_pct=0.1`
- accepted Demo equity: `9552.43426257`
- resolved per-order cap: `955.24342626 USDT`
- constructed notional: `954.6264 USDT`
- local/bounded `10 USDT` is not runtime admission authority

Artifact:

- `/tmp/openclaw/current_candidate_bounded_demo_admission_envelope_review_20260627T023903Z/current_candidate_bounded_demo_admission_envelope_review.json`
- sha `34cd80461706cde2dad8bb5bff9b2d72224230452a2b6d989ee9ae1b6f4b224c`
- status `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL`
- candidate `grid_trading|AVAXUSDT|Sell`

Why blocked:

- runtime standing Demo authorization is scoped to `grid_trading|ETHUSDT|Buy`, not AVAX Sell
- no current AVAX bounded authorization object exists
- no Decision Lease exists for this admission
- no Guardian/risk gate pass exists
- no current Rust authority-path admission artifact was supplied
- actual admission still needs a fresh BBO refresh

This note does not authorize orders. `runtime_admission_ready=false` and `order_admission_ready=false` remain explicit. No Bybit call, private endpoint, order/cancel/modify, PG write, runtime mutation, Cost Gate change, bounded auth/probe/order/live authority, or profit proof occurred.
