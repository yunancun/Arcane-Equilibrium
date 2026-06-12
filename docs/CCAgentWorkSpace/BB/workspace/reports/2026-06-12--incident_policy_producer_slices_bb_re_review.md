# P2 Incident-Policy Producer Slices BB Focused Re-Review

STATUS: DONE - APPROVE_WITH_CONDITIONS. Reviewed Bybit/exchange surface of `sm_halt_stuck`, `position_drift`, and external `engine_dead`; no blocker/high/medium finding.

> date: 2026-06-12
> scope: Bybit compatibility and exchange-side safety review for newly added incident-policy producer slices
> boundary: no private/signed/trading API calls, no CI, no deploy/rebuild/restart

## Verdict

**APPROVE-WITH-CONDITIONS**.

The new producer slices do not add a new Bybit endpoint, order path, market close path, or direct `set_trading_stop` call.

Conditions:

- Do not describe `engine_dead` as a Bybit/exchange outage detector; it is engine heartbeat/respawn failure notification.
- Do not describe `position_drift` as an exchange-side remediation; it is notify-only observation over reconciler residual drift.
- Keep all exchange stop side effects behind the existing C4 watcher -> owner handler -> `StopRequest` -> `PositionManager::set_trading_stop` path.
- Any future producer change that adds or changes a Bybit API request must use the normal BB official-doc refresh path.

## Slice Review

### `sm_halt_stuck`

BB has no Bybit compatibility objection.

The producer observes local pipeline halt state and reports `IncidentClass::SmHaltStuck`. It does not call Bybit. If the class eventually arms C4, the exchange-facing operation is still the previously reviewed C4 owner path, not a new producer-side exchange write.

Residual caveat: this is an arm-class incident, so E4/QA must still verify the integrated path under push-channel failure before runtime deployment.

### `position_drift`

BB has no Bybit compatibility objection.

The producer itself does not add a request. It consumes residual drift already produced by the reconciler. The reconciler may depend on existing Bybit position reads, but this slice only adds notify-only reporting after existing reconciliation handling; it does not add endpoint fanout, retries, position mutation, order placement, or stop sync.

Residual caveat: wording must preserve the source of truth. `position_drift` means unresolved local-vs-exchange reconciliation residuals; it is not proof that Bybit rejected or accepted any new action.

### `engine_dead`

BB has no Bybit compatibility objection.

The producer is watchdog-side and uses snapshot age plus failed respawn state. It does not call Bybit, consume Bybit auth, or mutate exchange state. `network_outage` is explicitly excluded before this producer runs.

Residual caveat: `engine_dead` can coexist with external network symptoms, but the implemented gate intentionally refuses the `network_outage` branch. Keep that distinction visible in operator text.

## Evidence

Source anchors reviewed:

- `rust/openclaw_engine/src/event_consumer/sm_halt_incident.rs`
- `rust/openclaw_engine/src/position_reconciler/incident.rs`
- `rust/openclaw_engine/src/notification_failsafe/incident_policy.rs`
- `rust/openclaw_engine/src/event_consumer/tests/c4_failsafe_wire_tests.rs`
- `helper_scripts/canary/engine_dead_incident.py`
- `helper_scripts/canary/engine_watchdog.py`

Focused verification observed:

```bash
cd rust && cargo test -p openclaw_engine sm_halt_incident --lib
# 5 passed

cd rust && cargo test -p openclaw_engine position_reconciler::incident --lib
# 6 passed

cd rust && cargo test -p openclaw_engine notification_failsafe::incident_policy --lib
# 15 passed

cd rust && cargo test -p openclaw_engine event_consumer::tests::c4_failsafe_wire_tests --lib
# 4 passed

python3 -m pytest helper_scripts/canary/test_canary.py -k 'engine_dead or WatchdogAlertWiring' -q
# 5 passed, 82 deselected
```

## BB Decision

BB clears the new producer slices for E4/QA/full-chain review. No additional Bybit docs lookup was required because this diff does not add or alter a Bybit endpoint or exchange semantics.
