# Operator Brief — P2 Incident-Policy Dispatch Trigger Checkpoint

2026-06-12 PM source-state check corrected a stale TODO row.

`P2-INCIDENT-POLICY-DISPATCH-TRIGGER` is no longer pure "待實作":

- CORE incident policy exists.
- Auth invalid/resolved producer exists.
- Bybit retCode fail-closed/resolved producer exists.
- C4 E2E exists for incident policy `AllFail` -> watcher timer -> Demo SM-04 Defensive.

Focused Mac and Linux Rust tests passed:

- incident_policy: 15 passed
- C4 failsafe wire: 4 passed
- ret_code_counter: 6 passed

Remaining gaps:

- `sm_halt_stuck`
- `position_drift`
- external watchdog `engine_dead` notify-only
- BB/E2/E4/QA full-chain review

No CI, no deploy, no rebuild/restart, no DB/auth/risk/trading mutation in this checkpoint.

## BB/E2 Review Update

2026-06-12 follow-up guest review:

- BB: `APPROVE-WITH-CONDITIONS`, 0 blocker/high/medium.
- E2: `PASS-WITH-CONDITIONS`, 0 blocker/high/medium/low.

Operational meaning:

- CORE+auth+Bybit producer path can continue development.
- Ticket is still partial, not runtime-complete.
- `bybit_fail_closed` means business-retCode fail-closed, not full exchange outage coverage.
- Exchange side effects still go only through C4 owner handler and existing `set_trading_stop` path.

Next development slice: remaining producer coverage, starting with `sm_halt_stuck`, then `position_drift` / `engine_dead` notify-only.
