# P2 Incident-Policy Dispatch Trigger Checkpoint

> ticket: `P2-INCIDENT-POLICY-DISPATCH-TRIGGER`  
> date: 2026-06-12  
> scope: source-state reconciliation + focused verification; no CI, no deploy, no rebuild/restart

## Conclusion

The TODO row was stale. The ticket is not still "PA spec complete / pending implementation".

Current source already contains:

- CORE: `rust/openclaw_engine/src/notification_failsafe/incident_policy.rs`
  - class-level `IncidentClass`
  - sustained window / 5 minute throttle / 7 day cooling
  - push-secret gate that downgrades arm incidents to notify-only when Slack/Email push channels are not enabled
  - single armed owner guard
  - self-heal guard that only allows the currently armed class to send `AllSuccess`
- Auth producer: `rust/openclaw_engine/src/live_auth_watcher.rs`
  - reports `AuthInvalid`
  - reports resolution on recovery
- Bybit producer: `rust/openclaw_engine/src/bybit_rest_client.rs`
  - GET/POST retCode counter reports `BybitFailClosed`
  - success recovery reports resolution
- C4 E2E: `rust/openclaw_engine/src/event_consumer/tests/c4_failsafe_wire_tests.rs`
  - incident policy `AllFail` feeds watcher
  - watcher arms and claims timer
  - in-band `NotificationFailsafeEscalate` drives Demo SM-04 Defensive and stop-sync path

## Focused Verification

Mac local:

```bash
cargo test -p openclaw_engine notification_failsafe::incident_policy --lib
# 15 passed

cargo test -p openclaw_engine event_consumer::tests::c4_failsafe_wire_tests --lib
# 4 passed

cargo test -p openclaw_engine ret_code_counter --lib
# 6 passed
```

## Remaining Scope

This is not full fail-safe runtime completion yet.

Still pending:

- `sm_halt_stuck` producer coverage
- `position_drift` notify-only producer coverage
- external `engine_dead` watchdog notify-only path
- BB review for real set_trading_stop trigger frequency and Bybit safety
- E2/E4/QA full-chain review after producer coverage decision

## PM Decision

Update TODO from "pending implementation" to "CORE+auth+Bybit source-live / producer coverage partial".

Next recommended work is BB/E2 review of the existing CORE+auth+Bybit producer path before adding the remaining producer coverage, because this ticket turns C4 from dormant to real trigger surface for selected incidents.

## Boundaries

- No CI
- No deploy
- No rebuild/restart
- No DB migration or apply
- No auth/risk/trading mutation
