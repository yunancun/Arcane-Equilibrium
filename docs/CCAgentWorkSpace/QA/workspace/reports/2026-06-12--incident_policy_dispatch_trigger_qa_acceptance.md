# QA Acceptance — P2 Incident Policy Dispatch Trigger

**Date**: 2026-06-12
**Role**: QA(worker), executed locally by PM session
**Scope**: source-level business-chain acceptance for `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` after BB/E2/E4.
**Boundary**: no CI, no deploy, no service rebuild, no service restart, no DB/auth/risk/order/trading mutation.

## Verdict

**STATUS: PASS_WITH_CONDITIONS**

The source business chain is accepted:

```text
producer -> incident_policy class ledger -> dispatch mode -> C4 watcher feed or notify-only -> existing downstream side-effect boundary
```

The acceptance is explicitly source-scoped. It is **not** deployed-E2E evidence and does not claim the active runtime binary contains this source chain.

## Acceptance Matrix

| Area | Evidence | Status |
|---|---|---|
| Arm-class path | `event_consumer::tests::c4_failsafe_wire_tests::e2e_c4_incident_policy_allfail_to_defensive_demo` passed on Mac and Linux source. This proves incident_policy `AllFail` feed -> watcher claim -> in-band C4 command -> Demo Defensive path. | PASS |
| Notify-only boundary | `notification_failsafe::incident_policy::tests::report_incident_notify_only_class_never_feeds_allfail` passed on Mac and Linux source. | PASS |
| External `engine_dead` boundary | `test_canary.py -k 'engine_dead or WatchdogAlertWiring'` passed on Mac and Linux source. | PASS |
| Bybit/order side effects | Focused grep: `engine_dead` production files contain only boundary comments for `AllFail`/`Defensive`; no `place_order`, `submit_order`, `cancel_order`, `close_position`, `set_trading_stop`, `OPENCLAW_ALLOW_MAINNET`, or `authorization.json`. `sm_halt` and `position_drift` producers only call `spawn_report_incident(...)`. | PASS |
| Class policy mapping | `IncidentClass::{AuthInvalid, BybitFailClosed, SmHaltStuck}` are `ArmTimer`; `IncidentClass::{EngineDead, PositionDrift}` are `NotifyOnly`. | PASS |
| Runtime sanity | Linux watchdog status: `engine_alive=true`, demo snapshot age 16.9s, live snapshot age 28.7s; `/api/v1/healthz` returned `status=ok`. This is current runtime health only, not source deploy proof. | PASS_WITH_SCOPE |

## Test Evidence

Mac source:

```bash
cargo test --release -p openclaw_engine \
  event_consumer::tests::c4_failsafe_wire_tests::e2e_c4_incident_policy_allfail_to_defensive_demo --lib
# 1 passed

cargo test --release -p openclaw_engine \
  notification_failsafe::incident_policy::tests::report_incident_notify_only_class_never_feeds_allfail --lib
# 1 passed

python3 -m pytest helper_scripts/canary/test_canary.py -k 'engine_dead or WatchdogAlertWiring' -q
# 5 passed, 82 deselected
```

Linux source:

```bash
cargo test --release -p openclaw_engine \
  event_consumer::tests::c4_failsafe_wire_tests::e2e_c4_incident_policy_allfail_to_defensive_demo --lib
# 1 passed

cargo test --release -p openclaw_engine \
  notification_failsafe::incident_policy::tests::report_incident_notify_only_class_never_feeds_allfail --lib
# 1 passed

python3 -m pytest helper_scripts/canary/test_canary.py -k "engine_dead or WatchdogAlertWiring" -q
# 5 passed, 82 deselected
```

Runtime read-only sanity:

```bash
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status
# engine_alive=true; demo age=16.9s; live age=28.7s

curl http://100.91.109.86:8000/api/v1/healthz
# {"status":"ok", ...}
```

## Caveats

1. Deployed-E2E is not performed. The active runtime remains operator/deploy gated; this QA report does not authorize a rebuild or restart.
2. The generic example route `/api/v1/health` and loopback `127.0.0.1:8000` failed during probing. Actual runtime bind is `100.91.109.86:8000`, and actual unauthenticated liveness route is `/api/v1/healthz`; this is route/topology drift in the QA smoke template, not an incident-policy regression.
3. Linux source was at `943c7a65` during focused tests while Mac/origin had advanced to `28bd0056`; the intervening commit is docs-only (`docs(l2): restore P4 online-FDR design report [skip ci]`) and does not touch incident-policy source. Final PM sync should still fast-forward Linux.

## QA Decision

`P2-INCIDENT-POLICY-DISPATCH-TRIGGER` may proceed to PM source closure. Runtime activation remains a separate operator-gated deploy/rebuild/restart decision.

**QA E2E ACCEPTANCE DONE: PASS_WITH_CONDITIONS · report path: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_qa_acceptance.md`**
