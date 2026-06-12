# P2 Incident-Policy Dispatch Trigger BB Review

STATUS: DONE_WITH_CONCERNS - CORE+auth+Bybit producer path is acceptable, but the ticket remains producer-coverage partial.

> date: 2026-06-12
> scope: read-only Bybit compatibility review for existing `incident_policy` CORE + `auth_invalid` + `bybit_fail_closed` producer path
> boundary: no private/signed/trading API calls, no deploy/rebuild/restart, no CI

## Verdict

**APPROVE-WITH-CONDITIONS** for continuing development on top of the current CORE+auth+Bybit path.

No BB blocker/high/medium finding for the reviewed source path.

Conditions:

- Do not mark `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` complete yet. `sm_halt_stuck`, `position_drift`, and external `engine_dead` producer coverage is still missing.
- Do not deploy/rebuild/restart this path as "runtime-complete" before E4/QA/full-chain review.
- Keep Bybit incident dispatch as notification/timer input only; all exchange stop side effects must continue to go through the C4 owner handler and existing `set_trading_stop` channel.

## Source Findings

The current production producer surface is narrow:

- `live_auth_watcher.rs` reports `IncidentClass::AuthInvalid` and resolution.
- `bybit_rest_client.rs` GET/POST reports `IncidentClass::BybitFailClosed` from the centralized retCode counter and reports stable recovery.
- No production producer currently reports `SmHaltStuck`, `PositionDrift`, or `EngineDead`.

The Bybit fail-closed source has bounded trigger frequency:

- 8 consecutive nonzero Bybit business retCodes, or 15 nonzero retCodes inside the 60s rolling window.
- Duplicate incident edges are suppressed while an incident is open.
- Recovery requires 3 consecutive successes and a cooled rolling window.
- `incident_policy` adds class-level 5m dispatch throttle, single armed owner, and 7d cooling after a timed-out incident resolves.

The reviewed path does **not** add a Bybit request at incident report time. It dispatches Slack/Email/banner notification first. Only if both push channels fail and the 1h C4 timer expires does the existing watcher send `NotificationFailsafeEscalate` into demo/live owner tasks.

The exchange write boundary remains the existing C4 path:

- watcher sends an in-band pipeline command;
- owner handler computes lock-profit `StopAdjustment`;
- server-side stop sync is sent through the existing `StopRequest` channel;
- the consumer side owns `PositionManager::set_trading_stop`;
- no market close, no open order, and no hidden retry is introduced by `incident_policy`.

BB's existing set-trading-stop safety assumptions still apply: wrong-side SL rejection is treated as an exchange rejection and recorded, not converted into a market close; paper is structurally excluded by the watcher loop and defensively short-circuited in the owner handler.

## Residual BB Concerns

1. `bybit_fail_closed` includes persistent client-fault retCodes such as invalid parameter/signature/rate-limit classes, not only venue-side faults. This is acceptable because the operator action is notification/fail-safe escalation, not retry; the report message carries retCode/path/window detail. Do not describe it as pure "exchange outage" coverage.
2. Transport/JSON parse/no-credentials errors are not counted by the retCode counter. This matches the current "retCode fail-closed" producer, but it is not complete Bybit availability coverage.
3. This review did not refresh current official Bybit docs/changelog because the current diff does not add or change a Bybit endpoint. A future endpoint/semantics change must use the normal BB official-doc refresh path.

## Evidence

Key local source anchors reviewed:

- `rust/openclaw_engine/src/notification_failsafe/incident_policy.rs`
- `rust/openclaw_engine/src/notification_failsafe/providers/single_watcher.rs`
- `rust/openclaw_engine/src/notification_failsafe/dispatchers/three_way.rs`
- `rust/openclaw_engine/src/tasks.rs`
- `rust/openclaw_engine/src/main_boot_tasks.rs`
- `rust/openclaw_engine/src/bybit_rest_client.rs`
- `rust/openclaw_engine/src/live_auth_watcher.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/notification_failsafe_escalate.rs`
- `rust/openclaw_engine/src/notification_failsafe/providers/exchange_stop_sync.rs`
- `rust/openclaw_engine/src/event_consumer/tests/c4_failsafe_wire_tests.rs`
- `rust/openclaw_engine/src/bybit_rest_client_tests.rs`

Focused verification already recorded in the PM checkpoint:

```bash
cargo test -p openclaw_engine notification_failsafe::incident_policy --lib
# 15 passed

cargo test -p openclaw_engine event_consumer::tests::c4_failsafe_wire_tests --lib
# 4 passed

cargo test -p openclaw_engine ret_code_counter --lib
# 6 passed
```

Mac and Linux both passed those focused suites at the source-state checkpoint.

## BB Decision

BB has no objection to moving next into the remaining producer coverage design/implementation, provided this ticket stays labeled partial until `sm_halt_stuck`, `position_drift`, and `engine_dead` are explicitly wired or explicitly scoped out by PM/PA.
