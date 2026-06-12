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
