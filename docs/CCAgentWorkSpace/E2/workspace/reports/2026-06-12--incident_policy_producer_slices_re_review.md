# P2 Incident-Policy Producer Slices E2 Focused Re-Review

STATUS: DONE - PASS_WITH_CONDITIONS. Reviewed `sm_halt_stuck`, `position_drift`, and external `engine_dead` producer slices; no blocker/high/medium/low finding.

> date: 2026-06-12
> scope: adversarial source review of newly added incident-policy producer slices after prior CORE/auth/Bybit review
> boundary: no CI, no deploy/rebuild/restart, no DB/auth/order/risk/trading mutation

## Verdict

**PASS-WITH-CONDITIONS**.

The planned producer coverage is source-live and internally consistent with the existing incident-policy model:

- arm classes remain `auth_invalid`, `bybit_fail_closed`, and `sm_halt_stuck`;
- notify-only classes remain `position_drift` and `engine_dead`;
- only the existing `incident_policy` + C4 watcher path can feed `AllFail`;
- external watchdog `engine_dead` does not enter Rust C4 and cannot arm Defensive.

Conditions:

- Do not claim runtime completion until E4/QA/full-chain review covers the integrated arm path.
- Keep deploy/rebuild/restart operator-gated.
- Preserve the current push-channel gate: arm classes must downgrade to notify-only when Slack/Email push channels are not both enabled.
- Preserve the external-watchdog boundary for `engine_dead`; changing it to Defensive automation requires a separate reviewed watchdog-side design.

## Slice Checks

### `sm_halt_stuck`

Passed:

- Producer reads only existing `TickPipeline` halt state: `halt_kind`, `halt_set_ts_ms`, `paper_paused`, and `session_halted`.
- It does not read stale passive selector `[69]`.
- It emits `IncidentClass::SmHaltStuck` through `incident_policy::spawn_report_incident(...)`, not by directly touching C4 watcher state.
- Local producer cadence is 5s, while the authoritative sustained window remains the incident-policy class window of 120s.
- Halt clear emits class-scoped `report_resolved(IncidentClass::SmHaltStuck)`.
- No direct `RiskGovernor`, order, auth, DB, exchange, or `set_trading_stop` write is introduced.

### `position_drift`

Passed:

- Producer observes after orphan/ghost handling and action dispatch, before baseline update, so it represents remaining unresolved drift.
- `MinorDrift` is ignored.
- Actionable drift requires the existing `PERSISTENT_DRIFT_CYCLES=3`.
- Startup grace clears producer state and does not accumulate hidden streak.
- `IncidentClass::PositionDrift` is policy-level `NotifyOnly`; the focused incident-policy test confirms notify-only classes never feed `AllFail`.
- The producer does not add a new reconciler action, DB write, order path, or RiskGovernor mutation.

### `engine_dead`

Passed:

- Producer is external to Rust and lives in `helper_scripts/canary/engine_dead_incident.py`.
- `network_outage` returns before the producer can run.
- Trigger requires snapshot stale >=30s and at least one failed respawn (`consecutive_failures >= 1`).
- `circuit_broken` suppresses `engine_dead` because circuit-broken is the stronger existing engine-down alert path.
- Output is local canary event plus existing alert sink only: `ENGINE_DEAD_NOTIFY_ONLY` and `ENGINE_DEAD_RESOLVED`.
- No Rust `AllFail`, C4 watcher feed, Defensive arm, restart policy change, auth/order/DB/risk/trading mutation, or Bybit request is introduced.

## Residual Notes

INFO-1: `sm_halt_stuck` is the only newly added arm-class producer. Its source path is acceptable, but full-chain E4/QA still needs to prove the integrated path from sustained incident to C4 owner handling under realistic push-channel failure.

INFO-2: `position_drift` producer state is in-memory. A process restart resets streaks and active signature. This is acceptable for notify-only coverage and matches the surrounding incident-policy source model; do not describe it as durable drift governance.

INFO-3: `engine_dead` intentionally cannot use the Rust `IncidentClass::EngineDead` sender while the engine is dead. That enum class remains a policy marker; the actual producer is watchdog-side notify-only.

## Evidence

Source anchors reviewed:

- `rust/openclaw_engine/src/event_consumer/sm_halt_incident.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/event_consumer/mod.rs`
- `rust/openclaw_engine/src/position_reconciler/incident.rs`
- `rust/openclaw_engine/src/position_reconciler/mod.rs`
- `rust/openclaw_engine/src/notification_failsafe/incident_policy.rs`
- `helper_scripts/canary/engine_dead_incident.py`
- `helper_scripts/canary/engine_watchdog.py`
- `helper_scripts/canary/test_canary.py`

Focused verification:

```bash
cd rust && cargo test -p openclaw_engine sm_halt_incident --lib
# 5 passed

cd rust && cargo test -p openclaw_engine position_reconciler::incident --lib
# 6 passed

cd rust && cargo test -p openclaw_engine notification_failsafe::incident_policy --lib
# 15 passed

cd rust && cargo test -p openclaw_engine event_consumer::tests::c4_failsafe_wire_tests --lib
# 4 passed

python3 -m py_compile helper_scripts/canary/engine_dead_incident.py helper_scripts/canary/engine_watchdog.py helper_scripts/canary/test_canary.py
# PASS

python3 -m pytest helper_scripts/canary/test_canary.py -k 'engine_dead or WatchdogAlertWiring' -q
# 5 passed, 82 deselected
```

## E2 Decision

Proceed to E4/QA/full-chain review. Producer coverage is no longer the blocker; the remaining blocker is integrated runtime-chain confidence and operator-gated deployment.
