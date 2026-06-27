# Operator Note: GUI Cap Touchability / Placement Refresh

State transition: `DONE_WITH_CONCERNS`.

The stale `10.0` placement cap has been removed from the review chain. The new no-order placement artifact uses the GUI/Rust cap:

- `max_demo_notional_usdt_per_order=955.24342626 USDT`
- GUI `P1 Risk/Trade=10.0%` -> `per_trade_risk_pct=0.1`
- `local_10_usdt_cap_is_global_risk_authority=false`

New artifact statuses:

- Touchability: `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED`
- Placement: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- Readiness: `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- Bounded auth: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, `decision=defer`, `blocking_gates=[]`

No bounded auth object, active probe/order authority, Decision Lease, Guardian/Rust admission, order, Cost Gate change, live authority, or profit proof was created.

Next safe step: separately review whether to emit a scoped bounded auth object from the valid standing Demo authorization. Execution still requires Decision Lease, Guardian gate, Rust authority admission, fresh actual-admission BBO, auditability, and reconstructability.
