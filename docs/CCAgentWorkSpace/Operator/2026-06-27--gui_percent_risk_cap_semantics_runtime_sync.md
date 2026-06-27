# Operator Note: GUI Percent Risk Cap Semantics Runtime Sync

State transition: `DONE_WITH_CONCERNS`.

Your correction is now enforced: GUI risk values are authoritative percentages. GUI `P1 Risk/Trade=10.0%` maps to Rust `per_trade_risk_pct=0.1`, not `10 USDT`. With accepted Demo equity `9552.43426257`, the current reviewed per-order cap is `955.24342626 USDT`.

Source/runtime commit:

- `2a7bfa5b603052638d35a20acf0516da752ca0db`

Runtime status:

- `trade-core` head is synced to `2a7bfa5b...`
- crontab expected-head pins updated: `11` replacements
- `openclaw-trading-api.service` is a user unit and was restarted to PID `3727506`
- watchdog remains active at PID `1538268`

Validation passed locally and on runtime. The co-located runner no longer defaults to `10 USDT`; it requires a positive GUI/Rust-resolved cap.

Remaining blockers before any execution:

- Decision Lease
- Guardian risk gate
- fresh actual-admission BBO

No order, writer/adapter enablement, plan mutation, Cost Gate change, live authority, active runtime probe/order authority, or profit proof occurred.
