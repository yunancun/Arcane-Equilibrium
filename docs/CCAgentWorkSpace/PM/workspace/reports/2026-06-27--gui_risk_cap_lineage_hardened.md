# GUI Risk Cap Lineage Hardened

Generated: 2026-06-27T09:05:40Z

## State Transition

`DONE_WITH_CONCERNS`

## Source Change

Source commit `da72439d66dd61bd6948389a2af762895d606606` hardens the GUI/Rust RiskConfig cap lineage after the operator correction that GUI `P1 Risk/Trade=10.0%` is a percentage (`per_trade_risk_pct=0.1`), not a fixed `10 USDT` cap.

The change keeps GUI/Rust RiskConfig as the source of truth and carries the full budget lineage through the current-candidate no-order chain:

- `per_trade_budget_usdt`
- `single_position_budget_usdt`
- `max_order_notional_usdt`
- `effective_single_order_cap_usdt`
- stale-local-`10 USDT` mismatch blockers before Decision Lease acquire or public quote calls

## Verification

- Focused cap/admission suite: `25 passed in 0.19s`
- Adjacent GUI-cap/sizing/gate/admission suite: `80 passed in 0.26s`
- `python3 -m py_compile`: passed
- `git diff --check`: passed

## Runtime Boundary

No order, Bybit private/order call, public quote capture, PG write, runtime mutation, service restart, Cost Gate change, live/mainnet authority, execution, or profit proof occurred.

## Remaining Concern

The runtime admission loop remains blocked on fresh Demo equity source. Latest accepted blocker is still `/tmp/openclaw/current_candidate_actual_bbo_fresh_equity_datadir_20260627T084723Z/demo_account_equity_artifact.json` sha `5df49e017fa821fa9a22f57733f1cd9e7b26ae261f57fb4451715ea104329665`, status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_NOT_READY_NO_AUTHORITY`, with `pipeline_status=disconnected`, `read_model=null`, and `balance=null`.

Session state: `/tmp/openclaw/session_loop_state_20260627T090540Z_gui_risk_cap_lineage_hardened/session_loop_state.json` sha `53baf8084f6db8a47a0d8d3abfa54b10a6ce97c27c83e0a768c93811b5769bfb`.
