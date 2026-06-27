# Operator Note: Current Candidate Active Decision Lease Gate Window

Date: 2026-06-27

Result: `BLOCKED_BY_LOSS_CONTROL`

The active Decision Lease gate was validated for the current AVAX Sell candidate under a bounded no-order Demo lease window. The helper acquired `lease:caa9dcc3fac8`, evaluated runtime governance while the lease was active, and released it successfully before writing the final artifact.

The remaining blocker is Guardian `CAUTIOUS` (`guardian_risk_state_not_normal`) with a `reconciler_drift` transition tail. Post-run governance confirms no active lease remains: `lease_live_count=0`, `list_leases=[]`.

Risk cap semantics remain GUI-sourced:

- GUI `P1 Risk/Trade=10.0%` = `955.24342626 USDT` cap from accepted Demo equity, not `10 USDT`.
- GUI `Max Single Position=25%` = `2388.10856564 USDT` exposure budget.
- Current effective single-order cap = `668.67039838 USDT`.

No order, Bybit private/order call, PG write, Cost Gate lowering, live/mainnet authority, runtime execution, or profit proof occurred.

Artifacts:

- `/tmp/openclaw/current_candidate_active_decision_lease_gate_window_20260627T070600Z/current_candidate_active_decision_lease_gate_window.json`
- sha256 `dfcf9152f78ed2b6f1370ebc73b7e5a9cfa6d041941df952279525f239e296a0`
- post-run snapshot sha256 `973da8c9e9a24e3987c76fbafaba72eac58f9a5c5533bd0a01d6c5468fdef0d2`
